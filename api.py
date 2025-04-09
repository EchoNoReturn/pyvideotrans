if __name__ == "__main__":
    import json
    import multiprocessing
    import random
    import re
    import os
    import shutil
    import threading
    import time
    import json
    import oss2
    import uuid

    from pathlib import Path
    from flask import Flask, request, jsonify, send_from_directory
    from flask_cors import CORS
    from waitress import serve
    from videotrans.configure import config
    from videotrans.task._dubbing import DubbingSrt
    from videotrans.task._speech2text import SpeechToText
    from videotrans.task._translate_srt import TranslateSrt
    from videotrans.task.job import start_thread
    from videotrans.task.trans_create import TransCreate
    from videotrans.util import tools
    from videotrans import tts as tts_model, translator, recognition
    from oss2.exceptions import OssError
    from datetime import datetime, timedelta
    from videotrans.util.http_request import http_request

    ####### 配置信息
    config.exec_mode = "api"

    # 设置根目录和默认主机、端口
    ROOT_DIR = config.ROOT_DIR
    # HOST = "127.0.0.1"
    # PORT = 9011
    HOST = "0.0.0.0"
    PORT = 8086

    # 读取 host.txt 设置主机和端口
    host_file = Path(ROOT_DIR + "/host.txt")
    if host_file.is_file():
        host_str = host_file.read_text(encoding="utf-8").strip()
        host_str = re.sub(r"https?://", "", host_str).split(":")

        if len(host_str) > 0:
            HOST = host_str[0]
        if len(host_str) == 2:
            PORT = int(host_str[1])

    # 存储生成的文件和进度日志
    API_RESOURCE = "apidata"
    TARGET_DIR = f"{ROOT_DIR}/{API_RESOURCE}"
    Path(TARGET_DIR).mkdir(parents=True, exist_ok=True)

    # 进度日志
    PROCESS_INFO = f"{TARGET_DIR}/processinfo"
    if Path(PROCESS_INFO).is_dir():
        shutil.rmtree(PROCESS_INFO)
    Path(PROCESS_INFO).mkdir(parents=True, exist_ok=True)

    # 任务结束状态
    END_STATUS_LIST = ["error", "succeed", "end", "stop"]
    # 日志状态
    LOGS_STATUS_LIST = ["logs"]

    # URL 前缀
    URL_PREFIX = f"http://{HOST}:{PORT}/{API_RESOURCE}"
    config.exit_soft = False

    # 创建 Flask 应用
    app = Flask(__name__, static_folder=TARGET_DIR)
    # 启用跨域资源共享
    CORS(app)

    # 读取 OSS 配置
    config_file = "_config.json"
    with open(config_file, "r") as file:
        config_json = json.load(file)

    # 提取 OSS 配置参数
    oss_config = config_json["oss"]
    access_key_id = oss_config["accessKeyId"]
    access_key_secret = oss_config["accessKeySecret"]
    bucket_name = oss_config["bucketName"]
    endpoint = oss_config["endpoint"]

    # 创建 OSS 认证对象
    auth = oss2.Auth(access_key_id, access_key_secret)
    bucket = oss2.Bucket(auth, endpoint, bucket_name)
    # 测试连接
    try:
        bucket.get_bucket_info()
        print(f"\n✅ 成功连接到 OSS，存储桶：{bucket_name}\n")
    except Exception as e:
        print("\n❌ 连接 OSS 失败:", str(e))

    ###### 接口分割线 ######

    # 第1个接口 /tts
    """
    根据字幕合成配音接口
    
    请求数据类型: Content-Type:application
    
    请求参数：
    
    name:必须参数，字符串类型，需要配音的srt字幕的绝对路径(需同本软件在同一设备)，或者直接传递合法的srt字幕格式内容
    tts_type:必须参数，数字类型，配音渠道，0="Edge-TTS",1='CosyVoice',2="ChatTTS",3=302.AI,4="FishTTS",5="Azure-TTS",
        6="GPT-SoVITS",7="clone-voice",8="OpenAI TTS",9="Elevenlabs.io",10="Google TTS",11="自定义TTS API"
    voice_role:必须参数，字符串类型，对应配音渠道的角色名，edge-tts/azure-tts/302.ai(azure模型)时目标语言不同，角色名也不同，具体见底部
    target_language:必须参数，字符串类型，需要配音的语言类型代码，即所传递的字幕文字语言代码，可选值 简体中文zh-cn，繁体zh-tw，英语en，法语fr，德语de，日语ja，韩语ko，俄语ru，西班牙语es，泰国语th，意大利语it，葡萄牙语pt，越南语vi，阿拉伯语ar，土耳其语tr，印地语hi，匈牙利语hu，乌克兰语uk，印尼语id，马来语ms，哈萨克语kk，捷克语cs，波兰语pl，荷兰语nl，瑞典语sv
    voice_rate:可选参数，字符串类型，语速加减值，格式为：加速`+数字%`，减速`-数字%`
    volume:可选参数，字符串类型，音量变化值(仅配音渠道为edge-tts生效)，格式为 增大音量`+数字%`，降低音量`-数字%`
    pitch:可选参数，字符串类型，音调变化值(仅配音渠道为edge-tts生效)，格式为 调大音调`+数字Hz`,降低音量`-数字Hz`
    out_ext:可选参数，字符串类型，输出配音文件类型，mp3|wav|flac|aac,默认wav
    voice_autorate:可选参数，布尔类型，默认False，是否自动加快语速，以便与字幕对齐
    
    返回数据：
    返回类型：json格式，
    成功时返回，可根据task_id通过 task_status 获取任务进度
    {"code":0,"msg":"ok","task_id":任务id}
    
    失败时返回
    {"code":1,"msg":"错误信息"}
    
    
    请求示例
    ```
    def test_tts():
        res=requests.post("http://127.0.0.1:9011/tts",json={
        "name":"C:/users/c1/videos/zh0.srt",
        "voice_role":"zh-CN-YunjianNeural",
        "target_language_code":"zh-cn",
        "voice_rate":"+0%",
        "volume":"+0%",
        "pitch":"+0Hz",
        "tts_type":"0",
        "out_ext":"mp3",
        "voice_autorate":True,
        })
        print(res.json())
    ```
    """
    @app.route("/tts", methods=["POST"])
    def tts():
        data = request.json
        # 从请求数据中获取参数
        name = data.get("name", "").strip()
        if not name:
            return jsonify(
                {"code": 1, "msg": "The parameter name is not allowed to be empty"}
            )
        is_srt = True
        if name.find("\n") == -1 and name.endswith(".srt"):
            if not Path(name).exists():
                return jsonify({"code": 1, "msg": f"The file {name} is not exist"})
        else:
            tmp_file = (
                    config.TEMP_DIR
                    + f"/tts-srt-{time.time()}-{random.randint(1, 9999)}.srt"
            )
            is_srt = tools.is_srt_string(name)
            Path(tmp_file).write_text(
                tools.process_text_to_srt_str(name) if not is_srt else name,
                encoding="utf-8",
            )
            name = tmp_file

        cfg = {
            "name": name,
            "voice_role": data.get("voice_role"),
            "target_language_code": data.get("target_language_code"),
            "tts_type": int(data.get("tts_type", 0)),
            "voice_rate": data.get("voice_rate", "+0%"),
            "volume": data.get("volume", "+0%"),
            "pitch": data.get("pitch", "+0Hz"),
            "out_ext": data.get("out_ext", "mp3"),
            "voice_autorate": (
                bool(data.get("voice_autorate", False)) if is_srt else False
            ),
        }
        is_allow_lang = tts_model.is_allow_lang(
            langcode=cfg["target_language_code"], tts_type=cfg["tts_type"]
        )
        if is_allow_lang is not True:
            return jsonify({"code": 4, "msg": is_allow_lang})
        is_input_api = tts_model.is_input_api(tts_type=cfg["tts_type"], return_str=True)
        if is_input_api is not True:
            return jsonify({"code": 5, "msg": is_input_api})

        obj = tools.format_video(name, None)
        obj["target_dir"] = TARGET_DIR + f'/{obj["uuid"]}'
        obj["cache_folder"] = config.TEMP_DIR + f'/{obj["uuid"]}'
        Path(obj["target_dir"]).mkdir(parents=True, exist_ok=True)
        cfg.update(obj)

        config.box_tts = "ing"
        trk = DubbingSrt(cfg)
        config.dubb_queue.append(trk)
        tools.set_process(
            text=f"Currently in queue No.{len(config.dubb_queue)}", uuid=obj["uuid"]
        )
        return jsonify({"code": 0, "task_id": obj["uuid"]})


    # 第2个接口 /translate_srt
    """
    字幕翻译接口
    
    请求参数:
    类型 Content-Type:application/json
    
    请求数据:
    name:必须参数，字符串类型，需要翻译的srt字幕的绝对路径(需同本软件在同一设备)，或者直接传递合法的srt字幕格式内容
    translate_type：必须参数，整数类型，翻译渠道
    target_language:必须参数，字符串类型，要翻译到的目标语言代码。可选值 简体中文zh-cn，繁体zh-tw，英语en，法语fr，德语de，日语ja，韩语ko，俄语ru，西班牙语es，泰国语th，意大利语it，葡萄牙语pt，越南语vi，阿拉伯语ar，土耳其语tr，印地语hi，匈牙利语hu，乌克兰语uk，印尼语id，马来语ms，哈萨克语kk，捷克语cs，波兰语pl，荷兰语nl，瑞典语sv
    source_code:可选参数，字符串类型，原始字幕语言代码，可选同上
    
    返回数据
    返回类型：json格式，
    成功时返回，可根据task_id通过 task_status 获取任务进度
    {"code":0,"msg":"ok","task_id":任务id}
    
    失败时返回
    {"code":1,"msg":"错误信息"}
    
    请求示例
    ```
    def test_translate_srt():
        res=requests.post("http://127.0.0.1:9011/translate_srt",json={
        "name":"C:/users/c1/videos/zh0.srt",
        "target_language":"en",
        "translate_type":0
        })
        print(res.json())
    ```
    
    """
    @app.route("/translate_srt", methods=["POST"])
    def translate_srt():
        data = request.json
        # 从请求数据中获取参数
        name = data.get("name", "").strip()
        if not name:
            return jsonify(
                {"code": 1, "msg": "The parameter name is not allowed to be empty"}
            )
        is_srt = True
        if name.find("\n") == -1 and name.endswith(".srt"):
            if not Path(name).exists():
                return jsonify({"code": 1, "msg": f"The file {name} is not exist"})
        else:
            tmp_file = (
                    config.TEMP_DIR
                    + f"/trans-srt-{time.time()}-{random.randint(1, 9999)}.srt"
            )
            is_srt = tools.is_srt_string(name)
            Path(tmp_file).write_text(
                tools.process_text_to_srt_str(name) if not is_srt else name,
                encoding="utf-8",
            )
            name = tmp_file

        cfg = {
            "translate_type": int(data.get("translate_type", 0)),
            "text_list": tools.get_subtitle_from_srt(name),
            "target_code": data.get("target_language"),
            "source_code": data.get("source_code", ""),
        }
        is_allow = translator.is_allow_translate(
            translate_type=cfg["translate_type"],
            show_target=cfg["target_code"],
            return_str=True,
        )
        if is_allow is not True:
            return jsonify({"code": 5, "msg": is_allow})
        obj = tools.format_video(name, None)
        obj["target_dir"] = TARGET_DIR + f'/{obj["uuid"]}'
        obj["cache_folder"] = config.TEMP_DIR + f'/{obj["uuid"]}'
        Path(obj["target_dir"]).mkdir(parents=True, exist_ok=True)
        cfg.update(obj)

        config.box_trans = "ing"
        trk = TranslateSrt(cfg)
        config.trans_queue.append(trk)
        tools.set_process(
            text=f"Currently in queue No.{len(config.trans_queue)}", uuid=obj["uuid"]
        )
        return jsonify({"code": 0, "task_id": obj["uuid"]})


    # 第3个接口 /recogn
    """
    语音识别、音视频转字幕接口
    
    请求参数:
    类型 Content-Type:application/json
    
    请求数据:
    name:必须参数，字符串类型，需要翻译的音频或视频的绝对路径(需同本软件在同一设备)
    recogn_type:必须参数，数字类型，语音识别模式，0=faster-whisper本地模型识别，1=openai-whisper本地模型识别，2=Google识别api，3=zh_recogn中文识别，4=豆包模型识别，5=自定义识别API，6=OpenAI识别API
    model_name:必须参数faster-whisper和openai-whisper模式时的模型名字
    detect_language:必须参数，字符串类型，音视频中人类说话语言。中文zh，英语en，法语fr，德语de，日语ja，韩语ko，俄语ru，西班牙语es，泰国语th，意大利语it，葡萄牙语pt，越南语vi，阿拉伯语ar，土耳其语tr，印地语hi，匈牙利语hu，乌克兰语uk，印尼语id，马来语ms，哈萨克语kk，捷克语cs，波兰语pl，荷兰语nl，瑞典语sv
    split_type：可选参数，字符串类型，默认all：整体识别，可选avg：均等分割
    is_cuda:可选参数，布尔类型，是否启用CUDA加速，默认False
    
    返回数据
    返回类型：json格式，
    成功时返回，可根据task_id通过 task_status 获取任务进度
    {"code":0,"msg":"ok","task_id":任务id}
    
    失败时返回
    {"code":1,"msg":"错误信息"}
    
    示例
    def test_recogn():
        res=requests.post("http://127.0.0.1:9011/recogn",json={
        "name":"C:/Users/c1/Videos/10ass.mp4",
        "recogn_type":0,
        "split_type":"all",
        "model_name":"tiny",
        "is_cuda":False,
        "detect_language":"zh",
        })
        print(res.json())
    
    """
    @app.route("/recogn", methods=["POST"])
    def recogn():
        data = request.json
        # 从请求数据中获取参数
        name = data.get("name", "").strip()
        if not name:
            return jsonify(
                {"code": 1, "msg": "The parameter name is not allowed to be empty"}
            )
        if not Path(name).is_file():
            return jsonify({"code": 1, "msg": f"The file {name} is not exist"})

        cfg = {
            "recogn_type": int(data.get("recogn_type", 0)),
            "split_type": data.get("split_type", "all"),
            "model_name": data.get("model_name", "tiny"),
            "is_cuda": bool(data.get("is_cuda", False)),
            "detect_language": data.get("detect_language", ""),
        }

        is_allow = recognition.is_allow_lang(
            langcode=cfg["detect_language"], recogn_type=cfg["recogn_type"]
        )
        if is_allow is not True:
            return jsonify({"code": 5, "msg": is_allow})

        is_input = recognition.is_input_api(
            recogn_type=cfg["recogn_type"], return_str=True
        )
        if is_input is not True:
            return jsonify({"code": 5, "msg": is_input})

        obj = tools.format_video(name, None)
        obj["target_dir"] = TARGET_DIR + f'/{obj["uuid"]}'
        obj["cache_folder"] = config.TEMP_DIR + f'/{obj["uuid"]}'
        Path(obj["target_dir"]).mkdir(parents=True, exist_ok=True)
        cfg.update(obj)
        config.box_recogn = "ing"
        trk = SpeechToText(cfg)
        config.prepare_queue.append(trk)
        tools.set_process(
            text=f"Currently in queue No.{len(config.prepare_queue)}", uuid=obj["uuid"]
        )
        return jsonify({"code": 0, "task_id": obj["uuid"]})


    # 第4个接口
    """
    视频完整翻译接口
    
    
    请求参数:
    类型 Content-Type:application/json
    
    请求数据:
    name:必须参数，字符串类型，需要翻译的音频或视频的绝对路径(需同本软件在同一设备)
    recogn_type:必须参数，数字类型，语音识别模式，0=faster-whisper本地模型识别，1=openai-whisper本地模型识别，2=Google识别api，3=zh_recogn中文识别，4=豆包模型识别，5=自定义识别API，6=OpenAI识别API
    model_name:必须参数faster-whisper和openai-whisper模式时的模型名字
    split_type：可选参数，字符串类型，默认all：整体识别，可选avg：均等分割
    is_cuda:可选参数，布尔类型，是否启用CUDA加速，默认False
    translate_type：必须参数，整数类型，翻译渠道
    target_language:必须参数，字符串类型，要翻译到的目标语言代码。可选值 简体中文zh-cn，繁体zh-tw，英语en，法语fr，德语de，日语ja，韩语ko，俄语ru，西班牙语es，泰国语th，意大利语it，葡萄牙语pt，越南语vi，阿拉伯语ar，土耳其语tr，印地语hi，匈牙利语hu，乌克兰语uk，印尼语id，马来语ms，哈萨克语kk，捷克语cs，波兰语pl，荷兰语nl，瑞典语sv
    source_language:可选参数，字符串类型，原始字幕语言代码，可选同上
    tts_type:必须参数，数字类型，配音渠道，0="Edge-TTS",1='CosyVoice',2="ChatTTS",3=302.AI,4="FishTTS",5="Azure-TTS",
        6="GPT-SoVITS",7="clone-voice",8="OpenAI TTS",9="Elevenlabs.io",10="Google TTS",11="自定义TTS API"
    voice_role:必须参数，字符串类型，对应配音渠道的角色名，edge-tts/azure-tts/302.ai(azure模型)时目标语言不同，角色名也不同，具体见底部
    voice_rate:可选参数，字符串类型，语速加减值，格式为：加速`+数字%`，减速`-数字%`
    volume:可选参数，字符串类型，音量变化值(仅配音渠道为edge-tts生效)，格式为 增大音量`+数字%`，降低音量`-数字%`
    pitch:可选参数，字符串类型，音调变化值(仅配音渠道为edge-tts生效)，格式为 调大音调`+数字Hz`,降低音量`-数字Hz`
    out_ext:可选参数，字符串类型，输出配音文件类型，mp3|wav|flac|aac,默认wav
    voice_autorate:可选参数，布尔类型，默认False，是否自动加快语速，以便与字幕对齐
    subtitle_type:可选参数，整数类型，默认0，字幕嵌入类型，0=不嵌入字幕，1=嵌入硬字幕，2=嵌入软字幕，3=嵌入双硬字幕，4=嵌入双软字幕
    append_video：可选参数，布尔类型，默认False，如果配音后音频时长大于视频，是否延长视频末尾
    only_video:可选参数，布尔类型，默认False，是否只生成视频文件，不生成字幕音频等
    
    返回数据
    返回类型：json格式，
    成功时返回，可根据task_id通过 task_status 获取任务进度
    {"code":0,"msg":"ok","task_id":任务id}
    
    失败时返回
    {"code":1,"msg":"错误信息"}
    
    示例
    def test_trans_video():
        res=requests.post("http://127.0.0.1:9011/trans_video",json={
        "name":"C:/Users/c1/Videos/10ass.mp4",
    
        "recogn_type":0,
        "split_type":"all",
        "model_name":"tiny",
    
        "translate_type":0,
        "source_language":"zh-cn",
        "target_language":"en",
    
        "tts_type":0,
        "voice_role":"zh-CN-YunjianNeural",
        "voice_rate":"+0%",
        "volume":"+0%",
        "pitch":"+0Hz",
        "voice_autorate":True,
        "video_autorate":True,
    
        "is_separate":False,
        "back_audio":"",
        
        "subtitle_type":1,
        "append_video":False,
    
        "is_cuda":False,
        })
        print(res.json())
    
    """
    @app.route("/trans_video", methods=["POST"])
    def trans_video():
        data = json.loads(request.json) if type(request.json) == str else request.json
        name = data.get("name", "")
        if not name:
            name = _download_file(
                data.get("object_key"), os.path.join(config.TEMP_DIR,"video_input_cache")
            )
            if not name:
                return jsonify(
                    {"code": 1, "msg": "The parameter name is not allowed to be empty"}
                )
        if not Path(name).exists():
            return jsonify({"code": 1, "msg": f"The file {name} is not exist"})

        cfg = {
            # 通用
            "name": name,
            "oss_key":  data.get("object_key", None),
            "is_separate": bool(data.get("is_separate", False)),
            "back_audio": data.get("back_audio", ""),
            "hashCode": data.get("hashCode"),
            # 识别
            "recogn_type": 0,
            "split_type": data.get("split_type", "all"),
            "model_name": "large-v3-turbo",     # options: tiny/medium/large-v3/large-v3-turbo
            "cuda": bool(data.get("is_cuda", False)),
            "subtitles": data.get("subtitles", ""),
            # 翻译
            "translate_type": int(data.get("translate_type", 21)), # 21 ==> 智谱AI翻译
            "target_language": data.get("target_language"),
            "source_language": data.get("source_language"),
            # 配音
            "tts_type": 1,
            "voice_role": data.get("voice_role", "clone"),# clone-single
            "refer_audio": data.get("refer_audio", ""),# 参考音频oss
            "refer_text": data.get("refer_text", ""),# 参考文本
            "voice_rate": data.get("voice_rate", "+0%"),
            "voice_autorate": bool(data.get("voice_autorate", True)),
            "video_autorate": bool(data.get("video_autorate", False)),
            "volume": data.get("volume", "+0%"),
            "pitch": data.get("pitch", "+0Hz"),
            "subtitle_type": int(data.get("subtitle_type", 0)),
            "append_video": bool(data.get("append_video", False)),
            "is_batch": True,
            "app_mode": "biaozhun",
            "only_video": bool(data.get("only_video", False)),
            # 存储桶
            "bucket": bucket,
        }

        # 自定义音色
        if cfg["voice_role"] == "clone-single" and cfg["refer_audio"] and cfg["voice_rate"]:
            cfg["refer_audio"] = bucket.sign_url("GET", cfg["refer_audio"], 3600)

        # 语音识别验证
        if not cfg["subtitles"]:
            is_allow = recognition.is_allow_lang(
                langcode=cfg["target_language"], recogn_type=cfg["recogn_type"]
            )
            if is_allow is not True:
                return jsonify({"code": 5, "msg": is_allow})
            is_input = recognition.is_input_api(
                recogn_type=cfg["recogn_type"], return_str=True
            )
            if is_input is not True:
                return jsonify({"code": 5, "msg": is_input})

        # 翻译验证
        if cfg["source_language"] != cfg["target_language"]:
            is_allow = translator.is_allow_translate(
                translate_type=cfg["translate_type"],
                show_target=cfg["target_language"],
                return_str=True,
            )
            if is_allow is not True:
                return jsonify({"code": 5, "msg": is_allow})

        # 配音验证
        if (
                cfg["voice_role"]
                and cfg["voice_role"].strip().lower() != "No"
                and cfg["target_language"]
        ):
            is_allow_lang = tts_model.is_allow_lang(
                langcode=cfg["target_language"], tts_type=cfg["tts_type"]
            )
            if is_allow_lang is not True:
                return jsonify({"code": 4, "msg": is_allow_lang})
            is_input_api = tts_model.is_input_api(
                tts_type=cfg["tts_type"], return_str=True
            )
            if is_input_api is not True:
                return jsonify({"code": 5, "msg": is_input_api})

        obj = tools.format_video(name, None)
        obj["target_dir"] = TARGET_DIR + f'/{obj["uuid"]}'
        obj["cache_folder"] = config.TEMP_DIR + f'/{obj["uuid"]}'
        Path(obj["target_dir"]).mkdir(parents=True, exist_ok=True)
        cfg.update(obj)
        
        # 获取用户id
        endpoint = f"/vid/video/getMemberId?name={data.get('memberId',None)}"
        headers = {"Content-Type": "application/json"}
        respone = http_request.send_request(endpoint=endpoint,headers=headers)
        cfg["record_id"] = respone["msg"]
        if(respone["code"] != 0):
            return jsonify({"code" : 1, "msg":"用户信息获取出错"})
        else:
            cfg['memberId'] = respone["msg"]
        # 入库
        endpoint = "/vid/video/copyModify"
        headers = {
            "Content-Type": "application/json",
        }
        video_data = {
            "processStatus" : "VIDEO_STATUS_PROCEED",
            "souLanguage": cfg["source_language"],
            "tarLanguage": cfg["target_language"],
            "hashCode": cfg["hashCode"],
            "uploadTime": data.get("uploadTime", int(time.time() * 1000)),
            "ossVideoKey":  data.get("object_key"),
            "taskId": obj["uuid"],
            "memberId":  cfg['memberId'],
        }
        respone = http_request.send_request(endpoint=endpoint,body=video_data,headers=headers)
        cfg["record_id"] = respone["msg"]
        if(respone["code"] != 0):
            return jsonify({"code" : 1, "msg":"视频信息记录出错"})
        
        config.current_status = "ing"
        trk = TransCreate(cfg)
        config.prepare_queue.append(trk)
        tools.set_process(
            text=f"Currently in queue No.{len(config.prepare_queue)}", uuid=obj["uuid"]
        )                                              
        return jsonify({"code": 0, "task_id": obj["uuid"],"id":cfg["record_id"]})


    # 获取任务进度接口
    """
    根据任务id，获取当前任务的状态
    
    请求数据类型：优先GET中获取，不存在则从POST中获取，都不存在则从 json数据中获取
    
    请求参数: 
    task_id:必须，字符串类型
    
    返回:json格式数据
    code:-1=进行中，0=成功结束，>0=出错了
    msg:code为-1时为进度信息，code>0时为出错信息，成功时为ok
    data:仅当code==0成功时存在，是一个dict对象
        absolute_path是生成的文件列表list，每项均是一个文件的绝对路径
        url 是生成的文件列表list，每项均是一个可访问的url
    
    
    失败：{"code":1,"msg":"不存在该任务"}
    进行中：{"code":-1,"msg":"正在合成声音"} 
    成功: {"code":0,"msg":"ok","data":{"absolute_path":["/data/1.srt","/data/1.mp4"],"url":["http://127.0.0.1:9011/task_id/1.srt"]}}
    
    
    示例
    def test_task_status():
        res=requests.post("http://127.0.0.1:9011/task_status",json={
            "task_id":"06c238d250f0b51248563c405f1d7294"
        })
        print(res.json())
    
    {
      "code": 0,
      "data": {
        "absolute_path": [
          "F:/python/pyvideo/apidata/daa33fee2537b47a0b12e12b926a4b01/10ass.mp4",
          "F:/python/pyvideo/apidata/daa33fee2537b47a0b12e12b926a4b01/en.m4a",
          "F:/python/pyvideo/apidata/daa33fee2537b47a0b12e12b926a4b01/en.srt",
          "F:/python/pyvideo/apidata/daa33fee2537b47a0b12e12b926a4b01/end.srt.ass",
          "F:/python/pyvideo/apidata/daa33fee2537b47a0b12e12b926a4b01/zh-cn.m4a",
          "F:/python/pyvideo/apidata/daa33fee2537b47a0b12e12b926a4b01/zh-cn.srt",
          "F:/python/pyvideo/apidata/daa33fee2537b47a0b12e12b926a4b01/文件说明.txt"
        ],
        "url": [
          "http://127.0.0.1:9011/apidata/daa33fee2537b47a0b12e12b926a4b01/10ass.mp4",
          "http://127.0.0.1:9011/apidata/daa33fee2537b47a0b12e12b926a4b01/en.m4a",
          "http://127.0.0.1:9011/apidata/daa33fee2537b47a0b12e12b926a4b01/en.srt",
          "http://127.0.0.1:9011/apidata/daa33fee2537b47a0b12e12b926a4b01/end.srt.ass",
          "http://127.0.0.1:9011/apidata/daa33fee2537b47a0b12e12b926a4b01/zh-cn.m4a",
          "http://127.0.0.1:9011/apidata/daa33fee2537b47a0b12e12b926a4b01/zh-cn.srt",
          "http://127.0.0.1:9011/apidata/daa33fee2537b47a0b12e12b926a4b01/文件说明.txt"
        ]
      },
      "msg": "ok"
    }
    """
    @app.route("/task_status", methods=["POST", "GET"])
    def task_status():
        # 1. 优先从 GET 请求参数中获取 task_id
        task_id = request.args.get("task_id")
        id = request.args.get("id")
        # 2. 如果 GET 参数中没有 task_id，再从 POST 表单中获取
        if task_id is None:
            task_id = request.form.get("task_id")
        # 3. 如果 POST 表单中也没有 task_id，再从 JSON 请求体中获取
        if task_id is None and request.is_json:
            task_id = request.json.get("task_id")
        if not task_id:
            return jsonify({"code": 1, "msg": "The parem  task_id is not set"})
        return _get_task_data(task_id,id)


    # 获取多个任务 前台 content-type:application/json, 数据 {task_id_list:[id1,id2,....]}
    @app.route("/task_status_list", methods=["POST", "GET"])
    def task_status_list():
        # 1. 优先从 GET 请求参数中获取 task_id
        task_ids = request.json.get("task_id_list", [])
        if not task_ids or len(task_ids) < 1:
            return jsonify({"code": 1, "msg": "缺少任务id"})

        return_data = {}
        for task_id in task_ids:
            return_data[task_id] = _get_task_data(task_id)
        return jsonify({"code": 0, "msg": "ok", "data": return_data})

    # 获取翻译信息
    # @app.route("/task_id", methods=[ "GET"])
    def get_translator(task_id="", id="",no_response=False):
            if not task_id:
                return ""
                # task_id = request.args.get("task_id")
            # task_id = request.args.get("taskid")
            import os
            import json
            from pathlib import Path
            current_file = os.path.abspath(__file__)
            project_root = os.path.dirname(current_file)
            file_path = os.path.join(project_root, "apidata", task_id)
            file_name = task_id+".json"
            path = Path(file_path)/file_name
            if not path.exists():
                if no_response:
                    # print(f"文件不存在：{path}")
                    return ""
                # return jsonify({"code": 1, "msg": None})
                return ""
            with open(path, 'r', encoding='utf-8') as f:
                data = json.loads(f.read())
                if data['is_save'] == False:
                    if data['is_ok']:
                        endpoint = f"/vid/video/saveTranslateContent"
                        headers = {"Content-Type": "application/json"}
                        body = {
                            "id":id,
                            "translateContent":data['text']
                        }
                        respone = http_request.send_request(endpoint=endpoint,body=body,headers=headers)
                        if respone.get('code') != 0:
                            raise Exception("识别和翻译内容保存失败")
                        # print("======= 保存成功 ========")
                        data['is_save'] = True
                        with open(Path(path),'w',encoding='utf-8') as f:
                            json.dump(data,f,ensure_ascii=False,indent=4)
                return data['text']


    # 获取文件上传地址
    @app.route("/get_upload_url", methods=["POST"])
    def get_upload_url():
        try:
            file_name = request.json.get("fileName")
            if not file_name:
                return jsonify({"code": 1, "msg": "The file name does not exist"})
            content_type = request.json.get("contentType")
            content_type = content_type if content_type else "application/octet-stream"

            # 获取文件扩展名
            _, file_ext = os.path.splitext(file_name)
            # 生成唯一文件名
            object_key = str(uuid.uuid4())
            # 生成预签名URL，有效期30分钟
            headers = {"Content-Type": content_type, "x-oss-meta-file-ext": file_ext}
            url = bucket.sign_url("PUT", object_key, 30 * 60, headers=headers)
            return jsonify(
                {
                    "code": 0,
                    "uploadUrl": url,
                    "objectKey": object_key,
                    "Content-Type": content_type,
                    "x-oss-meta-file-ext": file_ext,
                }
            )
        except Exception as e:
            return jsonify({"code": 1, "msg": str(e)})

    # 下载文件
    def _download_file(object_key, path):
        try:
            meta = bucket.head_object(object_key)
            # 读取存储的文件后缀
            file_ext = meta.headers.get("x-oss-meta-file-ext", "")
            print(f"file_ext:{file_ext}")
            # 生成完整的文件路径
            if os.path.isdir(path):
                file_path = os.path.join(path, object_key + file_ext)
            else:
                file_path = path + file_ext
            # 确保目标目录存在
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            print(f"file_path:{file_path}")
            # 下载文件
            bucket.get_object_to_file(object_key, file_path)
            return file_path
        except Exception as e:
            print(e)
            return None
    
    def _cobine_subtitle_translation_content(origin_msg, stc):
        return f"""
=== 执行状态信息 ===
{origin_msg}
=== 识别和翻译内容 ===
{stc}
===========
        """

    def _get_task_data(task_id,id):
        stc = get_translator(task_id = task_id,id = id, no_response=True)
        # print(f"stc:{str(stc)}")
                
        file = PROCESS_INFO + f"/{task_id}.json"
        if not Path(file).is_file():
            if task_id in config.uuid_logs_queue:
                msg = _cobine_subtitle_translation_content(_get_order(task_id), stc)
                return {"code": -1, "msg": msg}
            return {"code": 1, "msg": f"该任务 {task_id} 不存在"}

        try:
            data = json.loads(Path(file).read_text(encoding="utf-8"))
        except Exception as e:
            msg = _cobine_subtitle_translation_content(Path(file).read_text(encoding="utf-8"), stc)
            return {"code": -1, "msg": msg}

        if data["type"] == "error":
            msg = _cobine_subtitle_translation_content(data["text"], stc)
            return {"code": 3, "msg": msg}
        if data["type"] in LOGS_STATUS_LIST:
            text = data.get("text", "").strip()
            msg = text if text else "等待处理中"
            res_msg = _cobine_subtitle_translation_content(msg, stc)
            return {"code": -1, "msg": res_msg}
        # 完成，输出所有文件
        file_list = _get_files_in_directory(f"{TARGET_DIR}/{task_id}")
        if len(file_list) < 1:
            tip = "未生成任何结果文件，可能出错了"
            return {"code": 4, "msg": _cobine_subtitle_translation_content(tip, stc)}

        absolute_path = [f"{TARGET_DIR}/{task_id}/{name}" for name in file_list]
        url = [
            f"{request.scheme}://{request.host}/{API_RESOURCE}/{task_id}/{name}"
            for name in file_list
        ]

        # 生成签名 URL
        endpoint = f"/vid/video/targetVideo?id={id}"
        headers = {"Content-Type": "application/json"}
        signed_url = None
        retry_count = 6  # 最多轮询 10 次
        retry_interval = 3  # 每次轮询间隔 1 秒

        for attempt in range(retry_count):
            respone = http_request.send_request(endpoint=endpoint, headers=headers)
            if respone["code"] == 0 and respone["msg"]:
                try:
                    signed_url = bucket.sign_url("GET", respone["msg"], 3600)
                    break  # 成功生成签名 URL，退出轮询
                except oss2.exceptions.ClientError as e:
                    print(f"OSS ClientError: {e}")
                    signed_url = None
            else:
                print(f"轮询尝试 {attempt + 1}/{retry_count} 失败，响应码: {respone['code']}")
                time.sleep(retry_interval)

        if signed_url is None:
            raise Exception("无法生成签名 URL，请检查网络或配置")
        res = {
            "code": 0,
            "msg": _cobine_subtitle_translation_content("ok", stc),
            "data": {
                "absolute_path": absolute_path,
                "url": url,
                "signed_url": signed_url,
                "file_ext":".mp4",
            },
        }
        return res

    def _get_order(task_id):
        order_num = 0
        for it in config.prepare_queue:
            order_num += 1
            if it.uuid == task_id:
                return (
                    f"当前处于预处理队列第{order_num}位"
                    if config.defaulelang == "zh"
                    else f"No.{order_num} on perpare queue"
                )

        order_num = 0
        for it in config.regcon_queue:
            order_num += 1
            if it.uuid == task_id:
                return (
                    f"当前处于语音识别队列第{order_num}位"
                    if config.defaulelang == "zh"
                    else f"No.{order_num} on perpare queue"
                )
        order_num = 0
        for it in config.trans_queue:
            order_num += 1
            if it.uuid == task_id:
                return (
                    f"当前处于字幕翻译队列第{order_num}位"
                    if config.defaulelang == "zh"
                    else f"No.{order_num} on perpare queue"
                )
        order_num = 0
        for it in config.dubb_queue:
            order_num += 1
            if it.uuid == task_id:
                return (
                    f"当前处于配音队列第{order_num}位"
                    if config.defaulelang == "zh"
                    else f"No.{order_num} on perpare queue"
                )
        order_num = 0
        for it in config.align_queue:
            order_num += 1
            if it.uuid == task_id:
                return (
                    f"当前处于声画对齐队列第{order_num}位"
                    if config.defaulelang == "zh"
                    else f"No.{order_num} on perpare queue"
                )
        order_num = 0
        for it in config.assemb_queue:
            order_num += 1
            if it.uuid == task_id:
                return (
                    f"当前处于输出整理队列第{order_num}位"
                    if config.defaulelang == "zh"
                    else f"No.{order_num} on perpare queue"
                )
        return (
            "正在排队等待执行中，请稍后"
            if config.defaulelang == "zh"
            else f"Waiting in queue"
        )

    def _get_files_in_directory(dirname):
        """
        使用 pathlib 库获取指定目录下的所有文件名，并返回一个文件名列表。

        参数:
        dirname (str): 要获取文件的目录路径

        返回:
        list: 包含目录中所有文件名的列表
        """
        try:
            # 使用 Path 对象获取目录中的所有文件
            path = Path(dirname)
            files = [f.name for f in path.iterdir() if f.is_file()]
            return files
        except Exception as e:
            print(f"Error while accessing directory {dirname}: {e}")
            return []

    def _listen_queue():
        # 监听队列日志 uuid_logs_queue 不在停止中的 stoped_uuid_set
        Path(TARGET_DIR + f"/processinfo").mkdir(parents=True, exist_ok=True)
        while 1:
            # 找出未停止的
            uuid_list = list(config.uuid_logs_queue.keys())
            uuid_list = [
                uuid for uuid in uuid_list if uuid not in config.stoped_uuid_set
            ]
            # 全部结束
            if len(uuid_list) < 1:
                time.sleep(1)
                continue
            while len(uuid_list) > 0:
                uuid = uuid_list.pop(0)
                if uuid in config.stoped_uuid_set:
                    continue
                try:
                    q = config.uuid_logs_queue.get(uuid)
                    if not q:
                        continue
                    data = q.get(block=False)
                    if not data:
                        continue

                    if data["type"] not in END_STATUS_LIST + LOGS_STATUS_LIST:
                        continue
                    with open(
                            PROCESS_INFO + f"/{uuid}.json", "w", encoding="utf-8"
                    ) as f:
                        f.write(json.dumps(data))
                    if data["type"] in END_STATUS_LIST:
                        config.stoped_uuid_set.add(uuid)
                        del config.uuid_logs_queue[uuid]
                except Exception:
                    pass
            time.sleep(0.1)


    # Windows 上需要这个来避免子进程的递归执行问题
    multiprocessing.freeze_support()
    print(f"✅ Starting... API URL is   http://{HOST}:{PORT}\n")
    start_thread()
    threading.Thread(target=_listen_queue).start()
    try:
        serve(app, host=HOST, port=int(PORT))
    except Exception as e:
        import traceback

        traceback.print_exc()
