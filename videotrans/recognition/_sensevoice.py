import os
import time
from typing import Union, List, Dict
import requests
import base64
from videotrans.configure import config
from videotrans.recognition._base import BaseRecogn
from videotrans.util import tools


class SenseVoiceRecogn(BaseRecogn):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.raws = []

    def _exec(self) -> Union[List[Dict], None]:
        if self._exit():
            return

        file_path = self.audio_file
        if not os.path.exists(file_path):
            raise Exception(f"音频文件不存在: {file_path}")
        language = self.detect_language[:2].lower()
        
        self._signal(text=f"开始识别音频，请稍候...")

        try:
            # 读取音频文件并转换为 Base64
            with open(file_path, "rb") as f:
                audio_base64 = base64.b64encode(f.read()).decode("utf-8")

            # 调用 FastAPI 服务的 /asr 接口
            url = "http://127.0.0.1:9232/asr"  # FastAPI 服务地址
            headers = {
                "language": language
            }
            payload = {
                "wav": audio_base64
            }
            response = requests.post(url, headers=headers, json=payload)

            if response.status_code != 200:
                raise Exception(f"语音识别失败: {response.status_code}, {response.text}")

            # 解析识别结果
            result = response.json()
            if result["code"] != 0:
                raise Exception(f"语音识别失败: {result['msg']}")

            segments = result["res"]  # 获取识别结果
            if not segments:
                raise Exception("未获取到有效的识别结果")

            # 处理识别结果
            self.source_srt_list = segments
            self._save_srt_target(segments, self.kwargs["source_sub"])

            # 转换为标准字幕格式
            for i, segment in enumerate(segments):
                if self._exit():
                    return
                srt = {
                    "line": i + 1,
                    "start_time": segment["start_time"],
                    "end_time": segment["end_time"],
                    "endraw": tools.ms_to_time_string(ms=segment["end_time"] * 1000),  # 秒转毫秒
                    "startraw": tools.ms_to_time_string(ms=segment["start_time"] * 1000),  # 秒转毫秒
                    "text": segment["text"]
                }
                srt['time'] = f'{srt["startraw"]} --> {srt["endraw"]}'
                self._signal(
                    text=f'{srt["line"]}\n{srt["time"]}\n{srt["text"]}\n\n',
                    type='subtitle'
                )
                self.raws.append(srt)
            return self.raws
        except Exception as e:
            raise Exception(f"语音识别失败: {str(e)}")