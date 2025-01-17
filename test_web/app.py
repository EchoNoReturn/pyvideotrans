from time import sleep
import gradio as gr

# from data_type.trans_video_req_data import TransVideoReqData
from use_server import TaskStatus, UsePyVideoServer
from data_type.trans_video_req_data import *
from data_type.tts_req_data import *

SERVER_URL = "http://127.0.0.1:9011"
server_instant = UsePyVideoServer(SERVER_URL)

def put_video(data: TransVideoReqData):
    task_id = server_instant.trans_video(data)
    print("===== START =====")
    while task_id:
        res = server_instant.get_task_status(task_id)
        status: TaskStatus = res.get("status")
        msg: str = res.get("msg", "")
        if status == TaskStatus.SUCCESS:
            print("===== SUCCESS =====")
            return {
                "absolute_path":  res.get('absolute_path', 'N/A'),
                "url": res.get('url', 'N/A'),
            }
        elif status == TaskStatus.FAILED:
            print("===== FAILED =====")
            print(f"task_id:{task_id} status:{status}")
            break
        else:
            print(f"task_id:{task_id} status:{status} msg:{msg}")
        sleep(1)


def handle(video_url):
    data = TransVideoReqData(
        name=video_url,
        translate_type = 0,   #翻译渠道
        target_language = "zh-cn",  #目标语言
        tts_type = 0,   #配音渠道
        subtitle_type = 1,  #字幕嵌入类型
    )
    
    res = put_video(data)
    if res:
        the_list = res['absolute_path'] if type(res['absolute_path']) == list else res['absolute_path']
        the_result = None
        for i in the_list:
            if i.endswith(".mp4"):
                the_result = i
                break
        if the_result:
            return the_result
    return video_url


def get_gradio_demo():
    with gr.Blocks() as demo:
        with gr.Row():
            with gr.Column():
                video_input = gr.Video(label="Video Input")
                run_button = gr.Button(value="Run")
            with gr.Column():
                video_output = gr.Video(label="Video Output")
        run_button.click(fn=handle, inputs=video_input, outputs=video_output)
        return demo


if __name__ == "__main__":
    demo = get_gradio_demo()
    demo.launch(share=True)
