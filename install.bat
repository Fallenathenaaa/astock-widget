@echo off
cd /d "%~dp0"
rem One-time dependency install (run this on every new machine)
rem
rem Deps go into this project's own .venv: no pollution of the global
rem Python. The .venv itself is NOT portable -- it records this machine's
rem absolute paths and Python version, so copy the source folder only and
rem run this script again on the new machine.

set "VENV=%~dp0.venv"
set "PYEXE=%VENV%\Scripts\python.exe"
set "PYCMD="

rem ---- pick an interpreter whose version this project actually supports ----
rem requirements.txt says Python 3.10 - 3.14. Building the venv with 3.9 or
rem 3.15 would "succeed" and then fail much later inside pip with a message
rem that has nothing to do with the real cause.
if not exist "%PYEXE%" (
  where py >nul 2>&1
  if not errorlevel 1 (
    for %%V in (3.14 3.13 3.12 3.11 3.10) do (
      if not defined PYCMD (
        py -%%V -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 1)" >nul 2>&1
        if not errorlevel 1 set "PYCMD=py -%%V"
      )
    )
  )
  if not defined PYCMD (
    python -c "import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] <= (3, 14) else 1)" >nul 2>&1
    if not errorlevel 1 set "PYCMD=python"
  )
)

if not exist "%PYEXE%" (
  if not defined PYCMD (
    echo.
    echo FAILED: no supported Python found. This project needs 3.10 - 3.14.
    echo Install one first: https://www.python.org/downloads/
    echo If it is installed, make sure "py" or "python" is on your PATH.
    pause
    exit /b 1
  )
  echo Creating virtual environment with: %PYCMD%
  %PYCMD% -m venv "%VENV%"
)

if not exist "%PYEXE%" (
  echo.
  echo FAILED: cannot create the virtual environment.
  echo Install Python 3.10 - 3.14 first: https://www.python.org/downloads/
  pause
  exit /b 1
)

echo Python version in .venv:
"%PYEXE%" -c "import sys; print('  %d.%d.%d' % sys.version_info[:3])"

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
