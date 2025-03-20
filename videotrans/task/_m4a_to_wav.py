import ffmpeg
# pip install ffmpeg-python
def convert_m4a_to_wav(input_m4a, output_wav):
    ffmpeg.input(input_m4a).output(output_wav, ar=16000, ac=1, format='wav').run(overwrite_output=True)