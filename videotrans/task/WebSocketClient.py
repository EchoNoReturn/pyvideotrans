import websocket
import json
import threading


class WebSocketClient:
    def __init__(self, url):
        self.url = url
        self.ws = websocket.WebSocketApp(
            url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_close=self.on_close,
            on_error=self.on_error
        )

    def on_open(self, ws):
        print(" websocket connection successful============================> ")

    def on_message(self, ws, message):
        print("websocket msg：", json.loads(message))

    def on_close(self, ws, *args):
        print("websocket close")

    def on_error(self, ws, error):
        print("websocket error:", error)

    def send(self, msg_dict):
        if self.ws.sock and self.ws.sock.connected:
            self.ws.send(json.dumps(msg_dict))
        else:
            print("WebSocket 连接尚未建立或已关闭，无法发送消息")

    def run(self):
        thread = threading.Thread(target=self.ws.run_forever)
        thread.daemon = True
        thread.start()
