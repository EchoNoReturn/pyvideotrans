import os
from faster_whisper import WhisperModel
from pyannote.audio import Pipeline

# 音频识别和发言人标注
class _audioTranscribeWithSpeaker:
    def __init__(self, model_size="base", device="cpu"):
        """
        :param model_size: Faster-Whisper 模型大小。
        :param device: 运行设备，"cpu" 或 "cuda"。
        :param diarization_model: Pyannote 的发言人分离模型。
        """
        self.model = WhisperModel(model_size, device=device)

        # 加载发言人分离模型
        try:
            self.pipeline = Pipeline.from_pretrained("pyannote/speaker-diarization-3.1",use_auth_token="")
        except Exception as e:
            raise RuntimeError(f"无法加载发言人分离模型：{e}")

    def transcribe_audio(self, audio_path):
        # 音频文件判断是否存在
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"音频文件 {audio_path} 不存在。")

        # 执行发言人分离
        try:
            diarization = self.pipeline(audio_path)
        except Exception as e:
            raise RuntimeError(f"发言人分离失败：{e}")

        # 执行语音转录
        try:
            segments, info = self.model.transcribe(audio_path)
            print(f"总时长: {info.duration} 秒")
            print(f"识别语言: {info.language}")
        except Exception as e:
            raise RuntimeError(f"语音转录失败：{e}")

        # 生成带发言人标注的文本
        transcribed_text = ""
        for segment in segments:
            start, end = segment.start, segment.end
            speaker = None
            speaker_start = None
            speaker_end = None
            for turn, _, speaker_label in diarization.itertracks(yield_label=True):
                if start <= turn.start < end:
                    speaker = speaker_label
                    speaker_start = turn.start
                    speaker_end = turn.end
                    break
            speaker_label = speaker or "未知音色"
            transcribed_text += f"[{speaker_label}Time:{speaker_start}-{speaker_end}] {segment.text} 文本时间区间： {start} - {end}\n"

        return transcribed_text