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

def handle(video_url,  source_language, translate_type, target_language, model_name, subtitle_type,tts_type, voice_role, voice_autorate,is_separate,remove_noise,is_cuda):
    data = TransVideoReqData(
        name=video_url,
        source_language=source_language,  # 源语言
        translate_type=translate_type,   #翻译渠道
        target_language=target_language,  #目标语言
        tts_type=tts_type,   #配音渠道
        model_name=model_name,  #模型名称
        subtitle_type=subtitle_type,    #字幕嵌入类型
        voice_role=voice_role,  #角色类型
        video_autorate=voice_autorate,  #自动对齐
        is_separate = is_separate, # 保存背景音乐
        remove_noise=remove_noise,  #降噪
        is_cuda=is_cuda,    #CUDA加速
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
    # 源语言
    source_languages = [
        ("自动检测", "auto"),
        ("中文", "zh-cn"),
        ("英语", "en"),
        ("日语", "ja"),
        ("韩语", "ko"),
    ]
    # 翻译渠道
    translate_types = [
        ("谷歌翻译", 0),
        ("微软翻译", 1),
        ("千问翻译", 19),
        ("deepseek 翻译", 20),
    ]
    # 目标语言
    target_languages = [
        ("中文", "zh-cn"),
        ("英语", "en"),
        ("日语", "ja"),
        ("韩语", "ko"),
    ]
    # 模型名称
    model_names = [
        ("tiny", "tiny"),
        ("medium", "medium"),
        ("large-v3", "large-v3"),
    ]
    # 字幕嵌入类型
    subtitle_types = [
        ("不嵌入字幕", 0),
        ("嵌入硬字幕", 1),
        ("嵌入软字幕", 2),
        ("嵌入双硬字幕", 3),
        ("嵌入双软字幕", 4),
    ]
    # 配音渠道
    tts_types = [
        ("Edge-TTS",0),
        ("CosyVoice-TTS",1),
    ]
    
    # 配音角色
    voice_roles = [],
    edge_voice_roles = [
        ("无配音","No"),
        # 中文配音
        ("云健 - 男声(zh-CN)","zh-CN-YunjianNeural"),
        ("晓晓 - 女声(zh-CN)","zh-CN-XiaoxiaoNeural"),
        ("云扬 - 男声(zh-CN)","zh-CN-YunyangNeural"),
        ("晓辰 - 女声(zh-CN)","zh-CN-XiaochenNeural"),
        # # 英文配音
        ("Guy - 男声(en-US)","en-US-GuyNeural"),
        ("Jenny - 女声(en-US)","en-US-JennyNeural"),
        # # 日语配音
        ("圭太 - 男声(ja-JP)", "ja-JP-KeitaNeural"),
        ("七海 - 女声(ja-JP)", "ja-JP-NanamiNeural"),
        # # 韩语配音
        ("인준 - 男声(ko-KR)", "ko-KR-InJoonNeural"),
        ("지민 - 女声(ko-KR)", "ko-KR-JiMinNeural"),
    ]
    cosy_voice_roles = [
        ("无配音", "No"),
        ("克隆", "clone"),
    ]
    
    with gr.Blocks() as demo:
        with gr.Row():
            with gr.Column():
                video_input = gr.Video(label="视频输入")
                with gr.Row():
                    source_language = gr.Dropdown(label="源语言", choices=source_languages,value=source_languages[0][1])
                    translate_type = gr.Dropdown(label="翻译渠道", choices=translate_types, value=translate_types[1][1])
                    target_language = gr.Dropdown(label="目标语言", choices=target_languages,value=target_languages[1][1])
                with gr.Row():
                    model_name = gr.Dropdown(label="语音识别模型", choices=model_names, value=model_names[1][1])
                    subtitle_type= gr.Dropdown(label="字幕嵌入类型", choices=subtitle_types, value=subtitle_types[0][1])
                with gr.Row():
                    tts_type = gr.Dropdown(label="配音渠道", choices=tts_types, value=tts_types[0][1])
                    voice_role = gr.Dropdown(label="配音角色", choices=edge_voice_roles, value=edge_voice_roles[0][1])
                with gr.Row():
                    voice_autorate = gr.Radio(label="加快语速对齐", choices=[True, False], value=False)
                    is_separate = gr.Radio(label="保留背景音乐", choices=[True, False], value=False)
                    remove_noise = gr.Radio(label="人声降噪", choices=[True, False], value=False)
                    is_cuda = gr.Radio(label="CUDA加速", choices=[True, False], value=False)
                run_button = gr.Button(value="运行")
            with gr.Column():
                video_output = gr.Video(label="视频输出")
        run_button.click(
            fn=handle, 
            inputs=[video_input, source_language, translate_type, target_language, model_name, subtitle_type, tts_type, voice_role, voice_autorate, is_separate, remove_noise, is_cuda], 
            outputs=[video_output]
        )
        tts_type.change(
            fn=lambda tts: gr.update(choices=edge_voice_roles if tts == 0 else cosy_voice_roles, value=(edge_voice_roles if tts == 0 else cosy_voice_roles)[0][1]),
            inputs=tts_type,
            outputs=voice_role
        )
        return demo

if __name__ == "__main__":
    demo = get_gradio_demo()
    demo.launch(share=True)
