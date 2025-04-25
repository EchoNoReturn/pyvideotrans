import copy
import json
import os
import time
import requests

from pydub import AudioSegment
from pathlib import Path
from videotrans.configure import config
from videotrans.tts._base import BaseTTS
from videotrans.util import tools


# 线程池并发 返回wav数据转为mp3
class SparkTTS(BaseTTS):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.copydata = copy.deepcopy(self.queue_tts)
        api_url = config.params["sparktts_url"].strip().rstrip("/").lower()
        self.api_url = "http://" + api_url.replace("http://", "")
        self.proxies = {"http": "", "https": ""}

    def _exec(self):
        self._local_mul_thread()

    def _item_task(self, data_item: dict = None):
        if self._exit():
            return
        if not data_item:
            return
        try:
            text = data_item["text"].strip()
            prompt_text = data_item["ref_text"].strip()
            if not text:
                return
            role = data_item["role"]
            api_url = self.api_url
            data = {
                "text": text,
                "prompt_text": prompt_text,
                "save_path":os.path.dirname(data_item['filename']),
                "file_save_name":os.path.splitext(os.path.basename(data_item['filename']))[0],
                "file_sava_suffix" : "wav",
            }

            if role == "clone":
                if data_item.get("ref_wav") is None:
                    raise Exception("没有参考音频")
                data["audio_path"] = data_item["ref_wav"]
            elif role == "clone-single":
                # 自定义音色
                data["audio_path"] = data_item["ref_audio"]
            api_url += "/tts"

            # 克隆声音
            response = requests.post(
                f"{api_url}",
                data=data,
                proxies={"http": "", "https": ""},
                timeout=3600,
            )

            if response.status_code != 200:
                # 如果是JSON数据，使用json()方法解析
                self.error = f"SparkTTS 返回错误信息 status_code={response.status_code} {response.reason}:{response.text}"
                Path(data_item["filename"]).unlink(missing_ok=True)
                return
            if not os.path.exists(data['save_path']+"/"+data["file_save_name"]+".wav"):
                self.error = f"SparkTTS 合成声音失败-2:{text=}"
                return
            tools.wav2mp3(data['save_path']+"/"+data["file_save_name"]+".wav", data_item["filename"])
            # time.sleep(1)
            if self.inst and self.inst.precent < 80:
                self.inst.precent += 0.1
            self.error = ""
            self.has_done += 1
        except (requests.ConnectionError, requests.Timeout) as e:
            self.error = (
                "连接失败，请检查是否启动了api服务"
                if config.defaulelang == "zh"
                else "Connection failed, please check if the api service is started"
            )
        except Exception as e:
            self.error = str(e)
            config.logger.exception(e, exc_info=True)
        finally:
            if self.error:
                self._signal(text=self.error)
            else:
                self._signal(
                    text=f'{config.transobj["kaishipeiyin"]} {self.has_done}/{self.len}'
                )
        return
