[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)][string]$AppDir,
    [switch]$KeepData,
    [switch]$NoPause
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$AppDir = [System.IO.Path]::GetFullPath($AppDir).TrimEnd([char]92, [char]47)
if ($AppDir -eq [System.IO.Path]::GetPathRoot($AppDir)) { throw 'AppDir must not be a drive root.' }

Write-Host "Jack Codex portable uninstall: $AppDir"
$restoreScript = Join-Path $AppDir 'resources\scripts\clear-injected-prompts.ps1'
if (-not (Test-Path -LiteralPath $restoreScript -PathType Leaf)) { throw "Codex restore script is missing: $restoreScript" }
& powershell.exe -NoLogo -NoProfile -NonInteractive -File $restoreScript -Apply
if ($LASTEXITCODE -ne 0) { throw "Codex restore failed with exit code $LASTEXITCODE" }

Get-Process -Name 'Jack Codex 工具' -ErrorAction SilentlyContinue | Where-Object {
    $_.Path -and $_.Path.StartsWith($AppDir + [System.IO.Path]::DirectorySeparatorChar, [System.StringComparison]::OrdinalIgnoreCase)
} | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 500

if (-not $KeepData) {
    foreach ($path in @(
        (Join-Path $env:APPDATA 'jack-codex'),
        (Join-Path $env:APPDATA 'Jack Codex 工具'),
        (Join-Path $env:LOCALAPPDATA 'jack-codex'),
        (Join-Path $env:LOCALAPPDATA 'jack-codex-updater'),
        (Join-Path $env:LOCALAPPDATA 'Jack Codex 工具'),
        (Join-Path $env:LOCALAPPDATA 'Jack Codex 工具-updater')
    )) {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path -Recurse -Force }
    }
}

Remove-Item -LiteralPath $AppDir -Recurse -Force
Write-Host 'Jack Codex portable files removed.' -ForegroundColor Green
if (-not $NoPause) { Read-Host 'Press Enter to close' | Out-Null }
