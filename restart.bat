@echo off
chcp 65001 >nul
echo [1/4] 停止旧进程...
taskkill /F /IM python.exe 2>nul
timeout /t 2 /nobreak >nul

echo [2/4] 构建前端...
cd /d "d:\cursor\project12  漫画画质提升\frontend"
call npm run build
if errorlevel 1 (
    echo [错误] npm build 失败，请检查前端代码
    pause
    exit /b 1
)

echo [3/4] 构建成功！启动 API 服务...
cd /d "d:\cursor\project12  漫画画质提升"
start "" python -m mobi_manga_app.api --host 127.0.0.1 --port 8765

echo [4/4] 等待服务启动...
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8765

echo 完成！浏览器已自动打开。
pause

