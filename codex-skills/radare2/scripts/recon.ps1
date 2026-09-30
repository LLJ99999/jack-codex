param(
    [Parameter(Mandatory = $true)][string]$TargetPath,
    [int]$StringsLimit = 40,
    [int]$ImportsLimit = 80,
    [switch]$RunAnalysis
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot '..\..\scripts\lib\ToolDiscovery.ps1')

function Get-RequiredToolSpec([string]$Name) {
    $spec = Resolve-ReverseToolSpec -Name $Name
    if (-not $spec.Available) {
        throw "Missing required command: $Name. Install and verify radare2 before running this script."
    }
    return $spec
}
function Write-Section([string]$Title) {
    Write-Output ""
    Write-Output "=== $Title ==="
}

$rabin2 = Get-RequiredToolSpec -Name 'rabin2'
$r2 = if ($RunAnalysis) { Get-RequiredToolSpec -Name 'r2' } else { $null }
$target = (Resolve-Path -LiteralPath $TargetPath).Path
Write-Output "Target: $target"
Write-Section 'File information'
& $rabin2.Command @($rabin2.PrefixArgs + @('-I', '--', $target))
Write-Section 'Sections'
& $rabin2.Command @($rabin2.PrefixArgs + @('-S', '--', $target))
Write-Section 'Imports'
& $rabin2.Command @($rabin2.PrefixArgs + @('-i', '--', $target)) | Select-Object -First $ImportsLimit
Write-Section 'Exports'
& $rabin2.Command @($rabin2.PrefixArgs + @('-E', '--', $target))
Write-Section 'Strings'
& $rabin2.Command @($rabin2.PrefixArgs + @('-zz', '--', $target)) | Select-Object -First $StringsLimit
if ($RunAnalysis) {
    Write-Section 'Functions and entry point'
    & $r2.Command @($r2.PrefixArgs + @('-A', '-q', '-c', 's entry0;afl;iz;ii;q', '--', $target))
}
