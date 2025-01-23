import ffmpeg
import os

from Config import Config

# 提取视频中的音频
class _audioExtractor:
    def __init__(self, video_path, audio_path):
        self.video_path = video_path
        self.audio_path = audio_path
        self.ffmpeg_path = Config.get("ffmpeg_path")

    def extract_audio(self):
        """从视频文件中提取音频并保存为 WAV 格式"""
        if not os.path.isfile(self.video_path):
            raise FileNotFoundError(f"视频文件 {self.video_path} 不存在")

        # 输出 ffmpeg 可执行文件的路径
        print(f"FFmpeg 可执行文件路径: {self.ffmpeg_path}")
        
        if not os.path.isfile(self.ffmpeg_path):
            raise FileNotFoundError(f"FFmpeg 可执行文件 {self.ffmpeg_path} 不存在")

        print(f"正在从视频 {self.video_path} 提取音频...")
        try:
            # 使用指定路径的 ffmpeg 提取音频
            ffmpeg.input(self.video_path).output(self.audio_path,y=None).run(cmd=self.ffmpeg_path)
            print(f"音频已成功提取并保存为 {self.audio_path}")
        except ffmpeg.Error as e:
            print(f"提取音频时出错: {e}")

        return self.audio_path

# 示例用法：
if __name__ == "__main__":
    video_path = r"c:/Users/pc/Pictures/1.mp4"  # 视频文件路径
    audio_extractor = _audioExtractor(video_path,"test.wav")
    extracted_audio = audio_extractor.extract_audio()