import torch
import base64
import uvicorn
from fastapi import FastAPI, Request
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess
from pydantic import BaseModel

# 初始化ASR模型
# 该模型用于语音识别，包括语音信号的处理和转换为文本
model = AutoModel(
    model="iic/SenseVoiceSmall",
    trust_remote_code=True,
    remote_code="./model.py",
    vad_model="fsmn-vad",
    vad_kwargs={
        "max_single_segment_time": 30000
        },
    device="cuda:0",
)

# 定义ASR数据模型，用于接收POST请求中的数据
class ASRItem(BaseModel):
    wav : str # 输入音频

# 创建FastAPI实例
app = FastAPI()

# 定义POST请求的处理函数
@app.post("/asr")
def asr(request: Request,item: ASRItem):
    try:
        # 将Base64编码的音频数据解码并保存为文件
        data = base64.b64decode(item.wav)
        with open("test.wav", "wb") as f:
            f.write(data)
        language = request.headers.get("language") or "auto"
        language = "zn" if language == "zh" else language
        # 使用模型进行语音识别
        res = model.generate(
                        "test.wav", 
                        language=language,  # "zn", "en", "yue", "ja", "ko", "nospeech"
                        use_itn=True,
                        batch_size_s=60,
                        merge_vad=True,
                        merge_length_s=15
                        )
        
        # 对识别结果进行后处理
        text = rich_transcription_postprocess(res[0]["text"])
        
        # 成功响应
        result_dict = {
            "code": 0,
            "msg": "ok",
            "res": text
            }
    except Exception as e:
        # 异常响应
        result_dict = {
            "code": 1,
            "msg": str(e)
            }
    return result_dict

# 主函数，用于启动FastAPI服务
if __name__ == '__main__':
    # uvicorn.run(app, host='0.0.0.0', port=10086)
    uvicorn.run(app, host='127.0.0.1', port=10086) # 本地服务