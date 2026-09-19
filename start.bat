@echo off
cd /d "%~dp0"
rem A-Share desktop ticker launcher
rem
rem Use only the interpreter in this project's own .venv; run
rem install.bat first if it is missing. Do not guess which system
rem python has PySide6: a wrong guess starts a process with missing
rem deps, and since pythonw has no console the window never appears
rem and the error is never shown.
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
