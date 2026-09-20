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
rem Building the venv with 3.9 or 3.15 would "succeed" and then fail much later
rem inside pip with a message that has nothing to do with the real cause.
rem
rem The supported range lives in tools\check_python.py only. Do NOT copy the
rem version list into this file -- if it is duplicated here, bumping it to 3.15
rem later means editing two places and they will drift apart.
set "HELPER=%~dp0tools\check_python.py"
set "PYCMD="
if not exist "%PYEXE%" (
  where py >nul 2>&1
  if not errorlevel 1 (
    for /f "delims=" %%P in ('py "%HELPER%" --find 2^>nul') do set "PYCMD=%%P"
  )
  if not defined PYCMD (
    where python >nul 2>&1
    if not errorlevel 1 (
      for /f "delims=" %%P in ('python "%HELPER%" --find 2^>nul') do set "PYCMD=%%P"
    )
  )
  if not defined PYCMD (
    where python3 >nul 2>&1
    if not errorlevel 1 (
      for /f "delims=" %%P in ('python3 "%HELPER%" --find 2^>nul') do set "PYCMD=%%P"
    )
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

rem ---- also gate an EXISTING .venv ----
rem Picking a good interpreter only when the venv does not exist yet is not
rem enough: an upgrading user already has .venv, and early versions of this
rem project allowed Python 3.8+. A 3.8/3.9 venv would be reused as is --
rem install goes green, start only checks "import PySide6" (which an old env
rem may well have), and the 3.10-3.14 range in the README becomes a lie.
rem Report the problem instead of silently reusing it (never delete a user's
rem .venv behind their back).
"%PYEXE%" "%~dp0tools\check_python.py"
if errorlevel 1 (
  echo.
  echo FAILED: this .venv uses an unsupported Python version.
  echo          This project needs Python 3.10 - 3.14.
  echo.
  echo To fix it (three steps, about one minute):
  echo   1. Close this window.
  echo   2. Delete the ".venv" folder in this directory.
  echo   3. Double-click install.bat again.
  echo.
  echo Nothing else is touched: stocks.json, backups and logs all stay as they are.
  echo (The old .venv is not deleted automatically -- that is your call.)
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
  echo.
  pause
  exit /b 1
)
echo.
echo Done. You can now run start.bat
pause
exit /b 0
