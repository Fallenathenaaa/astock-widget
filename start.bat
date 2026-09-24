@echo off
cd /d "%~dp0"
rem A-Share desktop ticker launcher
rem
rem Portable mode first: if this folder ships with its own bundled Python
rem (py\pythonw.exe, from the "portable" download), use it directly. No
rem install, no venv, no system Python needed. Everything below is only the
rem fallback for a plain source checkout (run install.bat to build a .venv).
if exist "%~dp0py\pythonw.exe" (
  start "" "%~dp0py\pythonw.exe" "%~dp0widget.py"
  exit /b 0
)
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
  rem Stop if install failed: .venv may exist but pip did not finish,
  rem and falling through would run the whole install a second time.
  if errorlevel 1 exit /b 1
)
if not exist "%PYEXE%" (
  echo.
  echo FAILED: %PYEXE% not found.
  echo Run install.bat manually, or see README.md.
  pause
  exit /b 1
)
rem Same version gate as install.bat: an old .venv (3.8/3.9 from early
rem versions) must not sneak through just because PySide6 happens to import.
rem The range comes from the helper -- do not hardcode it here.
set "HELPER=%~dp0tools\check_python.py"
set "PYFINDER="
for %%C in (py python python3) do (
  if not defined PYFINDER (
    where %%C >nul 2>&1
    if not errorlevel 1 set "PYFINDER=%%C"
  )
)
set "PYMIN="
set "PYMAX="
if defined PYFINDER (
  for /f "tokens=1,2" %%A in ('%PYFINDER% "%HELPER%" --range 2^>nul') do (
    set "PYMIN=%%A"
    set "PYMAX=%%B"
  )
)
rem 兜底：cmd 不会做 shell 命令替换。如果前面的 for /f 没赋值成功，
rem 错误信息就会变成 "needs see - tools\check_python.py --range"（真出过）。
rem 这里给个与 README 一致的兜底字符串。
if not defined PYMIN set "PYMIN=3.10"
if not defined PYMAX set "PYMAX=3.14"
"%PYEXE%" "%~dp0tools\check_python.py"
if errorlevel 1 (
  echo.
  echo FAILED: this .venv uses an unsupported Python version.
  echo          This project needs Python %PYMIN% - %PYMAX%.
  echo.
  echo Fix it by running install.bat -- it will tell you exactly what to do.
  pause
  exit /b 1
)

rem Deps present? Not a version question -- just "can it import PySide6".
rem If not, hand the whole job back to install.bat instead of inventing a
rem second, weaker install path here (it used to try one single mirror and
rem give up, so a mirror outage looked like "the program is broken").
"%PYEXE%" -c "import PySide6" >nul 2>&1
if errorlevel 1 (
  echo.
  echo Dependencies missing. Running install.bat ...
  call "%~dp0install.bat"
  if errorlevel 1 exit /b 1
)
"%PYEXE%" -c "import PySide6" >nul 2>&1
if errorlevel 1 (
  echo.
  echo FAILED: PySide6 is still missing after install.bat.
  echo See the error above, or run install.bat yourself and read its output.
  pause
  exit /b 1
)
if not exist "%PYW%" set "PYW=%PYEXE%"
start "" "%PYW%" "%~dp0widget.py"
