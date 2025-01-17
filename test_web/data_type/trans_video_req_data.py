class TransVideoReqData(object):
    def __init__(
        self,
        name: str,
        is_separate: bool = False,
        back_audio: str = '',
        
        recogn_type: int = 0,
        split_type: str = 'all',
        model_name: str = 'tiny',
        is_cuda: bool = False,
        subtitles: str = '',
        
        translate_type: int = 0,
        target_language: str = 'zh-cn',
        source_language: str = 'auto',
        tts_type: int = 0,
        voice_role: str = 'zh-CN-YunjianNeural',
        voice_rate: str = "+0%",
        voice_autorate: bool = False,
        video_autorate: bool = False,
        volume: str = "+0%",
        pitch: str = "+0Hz",
        
        subtitle_type: int = 0,
        append_video: bool = False,
        
        is_batch: bool = True,
        app_mode: str = 'biaozhun',
        only_video: bool = False
    ):
        # 通用
        self.name = name
        self.is_separate = is_separate
        self.back_audio = back_audio
        
        # 识别
        self.recogn_type = recogn_type
        self.split_type = split_type
        self.model_name = model_name
        self.is_cuda = is_cuda
        self.subtitles = subtitles
        
        # 翻译
        self.translate_type = translate_type
        self.target_language = target_language
        self.source_language = source_language
        
        # 配音
        self.tts_type = tts_type
        self.voice_role = voice_role
        # self.voice_rate = voice_rate
        self.voice_autorate = voice_autorate
        self.video_autorate = video_autorate
        self.volume = volume
        self.pitch = pitch
        
        # 字幕类型
        self.subtitle_type = subtitle_type
        self.append_video = append_video
        
        # 扩展功能
        self.is_batch = is_batch
        self.app_mode = app_mode
        self.only_video = only_video
