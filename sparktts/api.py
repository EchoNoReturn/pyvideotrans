import time
from flask import Flask, request, jsonify
import os
import torch
import logging
import soundfile as sf
import io
from pathlib import Path
from cli.SparkTTS import SparkTTS
from pydub import AudioSegment

app = Flask(__name__)

log_dir = os.path.join(os.path.dirname(__file__), 'logs')
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'api.log')

from logging.handlers import RotatingFileHandler
file_handler = RotatingFileHandler(
    log_file, 
    maxBytes=1024 * 1024 * 10,
    backupCount=10
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)

console_handler = logging.StreamHandler()
console_handler.setFormatter(logging.Formatter(
    '[%(asctime)s] %(levelname)s %(message)s'
))
app.logger.addHandler(console_handler)


def initialize_model(model_dir="pretrained_models/Spark-TTS-0.5B", device=0):
    if torch.cuda.is_available():
        app.logger.info("Using CUDA")
        device = torch.device(f"cuda:{device}")
    else:
        device = torch.device("cpu")
        app.logger.info("GPU acceleration not available, using CPU")
    model = SparkTTS(model_dir, device)
    return model

model = initialize_model()

@app.route('/tts', methods=['POST'])
def tts():
    start_time = time.time()
    try:
        if request.is_json:
            data = request.json
        else:
            data = request.form
        prompt_speech_path = None
        audio_path = data.get('audio_path')
        if audio_path and os.path.exists(audio_path):
            prompt_speech_path = Path(audio_path)
        text = data.get('text')
        prompt_text = data.get('prompt_text')
        save_dir = data.get('save_path')
        
        os.makedirs(save_dir, exist_ok=True)
        timestamp = data.get("file_save_name")
        file_suffix = data.get('file_sava_suffix', 'mp3')
        save_path = os.path.join(save_dir, f"{timestamp}.{file_suffix}")

        with torch.no_grad():
            wav = model.inference(
                text,
                prompt_speech_path,
                prompt_text,
            )

            supported_formats = ['mp3', 'wav', 'ogg', 'flac', 'm4a', 'wma']
            
            if file_suffix.lower() not in supported_formats:
                app.logger.warning(f"Unsupported audio format: {file_suffix}， will use MP3 format")
                file_suffix = 'mp3'
                save_path = os.path.join(save_dir, f"{timestamp}.{file_suffix}")
            
            temp_wav_io = io.BytesIO()
            sf.write(temp_wav_io, wav, samplerate=16000, format='WAV')
            temp_wav_io.seek(0)
            
            audio_segment = AudioSegment.from_wav(temp_wav_io)
            
            export_params = {}
            if file_suffix.lower() == 'mp3':
                export_params = {'bitrate': '192k'}
            elif file_suffix.lower() == 'ogg':
                export_params = {'codec': 'libvorbis', 'quality': '5'}
            elif file_suffix.lower() == 'flac':
                export_params = {'compression': 8}
            elif file_suffix.lower() == 'm4a':
                export_params = {'codec': 'aac', 'bitrate': '192k'}
            
            audio_segment.export(save_path, format=file_suffix.lower(), **export_params)
            app.logger.info(f"The audio has been saved in {file_stuffix} format")

        total_time = round(time.time() - start_time, 3)
        app.logger.info(f"Request total processing time: {total_time}s")
        return jsonify({
            "status": "success",
            "total_time": total_time,
            "audio_path": save_path
            }), 200

    except Exception as e:
        app.logger.error(f"Error during TTS processing: {str(e)}", exc_info=True)
        return jsonify({"error": "Internal Server Error"}), 500

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=5000)