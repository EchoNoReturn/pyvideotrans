import copy
import json
import math
import os
import re
import shutil
import textwrap
import threading
import time
import uuid
from fileHash import calculate_file_hash
from typing import Dict
from pydub import AudioSegment
from pathlib import Path
import datetime
from flashtext import KeywordProcessor

# from videotrans.task._m4a_to_wav import convert_m4a_to_wav
from videotrans import translator
from videotrans.configure import config
from videotrans.recognition import run as run_recogn, Faster_Whisper_XXL
from videotrans.translator import run as run_trans, get_audio_code
from videotrans.tts import (
    run as run_tts,
    CLONE_VOICE_TTS,
    COSYVOICE_TTS,
    F5_TTS,
    EDGE_TTS,
    AZURE_TTS,
    ELEVENLABS_TTS,
    SPARK_TTS,
    INDEX_TTS,
)
from videotrans.util import tools
from ._base import BaseTask
from ._rate import SpeedRate
from ._remove_noise import remove_noise
from videotrans.util.http_request import http_request


class TransCreate(BaseTask):
    # （0）初始化配置和对象
    def __init__(self, cfg: Dict = None, obj: Dict = None):
        cfg_default = {
            "cache_folder": None,
            "target_dir": None,
            "remove_noise": True,
            "detect_language": None,
            "subtitle_language": None,
            "source_language_code": None,
            "target_language_code": None,
            "source_sub": None,
            "target_sub": None,
            "source_wav": "",
            "custom_ref_wav": "",
            "source_wav_output": "",
            "target_wav": "",
            "target_wav_output": "",
            "novoice_mp4": None,
            "targetdir_mp4": None,
            "instrument": None,
            "vocal": None,
            "shibie_audio": None,
            "background_music": None,
            "app_mode": "biaozhun",
            "subtitle_type": 0,
            "append_video": False,
            "only_video": False,
            "volume": "+0%",
            "pitch": "+0Hz",
            "voice_rate": "+0%",
        }
        cfg_default.update(cfg)
        super().__init__(cfg_default, obj)
        # 记录开始时间
        endpoint = "/py/video/modify"
        headers = {
            "Content-Type": "application/json",
        }
        video_data = {
            "id": self.cfg["record_id"],
            "procStartTime": int(time.time() * 1000),
        }
        response = http_request.send_request(
            endpoint=endpoint, body=video_data, headers=headers
        )
        if response["code"] != 0:
            print("视频信息记录出错")

        if "app_mode" not in self.cfg:
            self.cfg["app_mode"] = "biaozhun"
        # 存放原始语言字幕
        self.source_srt_list = []
        # 存放目标语言字幕
        self.target_srt_list = []

        # 原始视频时长  在慢速处理合并后，时长更新至此
        self.video_time = 0
        # 存储视频信息
        # 视频信息
        """
        result={
            "video_fps":0,
            "video_codec_name":"h264",
            "audio_codec_name":"aac",
            "width":0,
            "height":0,
            "time":0
        }
        """
        self.ignore_align = False
        self.video_info = None
        # 如果输入编码和输出编码一致，只需copy视频流，无需编码，除非嵌入硬字幕
        self.is_copy_video = False
        # 需要输出的视频编码选择，使用 h.264或h.265 : int   264 | 265
        self.video_codec_num = int(config.settings["video_codec"])
        # 存在添加的背景音乐
        if tools.vail_file(self.cfg["back_audio"]):
            self.cfg["background_music"] = Path(self.cfg["back_audio"]).as_posix()

        # 如果不是仅提取，则获取视频信息
        if self.cfg["app_mode"] not in ["tiqu"]:
            # 获取视频信息
            try:
                self._signal(
                    text=(
                        "分析视频数据，用时可能较久请稍等.."
                        if config.defaulelang == "zh"
                        else "Hold on a monment"
                    )
                )
                self.video_info = tools.get_video_info(self.cfg["name"])
                self.video_time = self.video_info["time"]
            except Exception as e:
                raise Exception(f"{config.transobj['get video_info error']}:{str(e)}")

            if not self.video_info:
                raise Exception(config.transobj["get video_info error"])
            vcodec_name = "h264" if self.video_codec_num == 264 else "hevc"
            # 如果获得原始视频编码格式同需要输出编码格式一致，设 is_copy_video=True
            if (
                self.video_info["video_codec_name"] == vcodec_name
                and self.video_info["color"] == "yuv420p"
            ):
                self.is_copy_video = True

        # 临时文件夹
        if "cache_folder" not in self.cfg or not self.cfg["cache_folder"]:
            self.cfg["cache_folder"] = f"{config.TEMP_DIR}/{self.uuid}"
        if "target_dir" not in self.cfg or not self.cfg["target_dir"]:
            self.cfg["target_dir"] = Path(self.cfg["target_dir"]).as_posix()
        # 创建文件夹
        Path(self.cfg["target_dir"]).mkdir(parents=True, exist_ok=True)
        Path(self.cfg["cache_folder"]).mkdir(parents=True, exist_ok=True)
        # 存放分离后的无声音mp4
        self.cfg["novoice_mp4"] = f"{self.cfg['cache_folder']}/novoice.mp4"

        self.set_source_language(self.cfg["source_language"], is_del=True)

        # 用于记录每个阶段的执行时间
        self.execution_times = {}

        # 如果配音角色不是No 并且不存在目标音频，则需要配音
        if (
            self.cfg["voice_role"]
            and self.cfg["voice_role"] not in ["No", "", " "]
            and self.cfg["target_language"] not in ["No", "-"]
        ):
            self.shoud_dubbing = True

        # 如果不是tiqu，则均需要合并
        if self.cfg["app_mode"] != "tiqu" and (
            self.shoud_dubbing or self.cfg["subtitle_type"] > 0
        ):
            self.shoud_hebing = True

        # 最终需要输出的mp4视频
        self.cfg["targetdir_mp4"] = (
            f"{self.cfg['target_dir']}/{self.cfg['noextname']}.mp4"
        )
        self._unlink_size0(self.cfg["targetdir_mp4"])

        # 是否需要背景音分离：分离出的原始音频文件
        if self.cfg["is_separate"]:
            # 背景音乐
            self.cfg["instrument"] = f"{self.cfg['cache_folder']}/instrument.wav"
            # 转为8k采样率，降低文件
            self.cfg["vocal"] = f"{self.cfg['cache_folder']}/vocal.wav"
            self.shoud_separate = True
            self._unlink_size0(self.cfg["instrument"])
            self._unlink_size0(self.cfg["vocal"])

        # 如果存在字幕，则视为原始语言字幕，不再识别
        if "subtitles" in self.cfg and self.cfg["subtitles"].strip():
            # 如果不存在目标语言，则视为原始语言字幕
            sub_file = self.cfg["source_sub"]
            with open(sub_file, "w", encoding="utf-8", errors="ignore") as f:
                txt = re.sub(
                    r":\d+\.\d+",
                    lambda m: m.group().replace(".", ","),
                    self.cfg["subtitles"].strip(),
                    re.S | re.M,
                )
                f.write(txt)
            self.shoud_recogn = False
        config.logger.info(f"{self.cfg=}")
        # 获取set.ini配置
        config.settings = config.parse_init()
        # 禁止修改字幕
        self._signal(text="forbid", type="disabled_edit")

        # 开启一个线程读秒
        def runing():
            t = 0
            while not self.hasend:
                if self._exit():
                    return
                time.sleep(2)
                t += 2
                self._signal(
                    text=f"{self.status_text} {t}s???{self.precent}",
                    type="set_precent",
                    nologs=True,
                )

        threading.Thread(target=runing).start()

    # ====================== 关键步骤 ====================== #

    # （1）开始预处理
    def prepare(self) -> None:
        try:
            self._saveStatus(self.cfg["record_id"], "VIDEO_STATUS_PROCEED_PRETREATMENT")
            self._start_timer("预处理阶段")
            if self._exit():
                return
            # 将原始视频分离为无声视频和音频
            self._split_wav_novicemp4()
            # 记录原视频信息
            self.cfg["origin_video_data"] = self._get_video_data(self.cfg["name"])
            self._end_timer("预处理阶段")
        except Exception as e:
            print("预处理出错...")
            self._saveStatus(self.cfg["record_id"], "VIDEO_STATUS_FAILED")
            self.get_new_task()

    # （2）开始语音识别
    def recogn(self) -> None:
        self._saveStatus(
            self.cfg["record_id"], "VIDEO_STATUS_PROCEED_SPEECH_RECOGNITION"
        )
        self._start_timer("语音识别")
        if self._exit():
            return
        if not self.shoud_recogn:
            return
        self.status_text = (
            "开始识别创建字幕"
            if config.defaulelang == "zh"
            else "Start to create subtitles"
        )
        self.precent += 3
        self._signal(text=config.transobj["kaishishibie"])
        if tools.vail_file(self.cfg["source_sub"]):
            self._recogn_succeed()
            return
        # 分离未完成，需等待
        if not tools.vail_file(self.cfg["source_wav"]):
            error = (
                "分离音频失败，请检查日志或重试"
                if config.defaulelang == "zh"
                else "Failed to separate audio, please check the log or retry"
            )
            self._signal(text=error, type="error")
            tools.send_notification(error, f'{self.cfg["basename"]}')
            self.hasend = True
            raise Exception(error)

        try:
            if not tools.vail_file(self.cfg["shibie_audio"]):
                tools.conver_to_16k(self.cfg["source_wav"], self.cfg["shibie_audio"])
            if self.cfg["remove_noise"]:
                self.status_text = (
                    "开始语音降噪处理，用时可能较久，请耐心等待"
                    if config.defaulelang == "zh"
                    else "Starting to process speech noise reduction, which may take a long time, please be patient"
                )
                self.cfg["shibie_audio"] = remove_noise(
                    self.cfg["shibie_audio"],
                    f"{self.cfg['cache_folder']}/remove_noise.wav",
                )
            self.status_text = (
                "语音识别文字处理中"
                if config.defaulelang == "zh"
                else "Speech Recognition to Word Processing"
            )

            if self.cfg["recogn_type"] == Faster_Whisper_XXL:
                import subprocess, shutil

                cmd = [
                    config.settings.get("Faster_Whisper_XXL", ""),
                    self.cfg["shibie_audio"],
                    "-f",
                    "srt",
                ]
                if self.cfg["detect_language"] != "auto":
                    cmd.extend(["-l", self.cfg["detect_language"][:2]])
                cmd.extend(
                    [
                        "--model",
                        self.cfg["model_name"],
                        "--output_dir",
                        self.cfg["target_dir"],
                    ]
                )
                txt_file = (
                    Path(
                        config.settings.get("Faster_Whisper_XXL", "")
                    ).parent.as_posix()
                    + "/pyvideotrans.txt"
                )
                if Path(txt_file).exists():
                    cmd.extend(
                        Path(txt_file).read_text(encoding="utf-8").strip().split(" ")
                    )
                while 1:
                    if not config.copying:
                        break
                    time.sleep(1)
                subprocess.run(cmd)
                # 定义输出的字幕文件路径
                outsrt_file = (
                    self.cfg["target_dir"]
                    + "/"
                    + Path(self.cfg["shibie_audio"]).stem
                    + ".srt"
                )
                # 如果输出的字幕文件路径与源字幕路径不同，则复制到源字幕路径并删除原文件
                if outsrt_file != self.cfg["source_sub"]:
                    shutil.copy2(outsrt_file, self.cfg["source_sub"])
                    Path(outsrt_file).unlink(missing_ok=True)
                # 发送信号更新字幕内容
                self._signal(
                    text=Path(self.cfg["source_sub"]).read_text(encoding="utf-8"),
                    type="replace_subtitle",
                )
            else:
                model = self.cfg["model_name"]
                print(f"语音识别模型 ==========> {model}")
                # file_path = self.cfg["shibie_audio"]
                # with open(file_path, "rb") as file:
                #     files = {
                #         "file": file,
                #     }
                #     data = {
                #         "language": self.cfg["detect_language"]
                #     }
                #     # 使用其他识别模型进行语音识别
                #     split_audio_url = "http://127.0.0.1:10001/asr/client"
                #     response = requests.post(split_audio_url, files = files, data = data)
                #     if response.status_code == 200:
                #     # raw_subtitles: 识别结果
                #         raw_subtitles = response.json().get("data")
                #         self.source_srt_list = raw_subtitles
                #         self._save_srt_target(raw_subtitles, self.cfg["source_sub"])
                #     else:
                #         raise Exception("语音识别失败！")

                raw_subtitles = run_recogn(
                    # faster-whisper openai-whisper googlespeech
                    recogn_type=self.cfg["recogn_type"],
                    # 整体 预先 均等
                    split_type=self.cfg["split_type"],
                    uuid=self.uuid,
                    # 模型名
                    model_name=self.cfg["model_name"],
                    # 识别音频
                    audio_file=self.cfg["shibie_audio"],
                    detect_language=self.cfg["detect_language"],
                    cache_folder=self.cfg["cache_folder"],
                    is_cuda=self.cfg["cuda"],
                    subtitle_type=self.cfg.get("subtitle_type", 0),
                    target_code=(
                        self.cfg["target_language_code"] if self.shoud_trans else None
                    ),
                    inst=self,
                )

                if self._exit():
                    return
                # 没有识别到有效文字信息, 抛出异常
                if not raw_subtitles or len(raw_subtitles) < 1:
                    raise Exception(
                        self.cfg["basename"]
                        + config.transobj["recogn result is empty"].replace(
                            "{lang}", self.cfg["source_language"]
                        )
                    )
                # 根据识别结果保存字幕文件
                if isinstance(raw_subtitles, tuple):
                    self._save_srt_target(raw_subtitles[0], self.cfg["source_sub"])
                    # 源视频字幕
                    self.source_srt_list = raw_subtitles[0]
                    if len(raw_subtitles) == 2:
                        self._save_srt_target(raw_subtitles[1], self.cfg["target_sub"])
                else:
                    #  raw_subtitles 源视频字幕文件
                    self._save_srt_target(raw_subtitles, self.cfg["source_sub"])
                    self.source_srt_list = raw_subtitles
            # 标记识别完成
            # 识别完成需要对字幕敏感词进行替换
            print("==============================================>")
            print(self.cfg)
            keyword_processor = KeywordProcessor()
            from videotrans.util.http_request import http_request

            keyword_dict = http_request.send_request(endpoint="/py/keyword/all")
            if keyword_dict["data"] is not None:
                for item in keyword_dict["data"]:
                    keyword_processor.add_keyword(item["data"], "*" * len(item["data"]))
            srt_file_path = os.path.join(
                os.path.dirname(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                ),
                "apidata",
                self.uuid,
            )
            srt_files = [
                os.path.join(srt_file_path, f)
                for f in os.listdir(srt_file_path)
                if f.endswith(".srt")
            ]
            time_pattern = re.compile(r"^\d{2}:\d{2}:\d{2},\d{3} -->")
            if srt_files is not None and len(srt_files) > 0:
                for srt_file in srt_files:
                    with open(srt_file, "r", encoding="utf-8") as f:
                        lines = f.readlines()
                    new_lines = []
                    for line in lines:
                        line_strip = line.strip()
                        if (
                            line_strip.isdigit()
                            or time_pattern.match(line_strip)
                            or line_strip == ""
                        ):
                            new_lines.append(line)
                        else:
                            try:
                                line = keyword_processor.replace_keywords(line)
                            except Exception as e:
                                print(
                                    f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}替换出错：{e}"
                                )
                                raise Exception("替换出错，请检查输入")
                            new_lines.append(line)
                    with open(srt_file, "w", encoding="utf-8") as f:
                        f.writelines(new_lines)
                # 敏感词替换后进行AI纠正
                if self.cfg["source_language"] == "zh-cn":
                    from AI import ContentUpdate

                    batch_size = 400
                    for srt_file in srt_files:
                        if os.path.isfile(srt_file):
                            with open(srt_file, "r", encoding="utf-8") as f:
                                lines = f.readlines()
                            content_list = []
                            for i in range(0, len(lines), batch_size):
                                batch = lines[i : i + batch_size]
                                text = "".join(batch)
                                try:
                                    new_text = ContentUpdate.deepseek_api(text)
                                    content_list.append(new_text)
                                except Exception as e:
                                    print(
                                        f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}===> AI纠正出错 ===>{e}"
                                    )
                                    content_list.append(text)
                            with open(srt_file, "w", encoding="utf-8") as f:
                                f.write("\n\n".join(content_list))
            self._recogn_succeed()
        except Exception as e:
            msg = f"{str(e)}{str(e.args)}"
            if re.search(r"cub[a-zA-Z0-9_.-]+?\.dll", msg, re.I | re.M) is not None:
                msg = (
                    f"【缺少cuBLAS.dll】请点击菜单栏-帮助/支持-下载cublasxx.dll,或者切换为openai模型 {msg} "
                    if config.defaulelang == "zh"
                    else f"[missing cublasxx.dll] Open menubar Help&Support->Download cuBLASxx.dll or use openai model {msg}"
                )
            elif re.search(r"out\s+?of.*?memory", msg, re.I):
                msg = (
                    f"显存不足，请使用较小模型，比如 tiny/base/small {msg}"
                    if config.defaulelang == "zh"
                    else f"Insufficient video memory, use a smaller model such as tiny/base/small {msg}"
                )
            elif re.search(r"cudnn", msg, re.I):
                msg = (
                    f"cuDNN错误，请尝试升级显卡驱动，重新安装CUDA12.x和cuDNN9 {msg}"
                    if config.defaulelang == "zh"
                    else f"cuDNN error, please try upgrading the graphics card driver and reinstalling CUDA12.x and cuDNN9 {msg}"
                )
            self.hasend = True
            self._signal(text=msg, type="error")
            tools.send_notification(str(e), f'{self.cfg["basename"]}')
            self._saveStatus(self.cfg["record_id"], "VIDEO_STATUS_FAILED")
            self.get_new_task()
            raise
        self._end_timer("语音识别")

    # （3）开始字幕翻译
    def trans(self) -> None:
        self._saveStatus(self.cfg["record_id"], "VIDEO_STATUS_PROCEED_SUBTITLING")
        self._start_timer("字幕翻译")
        if self._exit():
            return
        if not self.shoud_trans:
            return
        self.status_text = config.transobj["starttrans"]

        # 如果存在目标语言字幕，前台直接使用该字幕替换
        if self._srt_vail(self.cfg["target_sub"]):
            print(f"已存在，不需要翻译==")
            # 判断已存在的字幕文件中是否存在有效字幕纪录
            # 通知前端替换字幕
            self._signal(
                text=Path(self.cfg["target_sub"]).read_text(
                    encoding="utf-8", errors="ignore"
                ),
                type="replace_subtitle",
            )
            return
        try:
            # 开始翻译,从目标文件夹读取原始字幕
            rawsrt = tools.get_subtitle_from_srt(self.cfg["source_sub"], is_file=True)
            self.status_text = config.transobj["kaishitiquhefanyi"]
            target_srt = run_trans(
                translate_type=self.cfg["translate_type"],
                text_list=copy.deepcopy(rawsrt),
                inst=self,
                uuid=self.uuid,
                source_code=self.cfg["source_language_code"],
                target_code=self.cfg["target_language_code"],
            )
            # 不同语言才需要翻译
            if self.cfg["source_language_code"] != self.cfg["target_language_code"]:
                self._check_target_sub(rawsrt, target_srt)
            else:
                task_id = self.cfg["task_id"]
                file_path = os.path.join(
                    Path(__file__).resolve().parents[2],
                    "apidata",
                    task_id,
                    task_id + ".json",
                )
                print("==========================================> file_path")
                print(file_path)
                os.makedirs(Path(file_path), exist_ok=True)
                if not file_path.exists():
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(
                            {"text": "", "is_ok": False, "is_save": False},
                            f,
                            ensure_ascii=False,
                            indent=4,
                        )
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.loads(f.read())
                    data["text"] = ""
                for text in rawsrt:
                    data["text"] = data["text"] + text + "\n"
                data["is_ok"] = True
                with open(Path(file_path), "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)

            # 仅提取，该名字删原
            if self.cfg["app_mode"] == "tiqu":
                shutil.copy2(
                    self.cfg["target_sub"],
                    f"{self.cfg['target_dir']}/{self.cfg['noextname']}.srt",
                )
                if self.cfg.get("copysrt_rawvideo"):
                    p = Path(self.cfg["name"])
                    shutil.copy2(
                        self.cfg["target_sub"], f"{p.parent.as_posix()}/{p.stem}.srt"
                    )
                Path(self.cfg["source_sub"]).unlink(missing_ok=True)
                Path(self.cfg["target_sub"]).unlink(missing_ok=True)
                self.hasend = True
                self.precent = 100
        except Exception as e:
            self.hasend = True
            self._signal(text=str(e), type="error")
            tools.send_notification(str(e), f'{self.cfg["basename"]}')
            self._saveStatus(self.cfg["record_id"], "VIDEO_STATUS_FAILED")
            self.get_new_task()
            raise
        self.status_text = config.transobj["endtrans"]
        self._end_timer("字幕翻译")

    # （4）开始配音
    def dubbing(self) -> None:
        self._saveStatus(self.cfg["record_id"], "VIDEO_STATUS_PROCEED_DUB")
        self._start_timer("配音阶段")
        if self._exit():
            return
        if self.cfg["app_mode"] == "tiqu":
            self.precent = 100
            return
        if not self.shoud_dubbing:
            return

        self.status_text = config.transobj["kaishipeiyin"]
        self.precent += 3
        try:
            if (
                self.cfg["voice_role"] == "clone"
                and self.cfg["tts_type"] == ELEVENLABS_TTS
            ):
                if (
                    self.cfg["source_language_code"] != "auto"
                    # zh-cn -> zh
                    and self.cfg["source_language_code"][:2]
                    not in config.ELEVENLABS_CLONE
                ) or (
                    self.cfg["target_language_code"][:2] not in config.ELEVENLABS_CLONE
                ):
                    self.hasend = True
                    raise Exception(
                        "ElevenLabs: Cloning of the selected language is not supported"
                    )
                self.ignore_align = True
                from videotrans.tts._elevenlabs import ElevenLabsClone

                ElevenLabsClone(
                    self.cfg["source_wav"],
                    self.cfg["target_wav"],
                    self.cfg["source_language_code"],
                    self.cfg["target_language_code"],
                ).run()
            else:
                self._tts()
        except Exception as e:
            self.hasend = True
            self._signal(text=str(e), type="error")
            tools.send_notification(str(e), f'{self.cfg["basename"]}')
            self._saveStatus(self.cfg["record_id"], "VIDEO_STATUS_FAILED")
            self.get_new_task()
            raise
        self._end_timer("配音阶段")

    # （5）开始视频合成
    def assembling(self) -> None:
        self._saveStatus(
            self.cfg["record_id"], "VIDEO_STATUS_PROCEED_VIDEO_COMPOSITING"
        )
        self._start_timer("合成阶段")
        if self._exit():
            return
        if self.cfg["app_mode"] == "tiqu":
            self.precent = 100
            return
        if not self.shoud_hebing:
            self.precent = 100
            return
        if self.precent < 95:
            self.precent += 3
        self.status_text = config.transobj["kaishihebing"]
        try:
            self._join_video_audio_srt()
        except Exception as e:
            self.hasend = True
            self._signal(text=str(e), type="error")
            tools.send_notification(str(e), f'{self.cfg["basename"]}')
            self._saveStatus(self.cfg["record_id"], "VIDEO_STATUS_FAILED")
            self.get_new_task()
            raise
        self.precent = 100
        self._end_timer("合成阶段")

    # （6）收尾
    def task_done(self) -> None:
        # 正常完成仍是 ing，手动停止变为 stop
        if self._exit():
            return

        # 提取时，删除
        if self.cfg["app_mode"] == "tiqu":
            Path(
                f"{self.cfg['target_dir']}/{self.cfg['source_language_code']}.srt"
            ).unlink(missing_ok=True)
            Path(
                f"{self.cfg['target_dir']}/{self.cfg['target_language_code']}.srt"
            ).unlink(missing_ok=True)
        # 仅保存视频
        elif self.cfg["only_video"]:
            outputpath = Path(self.cfg["target_dir"])
            for it in outputpath.iterdir():
                ext = it.suffix.lower()
                if ext != ".mp4":
                    it.unlink(missing_ok=True)

        self.hasend = True
        self.precent = 100
        self._signal(text=f"{self.cfg['name']}", type="succeed")
        tools.send_notification(config.transobj["Succeed"], f"{self.cfg['basename']}")
        try:
            if "shound_del_name" in self.cfg:
                Path(self.cfg["shound_del_name"]).unlink(missing_ok=True)
            if self.cfg["only_video"]:
                mp4_path = Path(self.cfg["targetdir_mp4"])
                mp4_path.rename(mp4_path.parent.parent / mp4_path.name)
                shutil.rmtree(self.cfg["target_dir"], ignore_errors=True)
            Path(self.cfg["shibie_audio"]).unlink(missing_ok=True)
            shutil.rmtree(self.cfg["cache_folder"], ignore_errors=True)
        except Exception as e:
            config.logger.exception(e, exc_info=True)
        # 结束任务计时
        self._end_timer("task_done")

        # 计算目标文件的hash值
        hash_code = calculate_file_hash(self.cfg["targetdir_mp4"])

        # 上传处理完成的视频至oss
        # bucket = self.cfg["bucket"]
        # object_key = str(uuid.uuid4())
        # print(f"object_key==================>{object_key}")
        # oss_headers = {"Content-Type": "video/mp4", "x-oss-meta-file-ext": ".mp4"}
        # with open(self.cfg["targetdir_mp4"], "rb") as file:
        #     result = bucket.put_object(object_key, file, headers=oss_headers)
        #     result.resp.read()

        from oss2.models import PartInfo  # 确保导入PartInfo

        bucket = self.cfg["bucket"]
        object_key = str(uuid.uuid4())
        oss_headers = {"Content-Type": "video/mp4", "x-oss-meta-file-ext": ".mp4"}
        # 初始化分片上传
        upload_id = bucket.init_multipart_upload(
            object_key, headers=oss_headers
        ).upload_id
        part_size = 1024 * 1024  # 设置为1MB的分片大小，可根据需要调整
        parts = []

        try:
            with open(self.cfg["targetdir_mp4"], "rb") as file:
                part_number = 1
                while True:
                    data = file.read(part_size)
                    if not data:
                        break
                    # 上传分片
                    result = bucket.upload_part(
                        object_key, upload_id, part_number, data
                    )
                    # 记录分片的编号和ETag
                    parts.append(PartInfo(part_number, result.etag))
                    part_number += 1

            # 按分片编号排序（必须按1~n顺序）
            parts.sort(key=lambda p: p.part_number)

            # 完成分片上传
            bucket.complete_multipart_upload(object_key, upload_id, parts)
        except Exception as e:
            # 出错则中止上传
            bucket.abort_multipart_upload(object_key, upload_id)
            self._saveStatus(self.cfg["record_id"], "VIDEO_STATUS_FAILED")
            raise e

        result_video_data = self._get_video_data(self.cfg["targetdir_mp4"])
        # 计算各阶段的执行时间和百分比
        total_time = sum(
            stage["duration"]
            for stage in self.execution_times.values()
            if "duration" in stage
        )
        execution_logs = []
        sou_data = self.cfg["origin_video_data"]
        for stage, times in self.execution_times.items():
            if "duration" in times:
                percent = (
                    (times["duration"] / total_time) * 100 if total_time > 0 else 0
                )
                log_entry = f"{stage}: {times['duration']:.2f}s\t百分比: {percent:.2f}%"
                execution_logs.append(log_entry)
                config.logger.info(log_entry)
        total_time_log = f"总耗时: {total_time:.2f}s"
        execution_logs.append(total_time_log)
        tar_data = result_video_data
        config.logger.info(total_time_log)

        from datetime import datetime

        now = datetime.now()
        config.logger.info(now.strftime("%Y-%m-%d %H:%M:%S"))

        # 将日志信息转化为字符串
        execution_logs_str = "\n".join(execution_logs)
        task_id = self.cfg["task_id"]
        file_path = os.path.join(
            Path(__file__).resolve().parents[2], "apidata", task_id, task_id + ".json"
        )
        translator_text = ""
        if self.cfg["target_language_code"] != self.cfg["source_language_code"]:
            with open(file_path, "r", encoding="utf-8") as f:
                translator_text = json.loads(f.read())["text"]
        else:
            block = []
            with open(self.cfg["source_sub"], "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line == "":
                        if len(block) >= 3:
                            text_lines = block[2:]
                            translator_text += "\n".join(text_lines) + "\n\n"
                        block = []
                    else:
                        block.append(line)
            if len(block) >= 3:
                text_lines = block[2:]
                translator_text += "\n".join(text_lines) + "\n\n"

        # 翻译完成信息入库
        response = http_request.send_request(
            endpoint="/py/video/modify",
            body={
                "id": self.cfg["record_id"],
                "processStatus": "VIDEO_STATUS_SUCCEED",
                "ossProcKey": object_key,
                "procEndTime": int(time.time() * 1000),
                "result": execution_logs_str,
                "souDuration": round(sou_data["duration"], 2),
                "souSize": round(sou_data["size"] / 1024 / 1024, 3),
                "tarDuration": round(tar_data["duration"], 2),
                "tarSize": round(tar_data["size"] / 1024 / 1024, 3),
                "codec": sou_data["codec"],
                "width": sou_data["width"],
                "height": sou_data["height"],
                "tarHashCode": hash_code,
                "translateContent": translator_text,
            },
            headers={
                "Content-Type": "application/json",
            },
        )
        if response["code"] != 0:
            print("视频信息记录出错")
        self.get_new_task()

    def get_new_task(self):
        from .WebSocketClient import WebSocketClient

        java_config_file_path = (
            Path(__file__).resolve().parents[1] / "util" / "config.json"
        )
        print(java_config_file_path)
        with open(java_config_file_path, "r", encoding="utf-8") as f:
            java_server_port = json.loads(f.read())["java_server_prot"]
        ws_client = WebSocketClient(
            f"ws://127.0.0.1:{java_server_port}/front/ws/getNewTask"
        )
        ws_client.run()
        time.sleep(2)  # 休眠2s防止还未建立连接就关闭了...
        ws_client.send({"from": "client"})

    # ====================== 内部方法 ====================== #

    # 原始语言代码
    def set_source_language(self, source_language_code=None, is_del=False):
        self.cfg["source_language"] = source_language_code
        source_code = (
            self.cfg["source_language"]
            if self.cfg["source_language"] in config.langlist
            else config.rev_langlist.get(self.cfg["source_language"], None)
        )
        if source_code:
            self.cfg["source_language_code"] = source_code
        # 检测字幕原始语言
        self.cfg["detect_language"] = (
            get_audio_code(show_source=self.cfg["source_language_code"])
            if self.cfg["source_language_code"] != "auto"
            else "auto"
        )
        # 原始语言一定存在
        self.cfg["source_sub"] = (
            f"{self.cfg['target_dir']}/{self.cfg['source_language_code']}.srt"
        )
        # 原始语言wav
        self.cfg["source_wav_output"] = (
            f"{self.cfg['target_dir']}/{self.cfg['source_language_code']}.m4a"
        )
        self.cfg["source_wav"] = (
            f"{self.cfg['cache_folder']}/{self.cfg['source_language_code']}.m4a"
        )

        if (
            self.cfg["source_language_code"] != "auto"
            and Path(f"{self.cfg['cache_folder']}/auto.m4a").exists()
        ):
            Path(f"{self.cfg['cache_folder']}/auto.m4a").rename(self.cfg["source_wav"])
        # 是否需要语音识别:只要不存在原始语言字幕文件就需要识别
        self.shoud_recogn = True
        # 作为识别音频
        self.cfg["shibie_audio"] = f"{self.cfg['target_dir']}/shibie.wav"

        # 目标语言代码
        target_code = (
            self.cfg["target_language"]
            if self.cfg["target_language"] in config.langlist
            else config.rev_langlist.get(self.cfg["target_language"], None)
        )
        if target_code:
            self.cfg["target_language_code"] = target_code

        # 目标语言字幕文件
        if self.cfg["target_language_code"]:
            self.cfg["target_sub"] = (
                f"{self.cfg['target_dir']}/{self.cfg['target_language_code']}.srt"
            )
            # 配音后的目标语言音频文件
            self.cfg["target_wav_output"] = (
                f"{self.cfg['target_dir']}/{self.cfg['target_language_code']}.m4a"
            )
            self.cfg["target_wav"] = f"{self.cfg['cache_folder']}/target.m4a"

        # 是否需要翻译:存在目标语言代码并且不等于原始语言，并且不存在目标字幕文件，则需要翻译
        if (
            self.cfg["target_language_code"]
            and self.cfg["target_language_code"] != self.cfg["source_language_code"]
        ):
            self.shoud_trans = True

        # 如果原语言和目标语言相等，并且存在配音角色，则替换配音
        if (
            self.cfg["voice_role"] != "No"
            and self.cfg["source_language_code"] == self.cfg["target_language_code"]
        ):
            self.cfg["target_wav_output"] = (
                f"{self.cfg['target_dir']}/{self.cfg['target_language_code']}-dubbing.m4a"
            )
            self.cfg["target_wav"] = f"{self.cfg['cache_folder']}/target-dubbing.m4a"

        if is_del:
            self._unlink_size0(self.cfg["source_sub"])
            self._unlink_size0(self.cfg["target_sub"])
        if self.cfg["source_wav"]:
            Path(self.cfg["source_wav"]).unlink(missing_ok=True)
        if self.cfg["source_wav_output"]:
            Path(self.cfg["source_wav_output"]).unlink(missing_ok=True)
        if self.cfg["target_wav"]:
            Path(self.cfg["target_wav"]).unlink(missing_ok=True)
        if self.cfg["target_wav_output"]:
            Path(self.cfg["target_wav_output"]).unlink(missing_ok=True)
        if self.cfg["shibie_audio"]:
            Path(self.cfg["shibie_audio"]).unlink(missing_ok=True)

    # 识别成功，识别成功后，根据app_mode决定是否需要翻译
    def _recogn_succeed(self) -> None:
        # 仅提取字幕
        self.precent += 5
        if self.cfg["app_mode"] == "tiqu":
            dest_name = f"{self.cfg['target_dir']}/{self.cfg['noextname']}"
            if not self.shoud_trans:
                self.hasend = True
                self.precent = 100
                dest_name += ".srt"
                shutil.copy2(self.cfg["source_sub"], dest_name)
                Path(self.cfg["source_sub"]).unlink(missing_ok=True)
            else:
                dest_name += f"-{self.cfg['source_language_code']}.srt"
                shutil.copy2(self.cfg["source_sub"], dest_name)
        self.status_text = config.transobj["endtiquzimu"]

    # 检查目标字幕
    def _check_target_sub(self, source_srt_list, target_srt_list):
        for i, it in enumerate(source_srt_list):
            if i >= len(target_srt_list) or target_srt_list[i]["time"] != it["time"]:
                # 在 target_srt_list 的 索引 i 位置插入一个dict
                tmp = copy.deepcopy(it)
                tmp["text"] = "  "
                if i >= len(target_srt_list):
                    target_srt_list.append(tmp)
                else:
                    target_srt_list.insert(i, tmp)
            else:
                target_srt_list[i]["line"] = it["line"]
        self._save_srt_target(target_srt_list, self.cfg["target_sub"])

    # 分离音频 和 novoice.mp4
    def _split_wav_novicemp4(self) -> None:
        # 不是 提取字幕时，需要分离出视频
        if self.cfg["app_mode"] not in ["tiqu"]:
            config.queue_novice[self.cfg["noextname"]] = "ing"
            threading.Thread(
                target=tools.split_novoice_byraw,
                args=(
                    self.cfg["name"],
                    self.cfg["novoice_mp4"],
                    self.cfg["noextname"],
                    "copy" if self.is_copy_video else f"libx{self.video_codec_num}",
                ),
            ).start()
            if not self.is_copy_video:
                self.status_text = (
                    "视频需要转码，耗时可能较久.."
                    if config.defaulelang == "zh"
                    else "Video needs transcoded and take a long time.."
                )
        else:
            config.queue_novice[self.cfg["noextname"]] = "end"

        # 添加是否保留背景选项
        if self.cfg["is_separate"]:
            try:
                self._signal(text=config.transobj["Separating background music"])
                self.status_text = config.transobj["Separating background music"]
                tools.split_audio_byraw(
                    self.cfg["name"], self.cfg["source_wav"], True, uuid=self.uuid
                )
            except Exception as e:
                pass
            finally:
                if not tools.vail_file(self.cfg["vocal"]):
                    # 分离失败
                    self.cfg["instrument"] = None
                    self.cfg["vocal"] = None
                    self.cfg["is_separate"] = False
                    self.shoud_separate = False
                elif self.shoud_recogn:
                    # 需要识别时
                    # 分离成功后转为16k待识别音频
                    tools.conver_to_16k(self.cfg["vocal"], self.cfg["shibie_audio"])
        # 不分离，或分离失败
        if not self.cfg["is_separate"]:
            try:
                self.status_text = config.transobj["kaishitiquyinpin"]
                tools.split_audio_byraw(self.cfg["name"], self.cfg["source_wav"])
                # 需要识别
                if self.shoud_recogn:
                    tools.conver_to_16k(
                        self.cfg["source_wav"], self.cfg["shibie_audio"]
                    )
            except Exception as e:
                self._signal(text=str(e), type="error")
                raise
        if self.cfg["source_wav"]:
            shutil.copy2(
                self.cfg["source_wav"],
                self.cfg["target_dir"] + f"/{os.path.basename(self.cfg['source_wav'])}",
            )
        self.status_text = config.transobj["endfenliyinpin"]

    # 配音预处理，去掉无效字符，整理开始时间
    def _tts(self) -> None:
        queue_tts = []
        # 获取字幕 可能之前写入尚未释放，暂停1s等待并重试一次
        subs = tools.get_subtitle_from_srt(self.cfg["target_sub"])
        source_subs = tools.get_subtitle_from_srt(self.cfg["source_sub"])
        if len(subs) < 1:
            raise Exception(f"字幕格式不正确，请打开查看:{self.cfg['target_sub']}")
        try:
            rate = int(str(self.cfg["voice_rate"]).replace("%", ""))
        except:
            rate = 0
        if rate >= 0:
            rate = f"+{rate}%"
        else:
            rate = f"{rate}%"
        # 取出设置的每行角色
        line_roles = config.line_roles
        # 取出每一条字幕，行号\n开始时间 --> 结束时间\n内容
        for i, it in enumerate(subs):
            if it["end_time"] <= it["start_time"]:
                continue
            # 判断是否存在单独设置的行角色，如果不存在则使用全局
            voice_role = self.cfg["voice_role"]
            if line_roles and f'{it["line"]}' in line_roles:
                voice_role = line_roles[f'{it["line"]}']

            tmp_dict = {
                "text": it["text"],
                "ref_audio": self.cfg["refer_audio"],
                "ref_text": (
                    source_subs[i]["text"]
                    if source_subs and i < len(source_subs)
                    else ""
                ),
                "role": voice_role,
                "start_time_source": source_subs[i]["start_time"],
                "start_time": it["start_time"],
                "end_time_source": source_subs[i]["end_time"],
                "end_time": it["end_time"],
                "rate": rate,
                "startraw": it["startraw"],
                "endraw": it["endraw"],
                "volume": self.cfg["volume"],
                "pitch": self.cfg["pitch"],
                "tts_type": self.cfg["tts_type"],
                "filename": config.TEMP_DIR
                + f"/dubbing_cache/{it['start_time']}-{it['end_time']}-{time.time()}-{len(it['text'])}-{i}.mp3",
            }
            if voice_role == "clone-single":
                tmp_dict["ref_text"] = self.cfg["refer_text"]
            # 如果是clone-voice类型， 需要截取对应片段
            if (
                self.cfg["tts_type"]
                in [COSYVOICE_TTS, CLONE_VOICE_TTS, F5_TTS, SPARK_TTS, INDEX_TTS]
                and voice_role == "clone"
            ):
                if self.cfg["is_separate"] and not tools.vail_file(self.cfg["vocal"]):
                    raise Exception(
                        f"背景分离出错,请使用其他角色名"
                        if config.defaulelang == "zh"
                        else "Background separation error, please use another character name."
                    )

                if tools.vail_file(self.cfg["source_wav"]):
                    tmp_dict["ref_wav"] = (
                        config.TEMP_DIR
                        + f"/dubbing_cache/{it['start_time']}-{it['end_time']}-{time.time()}-{i}.wav"
                    )
                    if voice_role == "clone":
                        tools.cut_from_audio(
                            audio_file=(
                                self.cfg["vocal"]
                                if self.cfg["is_separate"]
                                else self.cfg["source_wav"]
                            ),
                            ss=it["startraw"],
                            to=it["endraw"],
                            out_file=tmp_dict["ref_wav"],
                        )
            queue_tts.append(tmp_dict)

        self.queue_tts = copy.deepcopy(queue_tts)
        Path(config.TEMP_DIR + "/dubbing_cache").mkdir(parents=True, exist_ok=True)
        if not self.queue_tts or len(self.queue_tts) < 1:
            raise Exception(f"Queue tts length is 0")
        # 具体配音操作
        run_tts(
            queue_tts=copy.deepcopy(self.queue_tts),
            language=self.cfg["target_language_code"],
            uuid=self.uuid,
            inst=self,
        )

    # 延长视频末尾以对齐音频
    def _novoicemp4_add_time(self, duration_ms):
        if duration_ms < 1000 or self._exit():
            return
        self._signal(text=f'{config.transobj["shipinmoweiyanchang"]} {duration_ms}ms')
        # 等待无声视频分离结束
        tools.is_novoice_mp4(
            self.cfg["novoice_mp4"], self.cfg["noextname"], uuid=self.uuid
        )

        shutil.copy2(self.cfg["novoice_mp4"], self.cfg["novoice_mp4"] + ".raw.mp4")

        # 计算需要定格的时长
        freeze_duration = duration_ms / 1000

        if freeze_duration <= 0:
            return
        try:
            # 构建 FFmpeg 命令
            default_codec = f"libx{config.settings['video_codec']}"
            cmd = [
                "-y",
                "-threads",
                f"{os.cpu_count()}",
                "-i",
                self.cfg["novoice_mp4"],
                "-vf",
                f"tpad=stop_mode=clone:stop_duration={freeze_duration}",
                "-c:v",
                default_codec,  # 使用 libx264 编码器，可根据需要更改
                "-crf",
                f'{config.settings["crf"]}',
                "-preset",
                config.settings["preset"],
                self.cfg["cache_folder"] + "/last-all.mp4",
            ]
            tools.runffmpeg(cmd)
            shutil.copy2(
                self.cfg["cache_folder"] + "/last-all.mp4", self.cfg["novoice_mp4"]
            )
        except Exception as e:
            # 延长失败
            config.logger.exception(e, exc_info=True)
            shutil.copy2(self.cfg["novoice_mp4"] + ".raw.mp4", self.cfg["novoice_mp4"])
        finally:
            Path(f"{self.cfg['novoice_mp4']}.raw.mp4").unlink(missing_ok=True)

    # 声画变速对齐
    def align(self) -> None:
        if self._exit():
            return
        if self.cfg["app_mode"] == "tiqu":
            self.precent = 100
            return

        if not self.shoud_dubbing or self.ignore_align:
            return

        self.status_text = config.transobj["duiqicaozuo"]
        self.precent += 3
        if self.cfg["voice_autorate"] or self.cfg["video_autorate"]:
            self.status_text = (
                "声画变速对齐阶段"
                if config.defaulelang == "zh"
                else "Sound & video speed alignment stage"
            )
        try:
            shoud_video_rate = (
                self.cfg["video_autorate"]
                and int(float(config.settings["video_rate"])) > 1
            )
            # 如果时需要慢速或者需要末尾延长视频，需等待 novoice_mp4 分离完毕
            if shoud_video_rate or self.cfg["append_video"]:
                tools.is_novoice_mp4(self.cfg["novoice_mp4"], self.cfg["noextname"])
            rate_inst = SpeedRate(
                queue_tts=self.queue_tts,
                uuid=self.uuid,
                shoud_audiorate=self.cfg["voice_autorate"]
                and int(float(config.settings["audio_rate"])) > 1,
                # 视频是否需慢速，需要时对 novoice_mp4进行处理
                shoud_videorate=shoud_video_rate,
                novoice_mp4=self.cfg["novoice_mp4"],
                # 原始总时长
                raw_total_time=self.video_time,
                noextname=self.cfg["noextname"],
                target_audio=self.cfg["target_wav"],
                cache_folder=self.cfg["cache_folder"],
            )
            self.queue_tts = rate_inst.run()
            # 慢速处理后，更新新视频总时长，用于音视频对齐
            self.video_time = tools.get_video_duration(self.cfg["novoice_mp4"])
            # 更新字幕
            srt = ""
            for idx, it in enumerate(self.queue_tts):
                if not config.settings["force_edit_srt"]:
                    it["startraw"] = tools.ms_to_time_string(ms=it["start_time_source"])
                    it["endraw"] = tools.ms_to_time_string(ms=it["end_time_source"])
                srt += (
                    f"{idx + 1}\n{it['startraw']} --> {it['endraw']}\n{it['text']}\n\n"
                )
            # 字幕保存到目标文件夹
            with Path(self.cfg["target_sub"]).open("w", encoding="utf-8") as f:
                f.write(srt.strip())
        except Exception as e:
            self.hasend = True
            self._signal(text=str(e), type="error")
            tools.send_notification(str(e), f'{self.cfg["basename"]}')
            raise

        # 成功后，如果存在 音量，则调节音量
        if (
            self.cfg["tts_type"] not in [EDGE_TTS, AZURE_TTS]
            and self.cfg["volume"] != "+0%"
            and tools.vail_file(self.cfg["target_wav"])
        ):
            volume = self.cfg["volume"].replace("%", "").strip()
            try:
                volume = 1 + float(volume) / 100
                tmp_name = (
                    self.cfg["cache_folder"]
                    + f'/volume-{volume}-{Path(self.cfg["target_wav"]).name}'
                )
                tools.runffmpeg(
                    [
                        "-y",
                        "-i",
                        self.cfg["target_wav"],
                        "-af",
                        f"volume={volume}",
                        tmp_name,
                    ]
                )
            except:
                pass
            else:
                shutil.copy2(tmp_name, self.cfg["target_wav"])

    # 添加背景音乐
    def _back_music(self) -> None:
        if self._exit() or not self.shoud_dubbing:
            return

        if tools.vail_file(self.cfg["target_wav"]) and tools.vail_file(
            self.cfg["background_music"]
        ):
            try:
                self.status_text = (
                    "添加背景音频"
                    if config.defaulelang == "zh"
                    else "Adding background audio"
                )
                # 获取视频长度
                vtime = tools.get_audio_time(self.cfg["target_wav"])
                # 获取背景音频长度
                atime = tools.get_audio_time(self.cfg["background_music"])

                # 转为m4a
                bgm_file = self.cfg["cache_folder"] + f"/bgm_file.m4a"
                if not self.cfg["background_music"].lower().endswith(".m4a"):
                    tools.wav2m4a(self.cfg["background_music"], bgm_file)
                    self.cfg["background_music"] = bgm_file
                else:
                    shutil.copy2(self.cfg["background_music"], bgm_file)
                    self.cfg["background_music"] = bgm_file

                beishu = math.ceil(vtime / atime)
                if (
                    config.settings["loop_backaudio"]
                    and beishu > 1
                    and vtime - 1 > atime
                ):
                    # 获取延长片段
                    file_list = [
                        self.cfg["background_music"] for n in range(beishu + 1)
                    ]
                    concat_txt = self.cfg["cache_folder"] + f"/{time.time()}.txt"
                    tools.create_concat_txt(file_list, concat_txt=concat_txt)
                    tools.concat_multi_audio(
                        concat_txt=concat_txt,
                        out=self.cfg["cache_folder"] + "/bgm_file_extend.m4a",
                    )
                    self.cfg["background_music"] = (
                        self.cfg["cache_folder"] + "/bgm_file_extend.m4a"
                    )
                # 背景音频降低音量
                tools.runffmpeg(
                    [
                        "-y",
                        "-i",
                        self.cfg["background_music"],
                        "-filter:a",
                        f"volume={config.settings['backaudio_volume']}",
                        "-c:a",
                        "aac",
                        self.cfg["cache_folder"] + f"/bgm_file_extend_volume.m4a",
                    ]
                )
                # 背景音频和配音合并
                cmd = [
                    "-y",
                    "-i",
                    self.cfg["target_wav"],
                    "-i",
                    self.cfg["cache_folder"] + f"/bgm_file_extend_volume.m4a",
                    "-filter_complex",
                    "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=2",
                    "-ac",
                    "2",
                    self.cfg["cache_folder"] + f"/lastend.m4a",
                ]
                tools.runffmpeg(cmd)
                self.cfg["target_wav"] = self.cfg["cache_folder"] + f"/lastend.m4a"
            except Exception as e:
                config.logger.exception(f"添加背景音乐失败:{str(e)}", exc_info=True)

    # 重新嵌入背景音
    def _separate(self) -> None:
        if self._exit() or not self.shoud_separate:
            return

        if tools.vail_file(self.cfg["target_wav"]):
            try:
                self.status_text = (
                    "重新嵌入背景音"
                    if config.defaulelang == "zh"
                    else "Re-embedded background sounds"
                )
                # 原始背景音乐 wav,和配音后的文件m4a合并
                # 获取视频长度
                vtime = tools.get_audio_time(self.cfg["target_wav"])
                # 获取音频长度
                atime = tools.get_audio_time(self.cfg["instrument"])
                beishu = math.ceil(vtime / atime)
                # instrument_file = self.cfg['cache_folder'] + f'/instrument.wav'
                # shutil.copy2(self.cfg['instrument'], instrument_file)
                instrument_file = self.cfg["instrument"]
                config.logger.info(f"合并背景音 {beishu=},{atime=},{vtime=}")
                if config.settings["loop_backaudio"] and atime + 1 < vtime:
                    # 背景音连接延长片段
                    file_list = [instrument_file for n in range(beishu + 1)]
                    concat_txt = self.cfg["cache_folder"] + f"/{time.time()}.txt"
                    tools.create_concat_txt(file_list, concat_txt=concat_txt)
                    tools.concat_multi_audio(
                        concat_txt=concat_txt,
                        out=self.cfg["cache_folder"] + "/instrument-concat.m4a",
                    )
                    self.cfg["instrument"] = (
                        self.cfg["cache_folder"] + f"/instrument-concat.m4a"
                    )
                # 背景音合并配音
                tools.backandvocal(self.cfg["instrument"], self.cfg["target_wav"])
            except Exception as e:
                config.logger.exception(
                    "合并原始背景失败"
                    + config.transobj["Error merging background and dubbing"]
                    + str(e),
                    exc_info=True,
                )

    # 处理所需字幕
    def _process_subtitles(self) -> tuple[str, str]:
        if not self.cfg["target_sub"] or not Path(self.cfg["target_sub"]).exists():
            raise Exception(
                f"不存在有效的字幕文件"
                if config.defaulelang == "zh"
                else "No valid subtitle file exists"
            )

        # 根据视频宽高适配字幕
        width = self.cfg["origin_video_data"]["width"]
        height = self.cfg["origin_video_data"]["height"]
        # 动态计算字体大小（基于视频高度）
        short_side = min(width, height)
        aspect_ratio = width / height

        # 1. 动态计算字体大小（区分横屏/竖屏）
        if aspect_ratio < 1:  # 竖屏视频
            fontsize = max(8, min(int(height * 0.003), 16))  # 竖屏字体稍小
        else:  # 横屏视频
            fontsize = max(12, min(int(short_side * 0.005), 24))

        # 2. 动态计算安全宽度
        if aspect_ratio < 1:  # 竖屏
            safe_width = width * 0.2
        else:  # 横屏
            safe_width = width * 0.4

        dynamic_cjk_len = max(16, min(int(safe_width / fontsize), 32))
        dynamic_other_len = max(24, min(int(safe_width / (fontsize * 0.2)), 64))

        print(f"width:{width}")
        print(f"height:{height}")
        print(f"fontsize:{fontsize}")
        print(f"dynamic_cjk_len:{dynamic_cjk_len}")
        print(f"dynamic_other_len:{dynamic_other_len}")

        # 如果原始语言和目标语言相同，或不存原始语言字幕，则强制单字幕
        if (self.cfg["source_language_code"] == self.cfg["target_language_code"]) or (
            not self.cfg["source_sub"] or not Path(self.cfg["source_sub"]).exists()
        ):
            if self.cfg["subtitle_type"] == 3:
                self.cfg["subtitle_type"] = 1
            elif self.cfg["subtitle_type"] == 4:
                self.cfg["subtitle_type"] = 2
        # 最终处理后需要嵌入视频的字幕
        process_end_subtitle = self.cfg["cache_folder"] + f"/end.srt"
        # 硬字幕时单行字符数
        # maxlen = int(
        #     config.settings["cjk_len"]
        #     if self.cfg["target_language_code"][:2] in ["zh", "ja", "jp", "ko"]
        #     else config.settings["other_len"]
        # )
        maxlen = (
            dynamic_cjk_len
            if self.cfg["target_language_code"][:2] in ["zh", "ja", "jp", "ko"]
            else dynamic_other_len
        )
        target_sub_list = tools.get_subtitle_from_srt(self.cfg["target_sub"])

        if (
            self.cfg["subtitle_type"] in [3, 4]
            and not Path(self.cfg["source_sub"]).exists()
        ):
            config.logger.info(f"无源语言字幕，使用目标语言字幕")
            self.cfg["subtitle_type"] = 1 if self.cfg["subtitle_type"] == 3 else 2

        # 双硬 双软字幕组装
        if self.cfg["subtitle_type"] in [3, 4]:
            source_sub_list = tools.get_subtitle_from_srt(self.cfg["source_sub"])
            source_length = len(source_sub_list)

            srt_string = ""
            for i, it in enumerate(target_sub_list):
                # 动态计算每行字符数（区分语言）
                target_maxlen = (
                    dynamic_cjk_len
                    if self.cfg["target_language_code"][:2] in ["zh", "ja", "jp", "ko"]
                    else dynamic_other_len
                )
                source_maxlen = (
                    dynamic_cjk_len
                    if self.cfg["source_language_code"][:2] in ["zh", "ja", "jp", "ko"]
                    else dynamic_other_len
                )

                # 处理目标语言字幕
                target_text = (
                    textwrap.fill(
                        it["text"].strip(), target_maxlen, replace_whitespace=False
                    )
                    if self.cfg["subtitle_type"] == 3
                    else it["text"].strip()
                )

                srt_string += f"{it['line']}\n{it['time']}\n{target_text}"

                # 处理源语言字幕（如果存在）
                if source_length > 0 and i < source_length:
                    source_text = (
                        textwrap.fill(
                            source_sub_list[i]["text"].strip(),
                            source_maxlen,
                            replace_whitespace=False,
                        ).strip()
                        if self.cfg["subtitle_type"] == 3
                        else source_sub_list[i]["text"].strip()
                    )
                    srt_string += f"\n{source_text}"

                srt_string += "\n\n"

            # 保存处理后的字幕文件
            process_end_subtitle = f"{self.cfg['cache_folder']}/shuang.srt"
            with Path(process_end_subtitle).open("w", encoding="utf-8") as f:
                f.write(srt_string.strip())
            shutil.copy2(process_end_subtitle, self.cfg["target_dir"] + "/shuang.srt")
        elif self.cfg["subtitle_type"] == 1:
            # 单硬字幕，需处理字符数换行
            srt_string = ""
            for i, it in enumerate(target_sub_list):
                tmp = textwrap.fill(
                    it["text"].strip(), maxlen, replace_whitespace=False
                )
                srt_string += f"{it['line']}\n{it['time']}\n{tmp.strip()}\n\n"
            with Path(process_end_subtitle).open("w", encoding="utf-8") as f:
                f.write(srt_string)
        else:
            # 单软字幕
            basename = os.path.basename(self.cfg["target_sub"])
            process_end_subtitle = self.cfg["cache_folder"] + f"/{basename}"
            shutil.copy2(self.cfg["target_sub"], process_end_subtitle)

        # 目标字幕语言
        subtitle_langcode = translator.get_subtitle_code(
            show_target=self.cfg["target_language"]
        )

        # 单软 或双软
        if self.cfg["subtitle_type"] in [2, 4]:
            return os.path.basename(process_end_subtitle), subtitle_langcode

        # 硬字幕转为ass格式 并设置样式
        process_end_subtitle_ass = tools.set_ass_font(process_end_subtitle, fontsize)
        basename = os.path.basename(process_end_subtitle_ass)
        return basename, subtitle_langcode

    # 延长视频末尾对齐声音
    def _append_video(self) -> None:
        # 有配音 延长视频或音频对齐
        if self._exit() or not self.shoud_dubbing:
            return
        video_time = self.video_time
        try:
            audio_length = int(tools.get_audio_time(self.cfg["target_wav"]) * 1000)
        except Exception:
            audio_length = 0
        if audio_length <= 0 or audio_length == video_time:
            return

        # 不延长视频末尾，如果音频大于时长则阶段
        if not self.cfg["append_video"]:
            if audio_length > video_time:
                ext = self.cfg["target_wav"].split(".")[-1]
                m = AudioSegment.from_file(
                    self.cfg["target_wav"], format="mp4" if ext == "m4a" else ext
                )
                m[0:video_time].export(
                    self.cfg["target_wav"], format="mp4" if ext == "m4a" else ext
                )
            return

        if audio_length > video_time:
            try:
                # 先对音频末尾移除静音
                tools.remove_silence_from_end(self.cfg["target_wav"], is_start=False)
                audio_length = int(tools.get_audio_time(self.cfg["target_wav"]) * 1000)
            except Exception:
                audio_length = 0

        if audio_length <= 0 or audio_length == video_time:
            return

        if audio_length > video_time:
            # 视频末尾延长
            try:
                # 对视频末尾定格延长
                self.status_text = (
                    "视频末尾延长中"
                    if config.defaulelang == "zh"
                    else "Extension at the end of the video"
                )
                self._novoicemp4_add_time(audio_length - video_time)
            except Exception as e:
                config.logger.exception(f"视频末尾延长失败:{str(e)}", exc_info=True)
        else:
            ext = self.cfg["target_wav"].split(".")[-1]
            m = AudioSegment.from_file(
                self.cfg["target_wav"], format="mp4" if ext == "m4a" else ext
            ) + AudioSegment.silent(duration=video_time - audio_length)
            m.export(self.cfg["target_wav"], format="mp4" if ext == "m4a" else ext)

    # 最终合成视频 source_mp4=原始mp4视频文件，noextname=无扩展名的视频文件名字
    def _join_video_audio_srt(self) -> None:
        if self._exit():
            return
        if not self.shoud_hebing:
            return True

        # 判断novoice_mp4是否完成
        tools.is_novoice_mp4(self.cfg["novoice_mp4"], self.cfg["noextname"])

        # 需要配音但没有配音文件
        if self.shoud_dubbing and not tools.vail_file(self.cfg["target_wav"]):
            raise Exception(
                f"{config.transobj['Dubbing']}{config.transobj['anerror']}:{self.cfg['target_wav']}"
            )

        # 字幕重新分割
        if self.cfg["subtitle_type"] > 0:
            # 读取原始字幕文件
            subs = tools.get_subtitle_from_srt(self.cfg["target_sub"])
            # 分割过长的字幕
            new_subs = []
            for sub in subs:
                duration = sub["end_time"] - sub["start_time"]
                text = sub["text"]
                # 如果字幕持续时间超过10秒或字符数超过40，则进行分割
                if duration > 10000 or len(text) > 40:
                    # 计算分割段数
                    segments = max(2, math.ceil(duration / 5000))
                    # 按标点符号分割文本
                    sentences = re.split(r"(?<=[,.!?;:，。！？；：])", text)
                    if len(sentences) < 2:
                        # 如果没有标点符号，则按字数均分
                        words = text.split()
                        seg_word_count = max(1, len(words) // segments)
                        sentences = [
                            " ".join(words[i : i + seg_word_count])
                            for i in range(0, len(words), seg_word_count)
                        ]
                    # 创建分割后的字幕段
                    seg_duration = duration / len(sentences)
                    for i, sentence in enumerate(sentences):
                        if not sentence.strip():
                            continue
                        new_sub = copy.deepcopy(sub)
                        new_sub["start_time"] = sub["start_time"] + i * seg_duration
                        new_sub["end_time"] = min(
                            sub["end_time"], sub["start_time"] + (i + 1) * seg_duration
                        )
                        new_sub["text"] = sentence.strip()
                        new_subs.append(new_sub)
                else:
                    new_subs.append(sub)
                # 打印最终所有字幕
                config.logger.info("\n==== 最终字幕 ====")
                srt_logs = []
                for i, sub in enumerate(new_subs, 1):
                    srt_logs.append(
                        f"[{i}] {tools.ms_to_time_string(ms=sub['start_time'])} --> "
                        f"{tools.ms_to_time_string(ms=sub['end_time'])}\n"
                        f"{sub['text']}\n"
                    )
                config.logger.info("\n".join(srt_logs))

            # 保存分割后的字幕文件
            if len(new_subs) > len(subs):
                srt_content = ""
                for i, sub in enumerate(new_subs):
                    srt_content += f"{i + 1}\n"
                    srt_content += f"{tools.ms_to_time_string(ms=sub['start_time'])} --> {tools.ms_to_time_string(ms=sub['end_time'])}\n"
                    srt_content += f"{sub['text']}\n\n"
                with open(self.cfg["target_sub"], "w", encoding="utf-8") as f:
                    f.write(srt_content.strip())

        # 字幕大小调整
        subtitles_file, subtitle_langcode = None, None
        if self.cfg["subtitle_type"] > 0:
            subtitles_file, subtitle_langcode = self._process_subtitles()

        self.precent = 90 if self.precent < 90 else self.precent
        # 添加背景音乐
        self._back_music()
        # 重新嵌入分离出的背景音
        self._separate()
        # 有配音 延长视频或音频对齐
        self._append_video()

        self.precent = min(max(90, self.precent), 90)

        protxt = config.TEMP_DIR + f"/compose{time.time()}.txt"
        threading.Thread(target=self._hebing_pro, args=(protxt,)).start()

        # 字幕嵌入时进入视频目录下
        os.chdir(Path(self.cfg["novoice_mp4"]).parent.resolve())
        if tools.vail_file(self.cfg["target_wav"]):
            shutil.copy2(self.cfg["target_wav"], self.cfg["target_wav_output"])
        try:
            self.status_text = (
                "视频+字幕+配音合并中"
                if config.defaulelang == "zh"
                else "Video + Subtitles + Dubbing in merge"
            )
            # 有配音有字幕
            if self.cfg["voice_role"] != "No" and self.cfg["subtitle_type"] > 0:
                if self.cfg["subtitle_type"] in [1, 3]:
                    self._signal(text=config.transobj["peiyin-yingzimu"])
                    # 需要配音+硬字幕
                    tools.runffmpeg(
                        [
                            "-y",
                            "-progress",
                            protxt,
                            "-i",
                            self.cfg["novoice_mp4"],
                            "-i",
                            Path(self.cfg["target_wav"]).as_posix(),
                            "-c:v",
                            f"libx{self.video_codec_num}",
                            "-c:a",
                            "aac",
                            "-b:a",
                            "192k",
                            "-vf",
                            f"subtitles={subtitles_file}",
                            "-crf",
                            f'{config.settings["crf"]}',
                            "-preset",
                            config.settings["preset"],
                            Path(self.cfg["targetdir_mp4"]).as_posix(),
                        ]
                    )
                else:
                    # 配音+软字幕
                    self._signal(text=config.transobj["peiyin-ruanzimu"])
                    tools.runffmpeg(
                        [
                            "-y",
                            "-progress",
                            protxt,
                            "-i",
                            self.cfg["novoice_mp4"],
                            "-i",
                            Path(self.cfg["target_wav"]).as_posix(),
                            "-i",
                            subtitles_file,
                            "-c:v",
                            "copy",
                            "-c:a",
                            "aac",
                            "-c:s",
                            "mov_text",
                            "-metadata:s:s:0",
                            f"language={subtitle_langcode}",
                            "-b:a",
                            "192k",
                            Path(self.cfg["targetdir_mp4"]).as_posix(),
                        ]
                    )
            elif self.cfg["voice_role"] != "No":
                # 有配音无字幕
                self._signal(text=config.transobj["onlypeiyin"])
                tools.runffmpeg(
                    [
                        "-y",
                        "-progress",
                        protxt,
                        "-i",
                        self.cfg["novoice_mp4"],
                        "-i",
                        Path(self.cfg["target_wav"]).as_posix(),
                        "-c:v",
                        "copy",
                        "-c:a",
                        "aac",
                        "-b:a",
                        "192k",
                        Path(self.cfg["targetdir_mp4"]).as_posix(),
                    ]
                )
            # 硬字幕无配音  原始 wav 合并
            elif self.cfg["subtitle_type"] in [1, 3]:
                self._signal(text=config.transobj["onlyyingzimu"])
                cmd = ["-y", "-progress", protxt, "-i", self.cfg["novoice_mp4"]]
                if tools.vail_file(self.cfg["source_wav"]):
                    cmd.append("-i")
                    cmd.append(Path(self.cfg["source_wav"]).as_posix())

                cmd.append("-c:v")
                cmd.append(f"libx{self.video_codec_num}")
                if tools.vail_file(self.cfg["source_wav"]):
                    cmd.append("-c:a")
                    cmd.append("aac")
                cmd += [
                    "-b:a",
                    "192k",
                    "-vf",
                    f"subtitles={subtitles_file}",
                    "-crf",
                    f'{config.settings["crf"]}',
                    "-preset",
                    config.settings["preset"],
                    Path(self.cfg["targetdir_mp4"]).as_posix(),
                ]
                tools.runffmpeg(cmd)
            elif self.cfg["subtitle_type"] in [2, 4]:
                # 无配音软字幕
                self._signal(text=config.transobj["onlyruanzimu"])
                # 原视频
                cmd = ["-y", "-progress", protxt, "-i", self.cfg["novoice_mp4"]]
                # 原配音流
                if tools.vail_file(self.cfg["source_wav"]):
                    cmd.append("-i")
                    cmd.append(Path(self.cfg["source_wav"]).as_posix())
                # 目标字幕流
                cmd += ["-i", subtitles_file, "-c:v", "copy"]
                if tools.vail_file(self.cfg["source_wav"]):
                    cmd.append("-c:a")
                    cmd.append("aac")
                cmd += [
                    "-c:s",
                    "mov_text",
                    "-metadata:s:s:0",
                    f"language={subtitle_langcode}",
                    "-crf",
                    f'{config.settings["crf"]}',
                    "-preset",
                    config.settings["preset"],
                ]
                cmd.append(Path(self.cfg["targetdir_mp4"]).as_posix())
                tools.runffmpeg(cmd)
        except Exception as e:
            msg = (
                f"最后一步字幕配音嵌入时出错:{e}"
                if config.defaulelang == "zh"
                else f"Error in embedding the final step of the subtitle dubbing:{e}"
            )
            self._signal(text=msg, type="error")
            raise Exception(msg)
        self.precent = 99
        os.chdir(config.ROOT_DIR)
        # 创建说明文本
        # self._create_txt()
        self.precent = 100
        time.sleep(1)
        self.hasend = True
        return True

    def _saveStatus(self, id, processStatus) -> None:
        resp = http_request.send_request(
            endpoint="/py/video/updateStatus",
            body={"id": id, "processStatus": processStatus},
            headers={
                "Content-Type": "application/json",
            },
        )
        if resp["code"] != 0:
            raise Exception("视频状态记录出错")

    # ffmpeg进度日志
    def _hebing_pro(self, protxt) -> None:
        basenum = 100 - self.precent
        video_time = self.video_time
        while 1:
            if self.precent >= 100:
                return
            if not os.path.exists(protxt):
                time.sleep(1)
                continue
            with open(protxt, "r", encoding="utf-8") as f:
                content = f.read().strip().split("\n")
                if content[-1] == "progress=end":
                    return
                idx = len(content) - 1
                end_time = "00:00:00"
                while idx > 0:
                    if content[idx].startswith("out_time="):
                        end_time = content[idx].split("=")[1].strip()
                        break
                    idx -= 1
                try:
                    h, m, s = end_time.split(":")
                except Exception:
                    time.sleep(1)
                    continue
                else:
                    h, m, s = end_time.split(":")
                    precent = round(
                        (int(h) * 3600000 + int(m) * 60000 + int(s[:2]) * 1000)
                        * basenum
                        / video_time,
                        2,
                    )
                    if self.precent + 0.1 < 99:
                        self.precent += 0.1
                    else:
                        self._signal(
                            text=config.transobj.get("hebing", "")
                            + f" -> {precent * 100}%"
                        )
                    time.sleep(1)

    # 创建说明txt
    def _create_txt(self) -> None:
        try:
            # Path(self.cfg['novoice_mp4']).unlink(missing_ok=True)
            if not self.cfg["only_video"]:
                with open(
                    self.cfg["target_dir"]
                    + f'/{"readme" if config.defaulelang != "zh" else "文件说明"}.txt',
                    "w",
                    encoding="utf-8",
                    errors="ignore",
                ) as f:
                    f.write(
                        f"""以下是可能生成的全部文件, 根据执行时配置的选项不同, 某些文件可能不会生成, 之所以生成这些文件和素材，是为了方便有需要的用户, 进一步使用其他软件进行处理, 而不必再进行语音导出、音视频分离、字幕识别等重复工作

        *.mp4 = 最终完成的目标视频文件
        {self.cfg['source_language_code']}.m4a|.wav = 原始视频中的音频文件(包含所有背景音和人声)
        {self.cfg['target_language_code']}.m4a = 配音后的音频文件(若选择了保留背景音乐则已混入)
        {self.cfg['source_language_code']}.srt = 原始视频中根据声音识别出的字幕文件
        {self.cfg['target_language_code']}.srt = 翻译为目标语言后字幕文件
        shuang.srt = 双语字幕
        vocal.wav = 原始视频中分离出的人声音频文件
        instrument.wav = 原始视频中分离出的背景音乐音频文件


        如果该项目对你有价值，并希望该项目能一直稳定持续维护，欢迎各位小额赞助，有了一定资金支持，我将能够持续投入更多时间和精力
        捐助地址：https://github.com/jianchang512/pyvideotrans/issues/80

        ====

        Here are the descriptions of all possible files that might exist. Depending on the configuration options when executing, some files may not be generated.

        *.mp4 = The final completed target video file
        {self.cfg['source_language_code']}.m4a|.wav = The audio file in the original video (containing all sounds)
        {self.cfg['target_language_code']}.m4a = The dubbed audio file (if you choose to keep the background music, it is already mixed in)
        {self.cfg['source_language_code']}.srt = Subtitles recognized in the original video
        {self.cfg['target_language_code']}.srt = Subtitles translated into the target language
        shuang.srt = Source language and target language subtitles srt 
        vocal.wav = The vocal audio file separated from the original video
        instrument.wav = The background music audio file separated from the original video


        If you feel that this project is valuable to you and hope that it can be maintained consistently, we welcome small sponsorships. With some financial support, I will be able to continue to invest more time and energy
        Donation address: https://ko-fi.com/jianchang512


        ====

        Github: https://github.com/jianchang512/pyvideotrans
        Docs: https://pyvideotrans.com

                        """
                    )
            # Path(self.cfg['target_dir'] + f'/end.srt').unlink(missing_ok=True)
            # Path(self.cfg['target_dir'] + f'/end.srt.ass').unlink(missing_ok=True)
            # Path(self.cfg['target_dir'] + f'/shuang.srt.ass').unlink(missing_ok=True)
        except:
            pass

    # 开始计时
    def _start_timer(self, stage: str):
        self.execution_times[stage] = {"start": time.time()}

    # 结束计时
    def _end_timer(self, stage: str):
        if stage in self.execution_times:
            self.execution_times[stage]["end"] = time.time()
            self.execution_times[stage]["duration"] = (
                self.execution_times[stage]["end"]
                - self.execution_times[stage]["start"]
            )

    # 获取视频元信息
    def _get_video_data(self, path: str):
        metadata = tools.runffprobe(
            ["-v", "error", "-show_format", "-show_streams", "-of", "json", path]
        )
        data = json.loads(metadata)
        video_stream = None
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break
        if not video_stream:
            raise ValueError(f"No video stream found in file: {path}")
        required_fields = ["width", "height", "codec_name"]
        for field in required_fields:
            if field not in video_stream:
                raise ValueError(f"Video stream is missing required field: {field}")
        video_data = {
            "duration": float(data["format"]["duration"]),
            "size": int(data["format"]["size"]),
            "width": int(video_stream["width"]),
            "height": int(video_stream["height"]),
            "codec": video_stream["codec_name"],
        }
        return video_data
