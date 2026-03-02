@echo off
chcp 65001 >nul
echo ================================================
echo 🛑 停止 Mini-RAG 服务器
echo ================================================
echo.
taskkill /F /IM python.exe 2>nul
if %errorlevel%==0 (
    echo ✅ 服务器已停止
) else (
    echo ℹ️ 没有找到运行中的服务器进程
)
echo.
pause