import os,time,sys
import requests
from pathlib import Path
root_dir=Path(__file__).parent.as_posix()

# ffmpeg
if sys.platform == 'win32':
    os.environ['PATH'] = root_dir + f';{root_dir}\\ffmpeg;' + os.environ['PATH']+f';{root_dir}/third_party/Matcha-TTS'
else:
    os.environ['PATH'] = root_dir + f':{root_dir}/ffmpeg:' + os.environ['PATH']
    os.environ['PYTHONPATH'] = os.environ.get('PYTHONPATH', '') + ':third_party/Matcha-TTS'
sys.path.append(f'{root_dir}/third_party/Matcha-TTS')
tmp_dir=Path(f'{root_dir}/tmp').as_posix()
logs_dir=Path(f'{root_dir}/logs').as_posix()
os.makedirs(tmp_dir,exist_ok=True)
os.makedirs(logs_dir,exist_ok=True)

from flask import Flask, request, render_template, jsonify,  send_from_directory,send_file,Response, stream_with_context,make_response,send_file
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import shutil
import datetime
from cosyvoice.cli.cosyvoice import CosyVoice, CosyVoice2
from cosyvoice.utils.file_utils import load_wav
from urllib.parse import urlparse


import torchaudio,torch
from pathlib import Path
import base64

'''
app logs
'''
# 配置日志
# 禁用 Werkzeug 默认的日志处理器
log = logging.getLogger('werkzeug')
log.handlers[:] = []
log.setLevel(logging.WARNING)
root_log = logging.getLogger()  # Flask的根日志记录器
root_log.handlers = []
root_log.setLevel(logging.WARNING)

app = Flask(__name__, 
    static_folder=root_dir+'/tmp', 
    static_url_path='/tmp')

app.logger.setLevel(logging.WARNING) 
# 创建 RotatingFileHandler 对象，设置写入的文件路径和大小限制
file_handler = RotatingFileHandler(logs_dir+f'/{datetime.datetime.now().strftime("%Y%m%d")}.log', maxBytes=1024 * 1024, backupCount=5)
# 创建日志的格式
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# 设置文件处理器的级别和格式
file_handler.setLevel(logging.WARNING)
file_handler.setFormatter(formatter)
# 将文件处理器添加到日志记录器中
app.logger.addHandler(file_handler)



sft_model = None
tts_model = None 

VOICE_LIST=['中文女', '中文男', '日语男', '粤语女', '英文女', '英文男', '韩语女']





def base64_to_wav(encoded_str, output_path):
    if not encoded_str:
        raise ValueError("Base64 encoded string is empty.")

    # 将base64编码的字符串解码为字节
    wav_bytes = base64.b64decode(encoded_str)

    # 检查输出路径是否存在，如果不存在则创建
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    # 将解码后的字节写入文件
    with open(output_path, "wb") as wav_file:
        wav_file.write(wav_bytes)

# 下载视频文件到指定路径
def download_video(url, save_path):
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(save_path, 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
            return True
        else:
            print(f"Failed to download video. Status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"Error downloading video: {e}")
        return False

# 获取请求参数
def get_params(req):
    params={
        "text":"",
        "lang":"",
        "role":"",
        "reference_audio":None,
        "reference_text":"",
        "speed":1.0
    }
    # 原始字符串
    params['text'] = req.args.get("text","").strip() or req.form.get("text","").strip()
    
    # 字符串语言代码
    params['lang'] = req.args.get("lang","").strip().lower() or req.form.get("lang","").strip().lower()
    # 兼容 ja语言代码
    if params['lang']=='ja':
        params['lang']='jp'
    elif params['lang'][:2] == 'zh':
        # 兼容 zh-cn zh-tw zh-hk
        params['lang']='zh'
    
    # 角色名 
    role = req.args.get("role","").strip() or req.form.get("role",'')
    if role:
        params['role']=role
    
    # 要克隆的音色文件    
    params['reference_audio'] = req.args.get("reference_audio",None) or req.form.get("reference_audio",None)
    encode=req.args.get('encode','') or req.form.get('encode','')
    if  encode=='base64':
        tmp_name=f'tmp/{time.time()}-clone-{len(params["reference_audio"])}.wav'
        base64_to_wav(params['reference_audio'],root_dir+'/'+tmp_name)
        params['reference_audio']=tmp_name
    else:
        # 生成临时文件名
        path = urlparse(params['reference_audio']).path
        file_name = os.path.basename(path).split('?')[0]
        tmp_name = f'tmp/{file_name}.wav'

        # 判断文件是否存在
        if not os.path.exists(tmp_name):
            # 下载视频
            if download_video(params['reference_audio'], tmp_name):
                params['reference_audio'] = tmp_name
            else:
                params['reference_audio'] = None  # 下载失败，设置为 None
        else:
            # 文件已存在，直接使用
            params['reference_audio'] = tmp_name
    
    # 音色文件对应文本
    params['reference_text'] = req.args.get("reference_text",'').strip() or req.form.get("reference_text",'')
    
    return params



def del_tmp_files(tmp_files: list):
    print('正在删除缓存文件...')
    for f in tmp_files:
        if os.path.exists(f):
            print('删除缓存文件:', f)
            os.remove(f)



# 实际批量合成完毕后连接为一个文件
def batch(tts_type,outname,params):
    print(f'tts_type:{tts_type},')
    print(f'outname:{outname}')
    print(f'params:{params}')
    global sft_model,tts_model
    if not shutil.which("ffmpeg"):
        raise Exception('必须安装 ffmpeg')    
    prompt_speech_16k=None
    if tts_type!='tts':
        if not params['reference_audio'] or not os.path.exists(f"{root_dir}/{params['reference_audio']}"):
            raise Exception(f'参考音频未传入或不存在 {params["reference_audio"]}')
        ref_audio=f"{tmp_dir}/-refaudio-{time.time()}.wav" 
        try:
            subprocess.run(["ffmpeg","-hide_banner", "-ignore_unknown","-y","-i",params['reference_audio'],"-ar","16000",ref_audio],
                   stdout=subprocess.PIPE,
                   stderr=subprocess.PIPE,
                   encoding="utf-8",
                   check=True,
                   text=True,
                   creationflags=0 if sys.platform != 'win32' else subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            raise Exception(f'处理参考音频失败:{e}')
        prompt_speech_16k = load_wav(ref_audio, 16000)

    text=params['text']
    audio_list=[]
    if tts_type=='tts':
        if sft_model is None:
            sft_model = CosyVoice2('pretrained_models/CosyVoice2-0.5B', load_jit=True,load_trt=False,fp16=False)
        # 仅文字合成语音
        for i, j in enumerate(sft_model.inference_sft(text, params['role'],stream=False,speed=params['speed'])):
            audio_list.append(j['tts_speech'])       
    elif tts_type=='clone_eq' and params.get('reference_text'):
        if tts_model is None:
            tts_model=CosyVoice2('pretrained_models/CosyVoice2-0.5B', load_jit=True,load_trt=False,fp16=False)
        for i, j in enumerate(tts_model.inference_zero_shot(text,params.get('reference_text'),prompt_speech_16k, stream=False,speed=params['speed'])):
            audio_list.append(j['tts_speech'])
    else:
        if tts_model is None:
            tts_model=CosyVoice2('pretrained_models/CosyVoice2-0.5B', load_jit=True,load_trt=False,fp16=False)
        print(text)
        for i, j in enumerate(tts_model.inference_cross_lingual(text,prompt_speech_16k, stream=False,speed=params['speed'])):
            audio_list.append(j['tts_speech'])
            
    audio_data = torch.concat(audio_list, dim=1)
    
    # 根据模型yaml配置设置采样率
    if tts_type=='tts':
        torchaudio.save(tmp_dir + '/' + outname,audio_data, 22050, format="wav")   
    elif tts_type=='clone_eq':
        torchaudio.save(tmp_dir + '/' + outname,audio_data, 24000, format="wav")   
    else:
        torchaudio.save(tmp_dir + '/' + outname,audio_data, 24000, format="wav")    
    
    print(f"音频文件生成成功：{tmp_dir}/{outname}")
    return tmp_dir + '/' + outname


# 单纯文字合成语音
@app.route('/tts', methods=['GET', 'POST'])        
def tts():
    params=get_params(request)
    if not params['text']:
        return make_response(jsonify({"code":1,"msg":'缺少待合成的文本'}), 500)  # 设置状态码为500      
    try:
        # 仅文字合成语音
        outname=f"tts-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S-')}.wav"
        outname=batch(tts_type='tts',outname=outname,params=params)
    except Exception as e:
        print(e)
        return make_response(jsonify({"code":2,"msg":str(e)}), 500)  # 设置状态码为500
    else:
        return send_file(outname, mimetype='audio/x-wav')
    

# 跨语言文字合成语音      
@app.route('/clone_mul', methods=['GET', 'POST'])        
@app.route('/clone', methods=['GET', 'POST'])        
def clone():
    print("请求进入")
    try:
        params=get_params(request)
        if not params['text']:
            return make_response(jsonify({"code":6,"msg":'缺少待合成的文本'}), 500)  # 设置状态码为500
        outname=f"clone-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S-')}.wav"
        outname=batch(tts_type='clone',outname=outname,params=params)
    except Exception as e:
        return make_response(jsonify({"code":8,"msg":str(e)}), 500)  # 设置状态码为500
    else:
        return send_file(outname, mimetype='audio/x-wav')


@app.route('/clone_eq', methods=['GET', 'POST'])         
def clone_eq():
    try:
        params=get_params(request)
        if not params['text']:
            return make_response(jsonify({"code":6,"msg":'缺少待合成的文本'}), 500)  # 设置状态码为500
        if not params['reference_text']:
            return make_response(jsonify({"code":6,"msg":'同语言克隆必须传递引用文本'}), 500)  # 设置状态码为500
            
        outname=f"clone-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S-')}.wav"
        outname=batch(tts_type='clone_eq',outname=outname,params=params)
    except Exception as e:
        return make_response(jsonify({"code":8,"msg":str(e)}), 500)  # 设置状态码为500
    else:
        return send_file(outname, mimetype='audio/x-wav')


@app.route('/v1/audio/speech', methods=['POST'])
def audio_speech():
    """
    兼容 OpenAI /v1/audio/speech API 的接口
    """
    import random

    if not request.is_json:
        return jsonify({"error": "请求必须是 JSON 格式"}), 400

    data = request.get_json()

    # 检查请求中是否包含必要的参数
    if 'input' not in data or 'voice' not in data:
        return jsonify({"error": "请求缺少必要的参数： input, voice"}), 400
    

    text = data.get('input')
    speed =  float(data.get('speed',1.0))
    
    voice = data.get('voice','中文女')
    params = {}
    params['text']=text
    params['speed']=speed
    api_name='tts'
    if voice in VOICE_LIST:
        params['role']=voice
    elif Path(voice).exists() or Path(f'{root_dir}/{voice}').exists():
        api_name='clone'
        params['reference_audio']=voice
    else:
        return jsonify({"error": {"message": f"必须填写配音角色名或参考音频路径", "type": e.__class__.__name__, "param": f'speed={speed},voice={voice},input={text}', "code": 400}}), 500

    
    filename=f'openai-{len(text)}-{speed}-{time.time()}-{random.randint(1000,99999)}.wav'
    try:
        outname=batch(tts_type=api_name,outname=filename,params=params)
        return send_file(outname, mimetype='audio/x-wav')
    except Exception as e:
        return jsonify({"error": {"message": f"{e}", "type": e.__class__.__name__, "param": f'speed={speed},voice={voice},input={text}', "code": 400}}), 500


if __name__=='__main__':
    host='127.0.0.1'
    port=9233
    print(f'\n启动api:http://{host}:{port}\n')
    try:
        from waitress import serve
    except Exception:
        app.run(host=host, port=port)
    else:
        serve(app,host=host, port=port)
