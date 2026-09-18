@echo off
cd /d "%~dp0"
rem A-Share desktop ticker launcher
rem Order: WorkBuddy venv -> system pythonw. Auto-installs PySide6 if missing.

set "VENV=C:\Users\sheep\.workbuddy-ai\binaries\python\envs\default"
set "PYW=%VENV%\Scripts\pythonw.exe"
set "PYEXE=%VENV%\Scripts\python.exe"

if not exist "%PYW%" set "PYW=pythonw"
if not exist "%PYEXE%" set "PYEXE=python"

"%PYEXE%" -c "import PySide6" >nul 2>&1
if errorlevel 1 (
  echo PySide6 not found. Installing from Aliyun mirror, please wait...
  "%PYEXE%" -m pip install PySide6 -i https://mirrors.aliyun.com/pypi/simple/
  if errorlevel 1 (
    echo.
    echo Install failed. Check your network, or run install.bat manually.
    pause
    exit /b 1
  )
)

start "" "%PYW%" "%~dp0widget.py"
