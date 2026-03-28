@echo off
echo 安装漫画画质提升工具...
echo.

echo [1/2] 安装基础依赖...
python -m pip install -e . --quiet

echo [2/2] 检查可用模型...
python -m mobi_manga_app.cli list-models

echo.
echo 安装完成！
echo.
echo 使用方法:
echo   python -m mobi_manga_app.cli process "漫画文件" --workspace .work/output
echo.
echo 如需更好的画质，安装 Real-ESRGAN:
echo   pip install realesrgan basicsr
pause
