import os
import re
import time
import uuid
import base64
import shutil
import uvicorn
import requests
from datetime import datetime
from datetime import datetime
from pydantic import BaseModel
from pydub import AudioSegment
from http.client import HTTPException
from pydub.silence import split_on_silence
from fastapi import FastAPI, File, Form, UploadFile


app = FastAPI()

class SplitAudio:

    # 将毫秒转换为 SRT 格式时间戳（HH+MM+SS,mmm） 示例: 00+00+00,000 
    @staticmethod
    def format_time(ms):
        seconds, milliseconds = divmod(ms, 1000)
        minutes, seconds = divmod(seconds, 60)
        hours, minutes = divmod(minutes, 60)
        return f"{hours:02}+{minutes:02}+{seconds:02},{milliseconds:03}"


    """
    分割文件
        :param :silence_thresh 静音阈值
            这个参数表示音量低于 -40 dBFS (分贝全刻度) 时, 认为是“静音”
            值越小 (如 -50) 表示更安静的部分才会被当作静音。
            值越大 (如 -30) 则稍微安静一点的声音也会被认为是静音。
        :param :min_silence_len 最小静音时长(毫秒)
            这个参数表示静音时长 (静音持续时间小于 min_silence_len) 的长度。
            值越小, 则更短的静音时长将被认为是静音。
            值越大, 则更长的静音时长将被认为是静音。
    """
    @staticmethod
    def split_audio_by_silence(input_file, output_folder, silence_thresh=-39, min_silence_len=180):
        os.makedirs(os.path.join(output_folder), exist_ok=True)
        audio = AudioSegment.from_file(input_file)
        segments = split_on_silence(audio, silence_thresh=silence_thresh, min_silence_len=min_silence_len)

        gap_time =400  # 设定延长时间 (单位: ms)
        total_start_time = 0
        for i, segment in enumerate(segments):
            segment_start_time = total_start_time  # 起始时间
            segment_duration = len(segment)  # 片段的持续时间
            segment_end_time = segment_start_time + segment_duration + gap_time # 片段的结束时间
            total_start_time = segment_end_time + 1  # 计算下一个片段的起始时间
            start_time_str = SplitAudio.format_time(segment_start_time)
            end_time_str = SplitAudio.format_time(segment_end_time)
            file_name = f"{i+1}_to_{start_time_str}_to_{end_time_str}.wav"
            file_path = os.path.join(output_folder, file_name)
            segment.export(file_path, format="wav")

    # 本地源文件存储路径 -> 项目根路径/temp_file/{uuid_str}/
    @staticmethod
    def download_local():
        project_root = os.path.dirname(os.path.abspath(__file__))
        uuid_str = str(uuid.uuid4())
        wav_path = os.path.join(project_root, "temp_file", uuid_str)
        os.makedirs(wav_path, exist_ok=True)
        return wav_path

    # 排序，用于对文件名进行排序
    @staticmethod
    def natural_sort_key(s):
        return [int(text) if text.isdigit() else text.lower() for text in re.split(r'(\d+)', s)]

    # 生成随机 UUID 字符串
    @staticmethod
    def uuid_str():
        return str(uuid.uuid4())

    # 调用语音识别模型api
    @staticmethod
    def asr_damo_api(file_input,language:str):
        """ 
        语音识别 API，支持文件路径、文件流和 URL
        :param file_input: 可以是 文件路径 (str)、文件流 (file object) 或 URL (str)
        :return: 识别结果 (str)
        """
        # 设置请求头，指定数据格式
        headers = {
            'Content-Type': 'application/json',
            'language':language
            }

        # 处理 URL 或本地文件
        if isinstance(file_input, str):
                file_input = open(file_input, "rb")  
        # 处理文件流
        wav = base64.b64encode(file_input.read()).decode()
        data = {
            "wav": wav
            }
        # 发起POST请求，发送数据进行语音识别
        url = "http://127.0.0.1:10086/"
        response = requests.post(url + "asr", headers=headers, json=data).json()
        # 根据响应结果返回识别结果或错误信息
        return response['res'] if response['code'] == 0 else response['msg']
    
    # 将SRT格式时间转换为毫秒
    @staticmethod
    def time_to_milliseconds(time_str):
        time_obj = datetime.strptime(time_str, "%H:%M:%S,%f")
        return (time_obj.hour * 3600 + time_obj.minute * 60 + time_obj.second) * 1000 + time_obj.microsecond // 1000

@app.post("/asr/client")
async def asr(language: str = Form(...),file: UploadFile = File(...)):
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  --->  {file.filename}")
    start_time = time.time()

    # 读取文件内容
    file_content = await file.read()
    
    # 下载本地路径
    wav_local_path = SplitAudio.download_local()
    
    # 源文件写入本地
    input_audio_path = os.path.join(wav_local_path, file.filename)
    with open(input_audio_path, "wb") as buffer:
        buffer.write(file_content)

    # 音频切割
    wav_local_path = os.path.join(wav_local_path,"audio")
    SplitAudio.split_audio_by_silence(input_audio_path, wav_local_path)

    # 获取切割后的文件列表
    file_list = sorted(os.listdir(wav_local_path), key = SplitAudio.natural_sort_key)
    if file_list:
        data_list = []
        line = 0
        for audio_file in file_list:
            line += 1
            local_file_path = os.path.join(wav_local_path, audio_file)
            msg = SplitAudio.asr_damo_api(local_file_path,language = language)
            audio_file = audio_file.replace("+", ":")
            audio_file = audio_file.split("_to_")
            data = {
                'line':line,
                'start_time':SplitAudio.time_to_milliseconds(audio_file[1]),
                'end_time':SplitAudio.time_to_milliseconds(audio_file[2].replace(".wav", "")),
                'text':msg,
                'startraw':audio_file[1],
                'endraw':audio_file[2].replace(".wav", ""),
                'time':audio_file[1]+" --> "+audio_file[2].replace(".wav", "")
            }

            # 构建data数据
            data_list.append(data)

        # 耗时
        print(f"耗时: {round(time.time() - start_time, 2)}s")

        # 删除临时文件夹
        shutil.rmtree(os.path.dirname(wav_local_path))

        # 返回数据
        return {
                'code':0,
                'msg':'success',
                'data':data_list,
                'total':len(file_list),
                'time':round(time.time() - start_time, 2)
            }
    else:
        return {
                'code':1,
                'msg':'error'
            }



#
if __name__ == "__main__":
    # uvicorn.run(app, host='0.0.0.0', port=10001)
    uvicorn.run(app, host='127.0.0.1', port=10001) # 本地服务