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
            api_key='sk-212dfdbb67b349a281620667e9afdcd6',
            base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
        ).chat.completions.create(
            # options: 
            #       1、 qwen-mt-plus    如果您对翻译质量有较高要求，建议选择qwen-mt-plus模型；
            #       2、 qwen-mt-turbo   如果您希望翻译速度更快或成本更低，建议选择qwen-mt-turbo模型。
            model='qwen-mt-plus',
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
        print("千问AI翻译启动")
        if self.source_code == "auto":
            raise Exception("该翻译引擎不支持自动识别")
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
        new_language = self.map_language(self.target_code)  # 目标语言
        old_language = self.map_language(self.source_code)  # 源语言
        total = 0
        for item in self.text_list:
            if item is not None and 'text' in item:
                text = item['text']
                content = self.openAI(text, old_language, new_language)
                total+=1
                if(total% 5==0):
                    import time
                    time.sleep(1)
                data['text'] = data['text'] + text+ "\n" + content + "\n"
                with open(Path(path),'w',encoding='utf-8') as f:
                    json.dump(data,f,ensure_ascii=False,indent=4)
                item['text'] = content
        data['is_ok'] = True
        with open(Path(path),'w',encoding='utf-8') as f:
            json.dump(data,f,ensure_ascii=False,indent=4)
        return self.text_list
 