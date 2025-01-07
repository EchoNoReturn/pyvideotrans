import gradio as gr


def handle(video_data):
    # 这里是具体的处理逻辑
    return video_data


def get_gradio_demo():
    with gr.Blocks() as demo:
        with gr.Row():
            with gr.Column():
                video_input = gr.Video(label="Video Input")
                run_button = gr.Button(value="Run")
            with gr.Column():
                video_output = gr.Video(label="Video Output")
        run_button.click(fn=handle, inputs=video_input, outputs=video_output)
        return demo


if __name__ == "__main__":
    demo = get_gradio_demo()
    demo.launch()
