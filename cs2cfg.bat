@echo off
REM cs2-autoconfig launcher.
REM   cs2cfg.bat              open the window
REM   cs2cfg.bat scan         report detected hardware
REM   cs2cfg.bat plan         dry run, nothing written
REM   cs2cfg.bat apply        write the changes
REM
REM Candidates are validated by running them, not by asking `where`. Windows
REM ships a python.exe stub in WindowsApps that sits on PATH, does nothing but
REM advertise the Store, and would otherwise be picked first.

setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "PY="
set "PYARGS="

call :probe "py" "-3"
if not defined PY (
    for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do call :probe "%%~fD\python.exe" ""
)
if not defined PY (
    for /d %%D in ("%ProgramFiles%\Python3*") do call :probe "%%~fD\python.exe" ""
)
if not defined PY (
    for /d %%D in ("%ProgramFiles(x86)%\Python3*") do call :probe "%%~fD\python.exe" ""
)
if not defined PY call :probe "python" ""
if not defined PY call :probe "python3" ""

if not defined PY goto :nopython

if "%~1"=="" (
    "%PY%" %PYARGS% -m cs2cfg gui
) else (
    "%PY%" %PYARGS% -m cs2cfg %*
)
set "RC=%ERRORLEVEL%"

REM Only hold the window open on failure, and only when double-clicked.
if not "%RC%"=="0" if "%~1"=="" pause
endlocal & exit /b %RC%

:probe
REM %1 = executable, %2 = extra argument (may be empty)
if defined PY exit /b 0
"%~1" %~2 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
set "PY=%~1"
set "PYARGS=%~2"
exit /b 0

:nopython
echo.
echo   No usable Python 3.9+ was found.
echo.
echo   Install it with:
echo       winget install -e --id Python.Python.3.13
echo.
echo   If Python is installed but not on PATH, run the module directly:
echo       "C:\path\to\python.exe" -m cs2cfg scan
echo.
pause
endlocal & exit /b 1
