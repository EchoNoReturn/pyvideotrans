import whisper
import pyaudio
import numpy as np
import torch

# 设置 Whisper 模型
device = "cuda" if torch.cuda.is_available() else "cpu"
model = whisper.load_model("small", device=device)  # 使用更小的模型以节省内存

# 设置音频流参数
FORMAT = pyaudio.paInt16 # 使用 16 位整数的音频格式
CHANNELS = 1 # 单声道
RATE = 16000  # 常见的采样率 16000 Hz
CHUNK = 1024  # 每块音频的大小 1024 字节
THRESHOLD = 500  # 音量阈值，用于检测是否有声音
AUDIO_BUFFER = []  # 保存音频数据的缓冲区
TRANSLATED_TEXTS = []  # 保存翻译结果

def translate_audio(audio_data):
    print("音频数据: ")
    print(audio_data) # 打印音频数据
    """将音频数据翻译为文本"""
    try:
        # 调用 Whisper 进行翻译 (翻译任务) 禁用半精度浮点数
        result = model.transcribe(audio_data, task="translate", fp16=False)

        print(result) # 打印翻译结果
        # 获取翻译结果并去除首尾空格
        translated_text = result["text"].strip()
        
        # 打印翻译结果
        if translated_text:
            print(f"翻译结果：{translated_text}")
            # 将翻译结果添加到列表中 (有效翻译)
            TRANSLATED_TEXTS.append(translated_text)
    except Exception as e:
        print(f"翻译错误：{str(e)}")

def audio_stream_callback(in_data, frame_count, time_info, status):
    """音频流回调函数"""
    global AUDIO_BUFFER
    
    # 检测音量
    audio_chunk = np.frombuffer(in_data, dtype=np.int16)
    amplitude = np.amax(np.abs(audio_chunk))
    if amplitude > THRESHOLD:
        # 将音频数据存入缓冲区
        AUDIO_BUFFER.extend(audio_chunk)
        
        # 如果缓冲区数据足够，进行翻译
        if len(AUDIO_BUFFER) >= RATE * 2:  # 5 秒的音频数据
            audio_data = np.array(AUDIO_BUFFER, dtype=np.int16)
            audio_data = audio_data.astype(np.float32) / 32768.0  # 归一化
            
            # 执行翻译
            translate_audio(audio_data)
            
            # 重置缓冲区
            AUDIO_BUFFER = []
    
    return (in_data, pyaudio.paContinue)

def main():
    """主函数"""
    # 初始化 PyAudio
    p = pyaudio.PyAudio()
    
    # 打开音频流 设置参数并指定回调函数
    stream = p.open(
        format=FORMAT,
        channels=CHANNELS,
        rate=RATE,
        input=True,
        frames_per_buffer=CHUNK,
        stream_callback=audio_stream_callback
    )
    
    # 开始录音
    print("开始实时音频翻译...按下 Ctrl+C 停止。")
    stream.start_stream()
    
    try:
        # 等待信号中断
        while stream.is_active():
            pass
    except KeyboardInterrupt:
        print("停止音频翻译。")
    
    # 停止和关闭流
    stream.stop_stream()
    stream.close()
    p.terminate()

if __name__ == "__main__":
    main()