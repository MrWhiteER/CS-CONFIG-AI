@echo off
REM One command to run the desktop application from source.
REM
REM   dev.bat            open the app
REM   dev.bat test       run the test suite
REM   dev.bat build      produce dist\cs2cfg.exe
REM
REM Candidates are validated by running them: Windows ships a python.exe stub
REM in WindowsApps that sits on PATH and only advertises the Store.

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
if not defined PY call :probe "python" ""
if not defined PY goto :nopython

if /i "%~1"=="test" (
    "%PY%" %PYARGS% -m unittest discover -s tests
    goto :done
)
if /i "%~1"=="build" (
    "%PY%" %PYARGS% -m pip install --quiet --disable-pip-version-check pyinstaller pywebview
    "%PY%" %PYARGS% -m PyInstaller --noconfirm cs2cfg.spec
    echo.
    echo Built: %~dp0dist\"CS2 Launcher.exe"  ^(app^)
    echo        %~dp0dist\cs2cfg.exe          ^(command line^)
    goto :done
)

REM Make sure the desktop window has what it needs before opening it.
"%PY%" %PYARGS% -c "import webview" >nul 2>&1
if errorlevel 1 (
    echo Installing the desktop window dependency ^(pywebview^)...
    "%PY%" %PYARGS% -m pip install --quiet --disable-pip-version-check pywebview
)

"%PY%" %PYARGS% -m cs2cfg desktop %*

:done
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" if "%~1"=="" pause
endlocal & exit /b %RC%

:probe
if defined PY exit /b 0
"%~1" %~2 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 9) else 1)" >nul 2>&1
if errorlevel 1 exit /b 0
set "PY=%~1"
set "PYARGS=%~2"
exit /b 0

:nopython
echo.
echo   No usable Python 3.9+ was found.
echo   Install it with:  winget install -e --id Python.Python.3.13
echo.
pause
endlocal & exit /b 1
