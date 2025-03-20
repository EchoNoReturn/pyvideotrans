from zhipuai import ZhipuAI

from videotrans.translator._base import BaseTrans

# pip install zhipuai
class Zhipu(BaseTrans):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
    @staticmethod
    def ZhipuAI(content, old_language, new_language):
        client = ZhipuAI(
            # APIKey
            api_key="de9e6c81a07e4d3dba7632912b451ba8.qKKa7DW1XHR2c739"
        )
        response = client.chat.completions.create(
            model="glm-4-plus",  # 填写需要调用的模型编码
            messages=[
                {
                    "role": "system",
                    "content": f"你是一个多语言翻译专家"
                },
                {
                    "role": "user",
                    "content": f"请将我发送给你的{old_language}内容翻译为{new_language}，仅返回翻译即可，"
                               f"不要提问、不要回答问题、不要确认、不要回复本条内容，从下一行开始翻译\n{content}"
                }
            ]
        )
        return response.choices[0].message.content
    @staticmethod
    def map_language(language_code):
        language_map = {
            "zh-cn": "中文",
            "en": "英文",
            "ja": "日文",
            "ko": "韩文"
        }
        return language_map.get(language_code)
    def run(self):
        print("智谱 ai 翻译启动")
        new_language = self.map_language(self.target_code)
        old_language = self.map_language(self.source_code)
        for item in self.text_list:
            if item is not None and 'text' in item:
                text = item['text']
                if text == '':
                    continue
                item['text'] = self.ZhipuAI(text, old_language, new_language)
        return self.text_list
        