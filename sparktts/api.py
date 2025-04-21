from flask import Flask, request, jsonify
import os
import torch
import soundfile as sf
from datetime import datetime
import tempfile
from werkzeug.utils import secure_filename
from pathlib import Path
from cli.SparkTTS import SparkTTS

app = Flask(__name__)

def initialize_model(model_dir="pretrained_models/Spark-TTS-0.5B", device=0):
    """Load the model once at the beginning."""
    if torch.cuda.is_available():
        device = torch.device(f"cuda:{device}")
    else:
        device = torch.device("cpu")
    model = SparkTTS(model_dir, device)
    return model

model = initialize_model()

@app.route('/tts', methods=['POST'])
def tts():
    try:
        # 检查是否有文件上传
        prompt_speech_path = None
        if 'audio_file' in request.files:
            audio_file = request.files['audio_file']
            if audio_file.filename != '':
                # 保存上传的音频文件到临时目录
                filename = secure_filename(audio_file.filename)
                temp_dir = tempfile.mkdtemp()
                temp_path = os.path.join(temp_dir, filename)
                audio_file.save(temp_path)
                prompt_speech_path = Path(temp_path)
                app.logger.info(f"Received audio file: {filename}, saved to {temp_path}")
        
        # 获取表单或JSON数据
        if request.is_json:
            data = request.json
        else:
            data = request.form
            
        text = data.get('text')
        prompt_text = data.get('prompt_text')
        save_dir = data.get('save_path')

        app.logger.info(f"Received TTS request with text: {text}")

        os.makedirs(save_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        save_path = os.path.join(save_dir, f"{timestamp}.wav")

        with torch.no_grad():
            app.logger.info("Starting model inference...")
            wav = model.inference(
                text,
                prompt_speech_path,
                prompt_text,
                gender,
                pitch,
                speed,
            )
            sf.write(save_path, wav, samplerate=16000)
            
        # 如果使用了临时目录，清理它
        if prompt_speech_path and os.path.dirname(prompt_speech_path) == temp_dir:
            try:
                os.remove(prompt_speech_path)
                os.rmdir(temp_dir)
                app.logger.info(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                app.logger.warning(f"Failed to clean up temporary files: {e}")

        app.logger.info(f"Audio saved at: {save_path}")
        return jsonify({"audio_path": save_path})
    except Exception as e:
        # Log the exception
        app.logger.error(f"Error during TTS processing: {e}")
        return jsonify({"error": "Internal Server Error"}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)