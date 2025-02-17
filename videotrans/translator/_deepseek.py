import re
from openai import OpenAI
from videotrans.translator._base import BaseTrans


class Deepseek(BaseTrans):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @staticmethod
    def contains_chinese(text):
        pattern = re.compile('[\u4e00-\u9fa5]')
        if bool(pattern.search(text)):
            return True
        elif ":" in text:
            return True
        elif "：" in text:
            return True
        return False

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
        if self.source_code == 'auto':
            old_language = ''
        else:
            old_language = self.map_language(self.source_code)
        new_language = self.map_language(self.target_code)
        for item in self.text_list:
            if item is not None and 'text' in item:
                text = item['text']
                content = self.openAI(text, old_language, new_language)
                if self.contains_chinese(content):
                    item['text'] = ''
                else:
                    item['text'] = content
        return self.text_list
