import requests
import json
import os
from pathlib import Path

class http_request:

    @staticmethod
    def send_request(endpoint, method="POST", body=None, headers=None):
        java_config_file_path =  Path(__file__).parent.resolve() / "config.json"
        java_server_port = ""
        with open(java_config_file_path, "r", encoding="utf-8") as f:
            java_server_port = json.loads(f.read())["java_server_prot"]
        url = f"http://127.0.0.1:{java_server_port}/front{endpoint}"
        try:
            response = requests.request(method, url, json=body, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"请求失败: {e}")
            return {"code": 1, "message": "请求失败"}

    def modify_video(self, video_data):
        endpoint = "/vid/video/modify"
        headers = {
            "Content-Type": "application/json",
        }
        return self.send_request(endpoint, method="POST", body=video_data, headers=headers)