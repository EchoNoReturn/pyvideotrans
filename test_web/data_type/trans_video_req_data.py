class TransVideoReqData(object):
    def __init__(
        self,
        name: str,
        recogn_type: int,
        split_type: str,
        model_name: str,
        detect_language: str,
        translate_type: int,
        source_language: str,
        target_language: str,
        tts_type: int,
        voice_role: str,
        voice_rate: str,
        volume: str,
        pitch: str,
        subtitle_type: int,
        voice_autorate: bool = True,
        video_autorate: bool = True,
        is_separate: bool = False,
        back_audio: str = '',
        append_video: bool = False,
        is_cuda: bool = False,
    ):
        self.name = name
        """
        文件的绝对路径或者名称
        """
        self.recogn_type = recogn_type
        self.split_type = split_type
        self.model_name = model_name
        self.detect_language = detect_language
        self.translate_type = translate_type
        self.source_language = source_language
        self.target_language = target_language
        self.tts_type = tts_type
        self.voice_role = voice_role
        self.voice_rate = voice_rate
        self.volume = volume
        self.pitch = pitch
        self.subtitle_type = subtitle_type
        self.voice_autorate = voice_autorate
        self.video_autorate = video_autorate
        self.is_separate = is_separate
        self.back_audio = back_audio
        self.append_video = append_video
        self.is_cuda = is_cuda
