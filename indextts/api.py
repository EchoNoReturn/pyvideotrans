import os
import shutil
import sys
import threading
import time
import warnings

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)
sys.path.append(os.path.join(current_dir, "indextts"))

from flask import Flask, request, send_file, jsonify
from indextts.infer import IndexTTS
from tools.i18n.i18n import I18nAuto
import torch

i18n = I18nAuto(language="zh_CN")
MODE = 'local'
tts = IndexTTS(model_dir="checkpoints", cfg_path="checkpoints/config.yaml")
app = Flask(__name__)

@app.route('/tts', methods=['POST'])
def api_tts():
    start_time = time.time()
    prompt = request.json.get('prompt')
    text = request.json.get('text')
    infer_mode = request.json.get('infer_model')
    file_name = request.json.get('save_file_name')
    file_path = request.json.get('save_file_path')
    output_path = os.path.join(file_path, f"{file_name}.wav")
    if infer_mode == 1:
        tts.infer(prompt, text, output_path)
    else:
        tts.infer_fast(prompt, text, output_path)
    end_time = time.time()
    app.logger.info(f" Interface execution duration: {end_time - start_time:.3f}s")
    return jsonify({
            "code": 0,
            "msg": "success"
        })

if __name__ == "__main__":
    import logging
    app.logger.setLevel(logging.INFO)
    if torch.cuda.is_available():
        app.logger.info(f"Currently using GPU acceleration: {torch.cuda.get_device_name(0)}")
    else:
        app.logger.info("Currently using CPU acceleration")
    app.run(host="127.0.0.1", port=8888, threaded=True)