import os, time, sys
import requests
from pathlib import Path
from flask import Flask, request, jsonify, send_file, make_response
import logging
from logging.handlers import RotatingFileHandler
import subprocess
import shutil
import datetime
from cosyvoice.cli.cosyvoice import CosyVoice, CosyVoice2
from cosyvoice.utils.file_utils import load_wav
from urllib.parse import urlparse
import torchaudio, torch
import base64
from onnxruntime import SessionOptions, GraphOptimizationLevel, InferenceSession

# 初始化路径配置
root_dir = Path(__file__).parent.as_posix()

# 配置FFmpeg路径
if sys.platform == 'win32':
    os.environ['PATH'] = root_dir + f';{root_dir}\\ffmpeg;' + os.environ['PATH'] + f';{root_dir}/third_party/Matcha-TTS'
else:
    os.environ['PATH'] = root_dir + f':{root_dir}/ffmpeg:' + os.environ['PATH']
    os.environ['PYTHONPATH'] = os.environ.get('PYTHONPATH', '') + ':third_party/Matcha-TTS'
sys.path.append(f'{root_dir}/third_party/Matcha-TTS')

# 创建临时和日志目录
tmp_dir = Path(f'{root_dir}/tmp').as_posix()
logs_dir = Path(f'{root_dir}/logs').as_posix()
os.makedirs(tmp_dir, exist_ok=True)
os.makedirs(logs_dir, exist_ok=True)

# 配置日志
log = logging.getLogger('werkzeug')
log.handlers[:] = []
log.setLevel(logging.WARNING)
root_log = logging.getLogger()
root_log.handlers = []
root_log.setLevel(logging.WARNING)

app = Flask(__name__, static_folder=root_dir + '/tmp', static_url_path='/tmp')
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100 MB
app.logger.setLevel(logging.WARNING)
file_handler = RotatingFileHandler(logs_dir + f'/{datetime.datetime.now().strftime("%Y%m%d")}.log', maxBytes=1024 * 1024, backupCount=5)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setLevel(logging.WARNING)
file_handler.setFormatter(formatter)
app.logger.addHandler(file_handler)

# 全局模型变量
sft_model = None
tts_model = None
VOICE_LIST = ['中文女', '中文男', '日语男', '粤语女', '英文女', '英文男', '韩语女']

# 工具函数：Base64转WAV
def base64_to_wav(encoded_str, output_path):
    if not encoded_str:
        raise ValueError("Base64 encoded string is empty.")
    wav_bytes = base64.b64decode(encoded_str)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as wav_file:
        wav_file.write(wav_bytes)

# 工具函数：下载视频文件
def download_video(url, save_path):
    try:
        response = requests.get(url, stream=True)
        if response.status_code == 200:
            with open(save_path, 'wb') as file:
                for chunk in response.iter_content(chunk_size=8192):
                    file.write(chunk)
            return True
        else:
            app.logger.error(f"Failed to download video. Status code: {response.status_code}")
            return False
    except Exception as e:
        app.logger.error(f"Error downloading video: {e}")
        return False

# 获取请求参数
def get_params(req):
    params = {
        "text": "",
        "lang": "",
        "role": "",
        "reference_audio": None,
        "reference_text": "",
        "speed": 1.0
    }
    params['text'] = req.args.get("text", "").strip() or req.form.get("text", "").strip()
    params['lang'] = req.args.get("lang", "").strip().lower() or req.form.get("lang", "").strip().lower()
    if params['lang'] == 'ja':
        params['lang'] = 'jp'
    elif params['lang'][:2] == 'zh':
        params['lang'] = 'zh'
    role = req.args.get("role", "").strip() or req.form.get("role", "")
    if role:
        params['role'] = role
    
     # 直接使用原始路径，不进行Base64转换
    params['reference_audio'] = req.args.get("reference_audio", None) or req.form.get("reference_audio", None)
    
    # 如果是URL则下载，否则直接使用本地路径
    if params['reference_audio'] and urlparse(params['reference_audio']).scheme in ('http', 'https'):
        path = urlparse(params['reference_audio']).path
        file_name = os.path.basename(path).split('?')[0]
        tmp_name = f'tmp/{file_name}.wav'
        if not os.path.exists(tmp_name):
            if download_video(params['reference_audio'], tmp_name):
                params['reference_audio'] = tmp_name
            else:
                params['reference_audio'] = None
        else:
            params['reference_audio'] = tmp_name
    
    params['reference_text'] = req.args.get("reference_text", '').strip() or req.form.get("reference_text", '')
    return params

# 工具函数：删除临时文件
def del_tmp_files(tmp_files: list):
    app.logger.info('正在删除缓存文件...')
    for f in tmp_files:
        if os.path.exists(f):
            app.logger.info(f'删除缓存文件: {f}')
            os.remove(f)

def convert_to_wsl_path(win_path):
    win_path = win_path.replace('\\', '/')
    if ':' in win_path:
        drive, path = win_path.split(':', 1)
        return f'/mnt/{drive.lower()}{path}'
    return win_path

# 初始化ONNX Runtime
def initialize_onnx_runtime(model_path):
    providers = [
        ('CUDAExecutionProvider', {'device_id': 0}),
        'CPUExecutionProvider'
    ]
    session_options = SessionOptions()
    session_options.graph_optimization_level = GraphOptimizationLevel.ORT_ENABLE_ALL
    session_options.log_severity_level = 1  # 设置为1以获取详细日志
    return InferenceSession(model_path, session_options=session_options, providers=providers)

# 批量合成语音
def batch(tts_type, outname, params):
    global sft_model, tts_model
    if not shutil.which("ffmpeg"):
        raise Exception('必须安装 ffmpeg')
    prompt_speech_16k = None
    if tts_type != 'tts':
        if  params['reference_audio']:
            params['reference_audio'] = convert_to_wsl_path(params['reference_audio'])
            print(f"reference_audio:{params['reference_audio']}")
        if not params['reference_audio'] or not os.path.exists(f"{params['reference_audio']}"):
            raise Exception(f'参考音频未传入或不存在 {params["reference_audio"]}')
        ref_audio = f"{tmp_dir}/-refaudio-{time.time()}.wav"
        try:
            subprocess.run(["ffmpeg", "-hide_banner", "-ignore_unknown", "-y", "-i", params['reference_audio'], "-ar", "16000", ref_audio],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding="utf-8", check=True, text=True,
                           creationflags=0 if sys.platform != 'win32' else subprocess.CREATE_NO_WINDOW)
        except Exception as e:
            raise Exception(f'处理参考音频失败: {e}')
        prompt_speech_16k = load_wav(ref_audio, 16000)
    text = params['text']
    audio_list = []
    if tts_type == 'tts':
        if sft_model is None:
            sft_model = CosyVoice2('pretrained_models/CosyVoice2-0.5B', load_jit=True, load_trt=False, fp16=False)
        for i, j in enumerate(sft_model.inference_sft(text, params['role'], stream=False, speed=params['speed'])):
            audio_list.append(j['tts_speech'])
    elif tts_type == 'clone_eq' and params.get('reference_text'):
        if tts_model is None:
            tts_model = CosyVoice2('pretrained_models/CosyVoice2-0.5B', load_jit=True, load_trt=False, fp16=False)
        for i, j in enumerate(tts_model.inference_zero_shot(text, params.get('reference_text'), prompt_speech_16k, stream=False, speed=params['speed'])):
            audio_list.append(j['tts_speech'])
    else:
        if tts_model is None:
            tts_model = CosyVoice2('pretrained_models/CosyVoice2-0.5B', load_jit=True, load_trt=False, fp16=False)
        for i, j in enumerate(tts_model.inference_cross_lingual(text, prompt_speech_16k, stream=False, speed=params['speed'])):
            audio_list.append(j['tts_speech'])
    audio_data = torch.concat(audio_list, dim=1)
    if tts_type == 'tts':
        torchaudio.save(tmp_dir + '/' + outname, audio_data, 22050, format="wav")
    elif tts_type == 'clone_eq':
        torchaudio.save(tmp_dir + '/' + outname, audio_data, 24000, format="wav")
    else:
        torchaudio.save(tmp_dir + '/' + outname, audio_data, 24000, format="wav")
    app.logger.info(f"音频文件生成成功：{tmp_dir}/{outname}")
    return tmp_dir + '/' + outname

# 跨语言文字合成语音
@app.route('/clone_mul', methods=['GET', 'POST'])
@app.route('/clone', methods=['GET', 'POST'])
def clone():
    print("请求进入")
    try:
        params = get_params(request)
        if not params['text']:
            return make_response(jsonify({"code": 6, "msg": '缺少待合成的文本'}), 500)
        outname = f"clone-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S-')}.wav"
        outname = batch(tts_type='clone', outname=outname, params=params)
    except Exception as e:
        return make_response(jsonify({"code": 8, "msg": str(e)}), 500)
    else:
        return send_file(outname, mimetype='audio/x-wav')

# 启动API
if __name__ == '__main__':
    host = '127.0.0.1'
    port = 9233
    print(f'\n启动api:http://{host}:{port}\n')
    try:
        from waitress import serve
    except Exception:
        app.run(host=host, port=port)
    else:
        serve(app, host=host, port=port)
