@echo off
cd /d "%~dp0"
rem A-Share desktop ticker launcher
rem
rem 只用本项目 .venv 里的解释器；没有就先跑 install.bat 装。
rem 不再猜系统里哪个 python 装过 PySide6 —— 猜错了会启一个缺依赖的进程，
rem 然后窗口不出现、报错也不显示（pythonw 没有控制台）。

set "VENV=%~dp0.venv"
set "PYW=%VENV%\Scripts\pythonw.exe"
set "PYEXE=%VENV%\Scripts\python.exe"

if not exist "%PYEXE%" (
  echo.
  echo Not installed yet. Running install.bat first ...
  call "%~dp0install.bat"
)

if not exist "%PYEXE%" (
  echo.
  echo FAILED: %PYEXE% not found.
  echo Run install.bat manually, or see README.md.
  pause
  exit /b 1
)

"%PYEXE%" -c "import PySide6" >nul 2>&1
if errorlevel 1 (
  echo PySide6 missing. Installing from requirements.txt ...
  "%PYEXE%" -m pip install -r "%~dp0requirements.txt" -i https://mirrors.aliyun.com/pypi/simple/
  if errorlevel 1 (
    echo.
    echo Install failed. Check your network, or run install.bat manually.
    pause
    exit /b 1
  )
)

if not exist "%PYW%" set "PYW=%PYEXE%"
start "" "%PYW%" "%~dp0widget.py"
