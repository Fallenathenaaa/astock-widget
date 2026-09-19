@echo off
cd /d "%~dp0"
rem One-time dependency install (use this on a new machine)
rem
rem Deps go into this project's own .venv: no pollution of the global
rem Python, and the folder can be copied to another machine as is.

set "VENV=%~dp0.venv"
set "PYEXE=%VENV%\Scripts\python.exe"

if not exist "%PYEXE%" (
  echo Creating virtual environment in .venv ...
  where py >nul 2>&1
  if not errorlevel 1 (
    py -3 -m venv "%VENV%"
  ) else (
    python -m venv "%VENV%"
  )
)

if not exist "%PYEXE%" (
  echo.
  echo FAILED: cannot create the virtual environment.
  echo Install Python 3.10 - 3.14 first: https://www.python.org/downloads/
  pause
  exit /b 1
)

echo Installing dependencies from requirements.txt ...
"%PYEXE%" -m pip install -r "%~dp0requirements.txt" -i https://mirrors.aliyun.com/pypi/simple/

if errorlevel 1 (
  echo.
  echo Mirror failed, retrying with the official index ...
  "%PYEXE%" -m pip install -r "%~dp0requirements.txt"
)

if errorlevel 1 (
  echo.
  echo FAILED. In China try another mirror:
  echo   "%PYEXE%" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
) else (
  echo.
  echo Done. You can now run start.bat
)
pause
