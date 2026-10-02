@echo off
rem  Run wrangler without caring what is on PATH.
rem
rem  Node and npm both install fine and still leave `wrangler` unfound, for a
rem  reason that has nothing to do with either: a program's PATH is a copy
rem  taken when it started, so every shell, editor and terminal opened before
rem  the install keeps the old one -- and a "new" window launched from an
rem  explorer.exe that is itself stale inherits the stale copy. Restarting
rem  explorer fixes it; this does not need fixing.
rem
rem  Usage, from anywhere:
rem      worker\wr.cmd login
rem      worker\wr.cmd d1 create cs2-autoconfig
rem      worker\wr.cmd deploy

setlocal

rem --- find node ------------------------------------------------------------
set "NODE_DIR="
for %%D in (
  "%ProgramFiles%\nodejs"
  "%ProgramFiles(x86)%\nodejs"
  "%LOCALAPPDATA%\Programs\nodejs"
) do if not defined NODE_DIR if exist "%%~D\node.exe" set "NODE_DIR=%%~D"

if not defined NODE_DIR (
  rem Already on PATH is just as good.
  where node >nul 2>&1 && set "NODE_DIR=."
)

if not defined NODE_DIR (
  echo.
  echo   Node is not installed, and wrangler runs on it.
  echo.
  echo       winget install OpenJS.NodeJS.LTS
  echo.
  echo   Then run this again. No new terminal needed -- that is the point of
  echo   this file.
  echo.
  exit /b 1
)

rem --- find wrangler --------------------------------------------------------
set "WRANGLER=%APPDATA%\npm\wrangler.cmd"
if not exist "%WRANGLER%" (
  echo.
  echo   wrangler is not installed. With Node present:
  echo.
  echo       "%NODE_DIR%\npm.cmd" install -g --allow-scripts=esbuild,workerd wrangler
  echo.
  echo   The .cmd on npm is not a typo: PowerShell refuses to run npm's other
  echo   half unless script execution is turned on machine-wide, which is not
  echo   worth doing to install one package.
  echo.
  exit /b 1
)

rem Both on the front of PATH for this process only. Nothing outside it is
rem changed, so there is no setting here to put back afterwards.
set "PATH=%NODE_DIR%;%APPDATA%\npm;%PATH%"

call "%WRANGLER%" %*
exit /b %ERRORLEVEL%
