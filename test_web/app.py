from time import sleep
import gradio as gr

from use_server import TaskStatus, UsePyVideoServer
from data_type.trans_video_req_data import *

SERVER_URL = "http://127.0.0.1:9011"
server_instant = UsePyVideoServer(SERVER_URL)


def put_video(data: TransVideoReqData):
    task_id = server_instant.trans_video(data)
    while task_id:
        res = server_instant.get_task_status(task_id)
        status: TaskStatus = res.get("status")
        msg: str = res.get("msg", "")
        if status == TaskStatus.SUCCESS:
            print("===== SUCCESS =====")
            print(f"Response: {res}")
            return {
                "absolute_path": res.get("absolute_path", "N/A"),
                "url": res.get("url", "N/A"),
            }
        elif status == TaskStatus.FAILED:
            print("===== FAILED =====")
            print(f"task_id:{task_id} status:{status}")
            break
        else:
            print(f"task_id:{task_id} status:{status} msg:{msg}")
        sleep(1)


def handle(
    video_url,
    source_language,
    target_language,
):
    data = TransVideoReqData(
        name=video_url,
        source_language=source_language,  # 源语言
        target_language=target_language,  # 目标语言
    )
    res = put_video(data)
    if res:
        the_list = (
            res["absolute_path"]
            if isinstance(res["absolute_path"], list)
            else res["absolute_path"]
        )
        the_result = None
        for i in the_list:
            if i.endswith(".mp4"):
                the_result = i
                break
        if the_result:
            return the_result
    return video_url


def get_gradio_demo():
    # 源语言
    source_languages = [
        ("中文", "zh-cn"),
        ("英语", "en"),
        ("日语", "ja"),
        ("韩语", "ko"),
    ]
    # 目标语言
    target_languages = [
        ("中文", "zh-cn"),
        ("英语", "en"),
        ("日语", "ja"),
        ("韩语", "ko"),
    ]

    with gr.Blocks() as demo:
        with gr.Row():
            with gr.Column():
                video_input = gr.Video(label="视频输入")
                with gr.Row():
                    source_language = gr.Dropdown(
                        label="源语言",
                        choices=source_languages,
                        value=source_languages[0][1],
                    )
                    target_language = gr.Dropdown(
                        label="目标语言",
                        choices=target_languages,
                        value=target_languages[1][1],
                    )
                run_button = gr.Button(value="运行")
            with gr.Column():
                video_output = gr.Video(label="视频输出")
        run_button.click(
            fn=handle,
            inputs=[
                video_input,
                source_language,
                target_language,
            ],
            outputs=[video_output],
        )
        return demo


if __name__ == "__main__":
    demo = get_gradio_demo()
    demo.launch(share=True)
