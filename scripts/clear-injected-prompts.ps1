[CmdletBinding()]
param(
    [switch]$Apply,
    [string]$CodexHome
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$installer = Join-Path $root 'install.ps1'
if (-not (Test-Path -LiteralPath $installer -PathType Leaf)) { throw "Installer is missing: $installer" }

if ([string]::IsNullOrWhiteSpace($CodexHome)) {
    foreach ($candidate in @(
        (Join-Path $env:APPDATA 'Jack Codex 工具\jack-desktop-state.json'),
        (Join-Path $env:APPDATA 'jack-codex\jack-desktop-state.json')
    )) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) { continue }
        try {
            $desktopState = Get-Content -LiteralPath $candidate -Raw -Encoding UTF8 | ConvertFrom-Json
            if ($desktopState.installedCodexHome -and [System.IO.Path]::IsPathRooted([string]$desktopState.installedCodexHome)) {
                $CodexHome = [string]$desktopState.installedCodexHome
                break
            }
        } catch { Write-Warning "Ignoring unreadable Jack desktop state: $candidate" }
    }
}
if ([string]::IsNullOrWhiteSpace($CodexHome)) {
    $CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
}
$CodexHome = [System.IO.Path]::GetFullPath($CodexHome).TrimEnd([char]92, [char]47)
$statePath = Join-Path $CodexHome '.jack-codex\install-state.json'
if (-not $Apply) {
    if (Test-Path -LiteralPath $statePath) {
        Write-Host "DRY-RUN: Jack Codex state found at $statePath"
        Write-Host 'Run again with -Apply to restore the recorded Codex state.'
    } else {
        Write-Host "DRY-RUN: no Jack Codex state found in $CodexHome"
    }
    exit 0
}
& powershell.exe -NoLogo -NoProfile -NonInteractive -File $installer -Action Uninstall -CodexHome $CodexHome
exit $LASTEXITCODE
