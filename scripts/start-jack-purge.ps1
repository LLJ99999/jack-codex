[CmdletBinding()]
param(
    [string]$Listen = $(if ($env:JACK_PURGE_LISTEN) { $env:JACK_PURGE_LISTEN } else { '127.0.0.1:8787' }),
    [string]$Upstream = $env:JACK_PURGE_UPSTREAM,
    [string]$CodexHome
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($CodexHome)) {
    $CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
}
$proxy = Join-Path $CodexHome '.jack-codex\jack-purge-proxy.mjs'
if (-not (Test-Path -LiteralPath $proxy -PathType Leaf)) {
    $proxy = Join-Path $PSScriptRoot 'jack-purge-proxy.mjs'
}
if (-not (Test-Path -LiteralPath $proxy -PathType Leaf)) {
    throw "jack-purge-proxy.mjs not found"
}
if ([string]::IsNullOrWhiteSpace($Upstream)) {
    $saved = Join-Path $CodexHome '.jack-codex\purge-upstream.txt'
    if (Test-Path -LiteralPath $saved -PathType Leaf) {
        $Upstream = ([System.IO.File]::ReadAllText($saved).Trim())
    }
}
if ([string]::IsNullOrWhiteSpace($Upstream)) {
    throw 'Missing upstream. Installer writes CODEX_HOME\.jack-codex\purge-upstream.txt from your existing base_url, or set JACK_PURGE_UPSTREAM=https://YOUR_RELAY_ORIGIN'
}
$Upstream = $Upstream.Trim().TrimEnd('/')
if ($Upstream.ToLowerInvariant().EndsWith('/v1')) { $Upstream = $Upstream.Substring(0, $Upstream.Length - 3).TrimEnd('/') }

$env:JACK_PURGE_LISTEN = $Listen
$env:JACK_PURGE_UPSTREAM = $Upstream
$env:JACK_PURGE_PERSONA = Join-Path $CodexHome 'managed-prompts\jack-codex-v1.md'
$env:JACK_PURGE_LOG = '1'
Write-Host "jack-purge $Listen -> $Upstream"
Write-Host "health: http://127.0.0.1:8787/health"
node $proxy
