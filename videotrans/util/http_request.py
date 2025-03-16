import requests
import json

class http_request:

    @staticmethod
    def send_request(endpoint, method="POST", body=None, headers=None):
        url = f"http://127.0.0.1:8080{endpoint}"
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