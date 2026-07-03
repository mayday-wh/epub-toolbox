@echo off
:: 设置窗口为 UTF-8 编码，防止中文乱码
chcp 65001 >nul

:: 切换到当前批处理文件所在的目录
cd /d "%~dp0"

:: ==========================================
:: 【配置区】在这里修改你默认要运行的 Python 文件名
set TARGET_PY=main.py
:: ==========================================

:: 判断是否使用了“拖拽文件”的方式运行
if not "%~1"=="" (
    set TARGET_PY="%~nx1"
)

echo 🚀 正在启动 Python 脚本 (uv run %TARGET_PY%)...
echo.

:: 直接使用 uv 命令，比调用 powershell 更快
uv run %TARGET_PY%

echo.
:: 捕获上一条命令的执行状态
if %errorlevel% neq 0 (
    echo ❌ 运行出错，请检查上方报错信息。
) else (
    echo ✅ 运行结束！
)

echo.
pause