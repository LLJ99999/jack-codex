@echo off
setlocal
set "TEMP_SCRIPT=%TEMP%\jack-codex-portable-uninstall.ps1"
copy /y "%~dp0portable-uninstall.ps1" "%TEMP_SCRIPT%" >nul 2>&1
if not exist "%TEMP_SCRIPT%" (
  echo [ERROR] portable-uninstall.ps1 is missing.
  pause
  exit /b 1
)
start "" powershell.exe -NoLogo -NoProfile -NonInteractive -File "%TEMP_SCRIPT%" -AppDir "%~dp0." %*
exit /b 0
