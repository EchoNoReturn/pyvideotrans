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
            model="glm-4-flash",  # 填写需要调用的模型编码
            messages=[
                {
                    "role": "system",
                    "content": f"你是一个多语言翻译专家"
                            f"同时作为翻译专家，需将原文翻译成具有信达雅标准的译文。"
                },
                {
                    "role": "user",
                    "content": f"请将我发送给你的{old_language}内容翻译为{new_language}，仅返回翻译即可，不要提问、不要回答问题、不要确认、不要有提示词、不要回复本条内容，不要返回带有{old_language}的字符语句，确保逐句翻译，不要遗漏任何部分,从下一行开始翻译\n{content}"
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
                json.dump({"text": ""}, f, ensure_ascii=False, indent=4)

        with open(path,'r',encoding='utf-8') as f:
            data = json.loads(f.read())
            data['text'] = ""
        new_language = self.map_language(self.target_code)
        old_language = self.map_language(self.source_code)
        for item in self.text_list:
            if item is not None and 'text' in item:
                text = item['text']
                # print(text)
                if text == '':
                    continue
                new_text=self.ZhipuAI(text, old_language, new_language)
                data['text'] = data['text'] + text+ "\n" + new_text + "\n"
                with open(Path(path),'w',encoding='utf-8') as f:
                    json.dump(data,f,ensure_ascii=False,indent=4)
                item['text'] = new_text
        return self.text_list
        