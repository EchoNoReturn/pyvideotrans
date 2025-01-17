import requests
import enum
import json

from data_type.tts_req_data import TTSReqData
from data_type.trans_video_req_data import TransVideoReqData

TTS_TYPE_DICT = {
    0: "Edge-TTS",
    1: "CosyVoice",
    2: "ChatTTS",
    3: "302.AI",
    4: "FishTTS",
    5: "Azure-TTS",
    6: "GPT-SoVITS",
    8: "OpenAI TTS",
    9: "Elevenlabs.io",
    10: "Google TTS",
    11: "自定义TTS API",
}


class TaskStatus(enum.Enum):
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class UsePyVideoServer(object):
    def __init__(self, server_addr: str):
        self.server_addr = (
            server_addr if server_addr.endswith("/") else f"{server_addr}/"
        )

    def _get_req_url(self, path: str):
        return f"{self.server_addr}{path}"

    def tts(self, data: TTSReqData):
        url = self._get_req_url("tts")
        res = requests.post(url, json=data)
        return res.json()

    # 翻译视频
    def trans_video(self, data: TransVideoReqData):
        url = self._get_req_url("trans_video")
        # print(json.dumps(data.__dict__), json.loads(json.dumps(data.__dict__)))
        res = requests.post(url, json=json.dumps(data.__dict__))
        try:
            res_data = res.json()
            print(f"res_data:{res_data}")
            return f"{res_data['task_id']}" if res_data['code'] == 0 else None
        except Exception as e:
            print(e)
            return None

    # 翻译状态获取
    def get_task_status(self, task_id: str):
        url = self._get_req_url(f"task_status?task_id={task_id}")
        res = requests.get(url)
        res_data = res.json()
        if res_data['code'] == 0:
            return {
                "status": TaskStatus.SUCCESS,
                "msg": res_data['msg'],
                "absolute_path": res_data['data']['absolute_path'],
                "url":  res_data['data']['url'],
            }
        elif res_data['code'] == -1:
            return {"status": TaskStatus.RUNNING, "msg": res_data['msg']}
        else:
            return {"status": TaskStatus.FAILED, "msg": "操作失败"}
