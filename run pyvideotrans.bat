@echo off
:: 切换到当前 .bat 文件所在目录
cd /d %~dp0

:: 激活虚拟环境
call .\.venv\Scripts\activate

:: 运行 Python 脚本
python .\api.py

pause
