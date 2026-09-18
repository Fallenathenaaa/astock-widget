@echo off
cd /d "%~dp0"
rem One-time dependency install (use this on a new machine)

set "VENV=C:\Users\sheep\.workbuddy-ai\binaries\python\envs\default"
set "PYEXE=%VENV%\Scripts\python.exe"
if not exist "%PYEXE%" set "PYEXE=python"

echo Installing PySide6 from Aliyun mirror...
"%PYEXE%" -m pip install PySide6 -i https://mirrors.aliyun.com/pypi/simple/

if errorlevel 1 (
  echo.
  echo FAILED. If you are in China, try another mirror:
  echo   "%PYEXE%" -m pip install PySide6 -i https://pypi.tuna.tsinghua.edu.cn/simple
) else (
  echo.
  echo Done. You can now run start.bat
)
pause
