from openai import OpenAI,RateLimitError, APIError, Timeout
from videotrans.translator._base import BaseTrans
import time


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
    def openAI(content, old_language, new_language, retries=5, delay=5):
        for attempt in range(retries):
            try:
                response = OpenAI(
                    api_key='sk-212dfdbb67b349a281620667e9afdcd6',
                    base_url='https://dashscope.aliyuncs.com/compatible-mode/v1',
                ).chat.completions.create(
                    model='qwen-mt-plus',
                    messages=[
                        {"role": "user", "content": content}
                    ],
                    extra_body={
                        "translation_options": {
                            "source_lang": old_language,
                            "target_lang": new_language,
                        }
                    }
                )
                return response.choices[0].message.content
            except RateLimitError as e:
                print(f"[重试] 第 {attempt+1}/{retries} 次请求过多：{e}，等待 {delay} 秒重试...")
                time.sleep(delay)
            except (APIError, Timeout) as e:
                print(f"[重试] 第 {attempt+1}/{retries} 次 API 错误或超时：{e}，等待 {delay} 秒重试...")
                time.sleep(delay)
            except Exception as e:
                print(f"[重试] 第 {attempt+1}/{retries} 次遇到未知错误：{e}，等待 {delay} 秒重试...")
                time.sleep(delay)
        raise Exception("超过最大重试次数，翻译失败")

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

        from flashtext import KeywordProcessor
        keyword_processor = KeywordProcessor()
        from videotrans.util.http_request import http_request
        endpoint = "/py/keyword/all"
        dict = http_request.send_request(endpoint=endpoint)
        if dict['data'] is not None:
            for item in dict['data']:
                keyword_processor.add_keyword(item['data'], '*' * len(item['data']))

        import re
        srt_file_path = os.path.join(project_root, "apidata", uuid, "zh-cn.srt")
        time_pattern = re.compile(r'^\d{2}:\d{2}:\d{2},\d{3} -->')
        with open(srt_file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        new_lines = []
        for line in lines:
            line_strip = line.strip()
            if line_strip.isdigit() or time_pattern.match(line_strip) or line_strip == '':
                new_lines.append(line)
            else:
                try:
                    line = keyword_processor.replace_keywords(line)
                except Exception as e:
                    import datetime
                    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}替换出错：{e}")
                    raise Exception("替换出错，请检查输入")
                new_lines.append(line)
        with open(srt_file_path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)


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
                text = keyword_processor.replace_keywords(item['text'])
                content = keyword_processor.replace_keywords(self.openAI(text, old_language, new_language))
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
 