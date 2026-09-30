!ifdef BUILD_UNINSTALLER
!macro customUnInit
  nsExec::Exec 'taskkill /F /T /IM "${APP_EXECUTABLE_FILENAME}"'
  Pop $0
  Sleep 800
  ${ifNot} ${isUpdated}
    DetailPrint "Restoring Jack Codex configuration..."
    IfFileExists "$INSTDIR\resources\scripts\clear-injected-prompts.ps1" restore_ready restore_missing
    restore_ready:
      nsExec::Exec 'powershell.exe -NoLogo -NoProfile -NonInteractive -File "$INSTDIR\resources\scripts\clear-injected-prompts.ps1" -Apply'
      Pop $0
      StrCmp $0 "0" restore_done restore_failed
    restore_missing:
      MessageBox MB_ICONSTOP "Jack Codex restore script is missing. Uninstall stopped to preserve Codex configuration."
      Abort
    restore_failed:
      MessageBox MB_ICONSTOP "Jack Codex configuration restore failed (exit $0). Uninstall stopped."
      Abort
    restore_done:
  ${endIf}
!macroend
!endif
