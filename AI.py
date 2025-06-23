import json
from openai import OpenAI


class ContentUpdate:
    def qwen(text):
        print("启用AI纠正...")
        return json.loads(
            OpenAI(
                api_key='sk-4de2c78f40724cbfa57a5ffeb5c55237',
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            ).chat.completions.create(
                # model list : https://help.aliyun.com/zh/model-studio/getting-started/models
                model="qwen-plus",
                messages=[
                    {
                        "role": "system",
                        "content": "你是一名语音转文本纠错专家，请根据以下特征修正识别错误：1) 优先处理同音字/近音字错误（如'期中考试'误为'期终考试'）；2) 修正因连读导致的词语缺失（如'这样子'误为'酱子'）；3) 保留口语化表达但修正明显歧义。仅输出最终修正文本；4) 保持原str格式输出"
                    }, {
                        "role": "user",
                        "content": text
                    }
                ],
                extra_body={
                    "enable_thinking": False
                }
            ).model_dump_json()
        )['choices'][0]['message']['content']

    def deepseek(text):
        return OpenAI(
            base_url='http://127.0.0.1:11434/v1',
            api_key='ollama',
        ).chat.completions.create(
            model="deepseek-r1:7b",
            messages=[
                {
                    "role": "system",
                    "content": "你是一名语音转文本纠错专家，请根据以下特征修正识别错误：1) 优先处理同音字/近音字错误（如'期中考试'误为'期终考试'）；2) 修正因连读导致的词语缺失（如'这样子'误为'酱子'）；3) 保留口语化表达但修正明显歧义。仅输出最终修正文本；4) 严格保持原str格式输出，需保留行号，时间轴，字幕内容等信息并保留换行符。"
                }, {
                    "role": "user",
                    "content": text
                }
            ]
        ).choices[0].message.content