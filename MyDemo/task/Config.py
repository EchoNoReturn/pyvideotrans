import os

# 全局配置类
class Config:
    # 默认全局配置
    _global_config = {
        "ffmpeg_path": os.path.join(os.getcwd(), "resources", "ffmpeg", "ffmpeg.exe"),
    }
    
    # 获取配置项的值
    @classmethod
    def get(cls, key, default=None):
        return cls._global_config.get(key, default)
  
    # 设置配置项的值
    @classmethod
    def set(cls, key, value):
        cls._global_config[key] = value
        
    # 显示当前配置
    @classmethod
    def show(cls):
        return cls._global_config
