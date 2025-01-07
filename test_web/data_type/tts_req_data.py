class TTSReqData:
    def __init__(
        self,
        name: str,
        tts_type: int,
        voice_role: str,
        target_language: str,
        voice_rate: str = "",
        volume: str = "",
        pitch: str = "",
        out_ext: str = "wav", # "mp3" | "wav" | "flac" | "aac" 选其一
        voice_autorate: bool = False,
    ):
        self.name = name
        self.tts_type = tts_type
        self.voice_role = voice_role
        self.target_language = target_language
        self.voice_rate = voice_rate
        self.volume = volume
        self.pitch = pitch
        self.out_ext = out_ext
        self.voice_autorate = voice_autorate