from openai import OpenAI

from videotrans.translator._base import BaseTrans


# local install openai SDK : pip install -U openai

class Qwen(BaseTrans):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @staticmethod
    def map_language(language_code):
        """
        中文: Chinese  
        英语: English
        日语: Japanese  
        韩语: Korean
        """
        language_map = {
            "zh-cn": "Chinese",
            "en": "English",
            "ja": "Japanese",
            "ko": "Korean"
        }
        return language_map.get(language_code)

    @staticmethod
    def openAI(content, old_language, new_language):
        return OpenAI(
            # https://bailian.console.aliyun.com/#/model-market/detail/qwen-mt-turbo
            api_key='sk-f6965dc7766b4b8e84c868dffac30425',
            base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
        ).chat.completions.create(
            # options: 
            #       1、 qwen-mt-plus    如果您对翻译质量有较高要求，建议选择qwen-mt-plus模型；
            #       2、 qwen-mt-turbo   如果您希望翻译速度更快或成本更低，建议选择qwen-mt-turbo模型。
            model='qwen-mt-turbo',
            messages=[
                {
                    "role": "user",
                    "content": content
                }
            ],
            extra_body={
                "translation_options": {
                    "source_lang": old_language,
                    "target_lang": new_language,
                }
            }
        ).choices[0].message.content

    def run(self):
        new_language = self.map_language(self.target_code)  # 目标语言
        old_language = self.map_language(self.source_code)  # 源语言
        for item in self.text_list:
            if item is not None and 'text' in item:
                text = item['text']
                content = self.openAI(text, old_language, new_language)
                item['text'] = content
        return self.text_list
