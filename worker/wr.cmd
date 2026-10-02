@echo off
rem  Run wrangler without caring what is on PATH.
rem
rem  Node and npm both install fine and still leave `wrangler` unfound, for a
rem  reason that has nothing to do with either: a program's PATH is a copy
rem  taken when it started, so every shell, editor and terminal opened before
rem  the install keeps the old one -- and a "new" window launched from an
rem  explorer.exe that is itself stale inherits the stale copy.
rem
rem  Usage, from anywhere:
rem      worker\wr.cmd login
rem      worker\wr.cmd d1 create cs2-autoconfig
rem      worker\wr.cmd deploy

setlocal

rem --- find node ------------------------------------------------------------
rem  Checked one at a time rather than in a for loop, because the obvious
rem  loop over the Program Files variables is a trap: the x86 one expands to a
rem  path containing a bracket, and a bracket inside a for block ends the
rem  block early. It worked on the machine it was written on and would have
rem  failed somewhere else.
set "NODE_DIR="
if exist "%ProgramFiles%\nodejs\node.exe"            set "NODE_DIR=%ProgramFiles%\nodejs"
if not defined NODE_DIR if exist "%ProgramW6432%\nodejs\node.exe"   set "NODE_DIR=%ProgramW6432%\nodejs"
if not defined NODE_DIR if exist "%LOCALAPPDATA%\Programs\nodejs\node.exe" set "NODE_DIR=%LOCALAPPDATA%\Programs\nodejs"
if not defined NODE_DIR if exist "C:\Program Files\nodejs\node.exe" set "NODE_DIR=C:\Program Files\nodejs"
if not defined NODE_DIR if exist "C:\Program Files (x86)\nodejs\node.exe" set "NODE_DIR=C:\Program Files (x86)\nodejs"

if not defined NODE_DIR (
  for /f "delims=" %%P in ('where node 2^>nul') do if not defined NODE_DIR set "NODE_DIR=%%~dpP"
)

if not defined NODE_DIR (
  echo.
  echo   Node is not installed, and wrangler runs on it.
  echo.
  echo       winget install OpenJS.NodeJS.LTS
  echo.
  echo   Then run this again. No new terminal needed, which is the point of
  echo   this file.
  echo.
  exit /b 1
)

rem --- find wrangler --------------------------------------------------------
rem  Several places, because %APPDATA% is not reliable: it is per-user, so an
rem  elevated prompt has a different one, and some shells inherit a stale copy.
set "WRANGLER="
if exist "%APPDATA%\npm\wrangler.cmd" set "WRANGLER=%APPDATA%\npm\wrangler.cmd"
if not defined WRANGLER if exist "%USERPROFILE%\AppData\Roaming\npm\wrangler.cmd" set "WRANGLER=%USERPROFILE%\AppData\Roaming\npm\wrangler.cmd"
if not defined WRANGLER if exist "%NODE_DIR%\wrangler.cmd" set "WRANGLER=%NODE_DIR%\wrangler.cmd"

rem Ask npm where it actually puts global packages, rather than assuming.
if not defined WRANGLER (
  for /f "delims=" %%P in ('"%NODE_DIR%\npm.cmd" prefix -g 2^>nul') do (
    if not defined WRANGLER if exist "%%P\wrangler.cmd" set "WRANGLER=%%P\wrangler.cmd"
  )
)

if not defined WRANGLER (
  for /f "delims=" %%P in ('where wrangler.cmd 2^>nul') do if not defined WRANGLER set "WRANGLER=%%P"
)

if not defined WRANGLER (
  echo.
  echo   wrangler was not found. Looked in:
  echo.
  echo       %APPDATA%\npm\wrangler.cmd
  echo       %USERPROFILE%\AppData\Roaming\npm\wrangler.cmd
  echo       %NODE_DIR%\wrangler.cmd
  echo       whatever "npm prefix -g" reports
  echo       anything called wrangler.cmd on PATH
  echo.
  echo   APPDATA is currently: %APPDATA%
  echo   If that is not under your own user folder, this is an elevated
  echo   prompt -- close it and use an ordinary one. None of this needs
  echo   administrator.
  echo.
  echo   To install it:
  echo       "%NODE_DIR%\npm.cmd" install -g --allow-scripts=esbuild,workerd wrangler
  echo.
  exit /b 1
)

rem Both on the front of PATH for this process only. Nothing outside it is
rem changed, so there is no setting here to put back afterwards.
set "PATH=%NODE_DIR%;%APPDATA%\npm;%PATH%"

rem Run from the folder holding wrangler.toml, whatever folder this was called
rem from. wrangler reads its configuration from the working directory, so
rem calling this from the repository root gave "Required Worker name missing"
rem -- which sounds like a fault in the configuration rather than what it is,
rem which is wrangler never having found the configuration at all.
pushd "%~dp0"
call "%WRANGLER%" %*
set "CODE=%ERRORLEVEL%"
popd
exit /b %CODE%
