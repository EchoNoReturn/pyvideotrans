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


def handle(video_url, translate_type, target_language, tts_type, subtitle_type,voice_role,voice_autorate):
    data = TransVideoReqData(
        name=video_url,
        translate_type=translate_type,   #翻译渠道
        target_language=target_language,  #目标语言
        tts_type=tts_type,   #配音渠道
        subtitle_type=subtitle_type,  #字幕嵌入类型
        voice_role=voice_role,
        video_autorate=voice_autorate,
    )
    
    res = put_video(data)
    if res:
        the_list = res['absolute_path'] if isinstance(res['absolute_path'], list) else res['absolute_path']
        the_result = None
        for i in the_list:
            if i.endswith(".mp4"):
                the_result = i
                break
        if the_result:
            return the_result
    return video_url


def get_gradio_demo():
    # 翻译渠道
    translate_types = [
        ("谷歌翻译", 0),
    ]
    # 目标语言
    target_languages = [
        ("中文简体", "zh-cn"),
        ("中文繁體", "zh-tw"),
        ("English", "zh-cn"),
        ("French", "fr"),
    ]
    # 配音渠道
    tts_types = [
        ("Edge-TTS", 0),
    ]
    # 字幕嵌入类型
    subtitle_types = [
        ("不嵌入字幕", 0),
        ("嵌入硬字幕", 1),
        ("嵌入软字幕", 2),
        ("嵌入双硬字幕", 3),
        ("嵌入双软字幕", 4),
    ]
    # 配音角色
    voice_roles = [
        ("无","no"),
        ("YunjianNeural(zh-CN)","zh-CN-YunjianNeural"),
    ]
    
    with gr.Blocks() as demo:
        with gr.Row():
            with gr.Column():
                video_input = gr.Video(label="视频输入")
                with gr.Row():
                    translate_type = gr.Dropdown(label="翻译渠道", choices=translate_types, value=translate_types[0][1])
                    target_language = gr.Dropdown(label="目标语言", choices=target_languages, value=target_languages[0][1])
                    tts_type= gr.Dropdown(label="配音渠道", choices=tts_types, value=tts_types[0][1])
                with gr.Row():
                    subtitle_type= gr.Dropdown(label="字幕嵌入类型", choices=subtitle_types, value=subtitle_types[0][1])
                    voice_role = gr.Dropdown(label="配音角色",choices=voice_roles,value=voice_roles[0][1])
                    voice_autorate = gr.Radio(label="是否自动加快语速与字幕对齐", choices=[True, False], value=False)
                run_button = gr.Button(value="运行")
            with gr.Column():
                video_output = gr.Video(label="视频输出")
                logText = gr.Textbox(label="运行日志")
        run_button.click(
            fn=handle, 
            inputs=[video_input,translate_type,target_language,tts_type,subtitle_type,voice_role,voice_autorate], 
            outputs=video_output
        )
        return demo

if __name__ == "__main__":
    demo = get_gradio_demo()
    demo.launch(share=True)
