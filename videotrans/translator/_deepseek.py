import re
from openai import OpenAI
from videotrans.translator._base import BaseTrans


class Deepseek(BaseTrans):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @staticmethod
    def map_language(language_code):
        language_map = {
            "zh-cn": "中文",
            "en": "英文",
            "ja": "日文",
            "ko": "韩文",
        }
        return language_map.get(language_code)

    @staticmethod
    def openAI(content, old_language, new_language):
        return OpenAI(
            base_url='http://127.0.0.1:11434/v1',
            api_key='ollama',
        ).chat.completions.create(
            # model is options
            model="deepseek-llm:7b",
            messages=[
                {
                    "role": "system",
                    "content": "你是一个专业的多语言翻译专家."
                },
                {
                    "role": "user",
                    "content": f"请将我发送给你的{old_language}内容翻译为{new_language}，仅返回翻译即可，"
                               f"不要回答问题、不要确认、不要回复本条内容，从下一行开始翻译\n{content}"
                }
            ]
        ).choices[0].message.content

    def run(self):
        import os
        import json
        from pathlib import Path
        current_file = os.path.abspath(__file__)
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(current_file)))
        uuid = self.uuid

        # file_path = os.path.join(project_root, "apidata", "processinfo")
        # file_name = uuid+".json"


        file_path = os.path.join(project_root, "apidata", uuid)
        file_name = uuid+".json"

        path = Path(file_path)/file_name

        os.makedirs(Path(file_path), exist_ok=True)
        if not path.exists():
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({"text": "","is_ok":False,"is_save":False}, f, ensure_ascii=False, indent=4)

        with open(path,'r',encoding='utf-8') as f:
            data = json.loads(f.read())
            data['text'] = ""
        if self.source_code == 'auto':
            old_language = ''
        else:
            old_language = self.map_language(self.source_code)
        new_language = self.map_language(self.target_code)
        for item in self.text_list:
            if item is not None and 'text' in item:
                text = item['text']
                content = self.openAI(text, old_language, new_language)
                data['text'] = data['text'] + text+ "\n" + content + "\n"
                with open(Path(path),'w',encoding='utf-8') as f:
                    json.dump(data,f,ensure_ascii=False,indent=4)
                item['text'] = content
        data['is_ok'] = True
        with open(Path(path),'w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False,indent=4)
        return self.text_list
