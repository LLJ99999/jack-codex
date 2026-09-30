[CmdletBinding()]
param(
    [ValidateSet('Install', 'Uninstall')][string]$Action = 'Install',
    [string]$CodexHome,
    [Alias('PromptFile')][string]$SourcePrompt,
    [string]$SkillsSource,
    [switch]$InjectAgents,
    [switch]$Uninstall
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$BeginMarker = '<!-- JACK-CODEX-INJECT:BEGIN -->'
$EndMarker = '<!-- JACK-CODEX-INJECT:END -->'
$SkillsBeginMarker = '# JACK-CODEX-SKILLS BEGIN'
$SkillsEndMarker = '# JACK-CODEX-SKILLS END'
$script:TransactionCreatedPaths = @()

if ($Uninstall) { $Action = 'Uninstall' }

function Read-Text([string]$Path) {
    return [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
}
function Write-Text([string]$Path, [string]$Text) {
    $parent = Split-Path -Parent $Path
    if ($parent) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
    [System.IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}
function Get-FullPath([string]$Path) {
    return [System.IO.Path]::GetFullPath($Path).TrimEnd([char]92, [char]47)
}
function Assert-ChildPath([string]$Parent, [string]$Child, [string]$Label) {
    $p = (Get-FullPath $Parent) + [System.IO.Path]::DirectorySeparatorChar
    $c = Get-FullPath $Child
    if (-not $c.StartsWith($p, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label escapes the allowed root: $c"
    }
}
function Get-HashValue([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return $null }
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Get-TreeHash([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path -PathType Container)) { return $null }
    $rows = foreach ($f in Get-ChildItem -LiteralPath $Path -Recurse -File | Sort-Object FullName) {
        $rel = $f.FullName.Substring($Path.Length).TrimStart([char]92, [char]47).Replace([char]92, [char]47)
        "$rel`:$((Get-HashValue $f.FullName))"
    }
    $temp = Join-Path ([System.IO.Path]::GetTempPath()) ('jack-tree-' + [guid]::NewGuid().ToString('N') + '.txt')
    try {
        Write-Text $temp ($rows -join "`n")
        return Get-HashValue $temp
    } finally { Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue }
}
function Remove-MarkerBlock([string]$Text) {
    $pattern = '(?ms)\s*' + [regex]::Escape($BeginMarker) + '.*?' + [regex]::Escape($EndMarker) + '\s*'
    return [regex]::Replace($Text, $pattern, [Environment]::NewLine, 1)
}
function Remove-SkillsBlock([string]$Text) {
    $pattern = '(?ms)\s*' + [regex]::Escape($SkillsBeginMarker) + '.*?' + [regex]::Escape($SkillsEndMarker) + '\s*'
    return [regex]::Replace($Text, $pattern, [Environment]::NewLine, 1)
}
function Assert-NoReparsePoint([string]$Root, [string]$Path) {
    $rootFull = Get-FullPath $Root
    $current = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
    while ($true) {
        if (($current.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0) {
            throw "Source path contains a reparse point: $($current.FullName)"
        }
        if ((Get-FullPath $current.FullName) -eq $rootFull) { break }
        $parent = Split-Path -Parent $current.FullName
        if (-not $parent) { throw "Source path is outside resource root: $Path" }
        $current = Get-Item -LiteralPath $parent -Force -ErrorAction Stop
    }
}
function Resolve-SourcePath([string]$Value, [string]$DefaultName) {
    if ([string]::IsNullOrWhiteSpace($Value)) { $Value = Join-Path $PSScriptRoot $DefaultName }
    elseif (-not [System.IO.Path]::IsPathRooted($Value)) { $Value = Join-Path $PSScriptRoot $Value }
    $full = Get-FullPath $Value
    Assert-ChildPath $PSScriptRoot $full $DefaultName
    if (Test-Path -LiteralPath $full) { Assert-NoReparsePoint $PSScriptRoot $full }
    return $full
}
function Copy-DirectoryExact([string]$Source, [string]$Destination) {
    if (Test-Path -LiteralPath $Destination) { Remove-Item -LiteralPath $Destination -Recurse -Force }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    foreach ($item in Get-ChildItem -LiteralPath $Source -Force) {
        Copy-Item -LiteralPath $item.FullName -Destination $Destination -Recurse -Force
    }
}
function Move-ToPreservedPath([string]$Path, [string]$Suffix) {
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $destination = $Path + ".jack-$Suffix-$stamp"
    if (Test-Path -LiteralPath $destination) { $destination += '-' + [guid]::NewGuid().ToString('N').Substring(0, 8) }
    Move-Item -LiteralPath $Path -Destination $destination
    $script:TransactionCreatedPaths += $destination
    return $destination
}

if ([string]::IsNullOrWhiteSpace($CodexHome)) {
    $CodexHome = if ($env:CODEX_HOME) { $env:CODEX_HOME } else { Join-Path $HOME '.codex' }
}
$CodexHome = Get-FullPath $CodexHome
if ([string]::IsNullOrWhiteSpace($CodexHome) -or $CodexHome -eq [System.IO.Path]::GetPathRoot($CodexHome)) {
    throw 'CodexHome must be a dedicated directory, not a drive root.'
}

$configPath = Join-Path $CodexHome 'config.toml'
$agentsPath = Join-Path $CodexHome 'AGENTS.md'
$managedDir = Join-Path $CodexHome 'managed-prompts'
$targetPrompt = Join-Path $managedDir 'jack-codex-v1.md'
$skillsTarget = Join-Path $CodexHome 'skills'
$metadataDir = Join-Path $CodexHome '.jack-codex'
$backupDir = Join-Path $metadataDir 'backups'
$statePath = Join-Path $metadataDir 'install-state.json'
foreach ($path in @($configPath, $agentsPath, $managedDir, $targetPrompt, $skillsTarget, $metadataDir, $backupDir, $statePath)) {
    Assert-ChildPath $CodexHome $path 'managed path'
}

if ($Action -eq 'Uninstall') {
    if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
        Write-Host "Jack Codex is not installed in $CodexHome"
        exit 0
    }
    $state = Read-Text $statePath | ConvertFrom-Json

    if (Test-Path -LiteralPath $configPath) {
        $config = Remove-SkillsBlock (Read-Text $configPath)
        $linePattern = '(?m)^\s*model_instructions_file\s*=\s*[^\r\n]*(?:\r?\n|$)'
        $currentInstruction = [regex]::Match($config, '(?m)^\s*model_instructions_file\s*=\s*[^\r\n]*')
        $managedInstruction = 'model_instructions_file = "' + $targetPrompt.Replace([char]92, [char]47).Replace('"', '\"') + '"'
        if ($currentInstruction.Success -and $currentInstruction.Value.Trim() -eq $managedInstruction) {
            if ($state.config.hadInstructionLine -and $state.config.instructionLine) {
                $replacement = [string]$state.config.instructionLine + [Environment]::NewLine
                $config = [regex]::Replace($config, $linePattern, $replacement, 1)
            } else {
                $config = [regex]::Replace($config, $linePattern, '', 1)
            }
        } elseif ($currentInstruction.Success) {
            Write-Warning 'Preserved user-modified model_instructions_file during uninstall.'
        }
        if (-not [bool]$state.config.existed -and [string]::IsNullOrWhiteSpace($config)) {
            Remove-Item -LiteralPath $configPath -Force
        } else {
            Write-Text $configPath ($config.TrimEnd() + [Environment]::NewLine)
        }
    }

    if (Test-Path -LiteralPath $agentsPath) {
        $agents = Remove-MarkerBlock (Read-Text $agentsPath)
        if ($state.agents.existed -or -not [string]::IsNullOrWhiteSpace($agents)) { Write-Text $agentsPath $agents.TrimEnd() + [Environment]::NewLine }
        else { Remove-Item -LiteralPath $agentsPath -Force }
    }

    foreach ($skill in @($state.skills)) {
        $name = [string]$skill.name
        if ($name -notmatch '^[A-Za-z0-9._-]+$') { continue }
        $dest = Join-Path $skillsTarget $name
        Assert-ChildPath $skillsTarget $dest 'skill target'
        if (Test-Path -LiteralPath $dest) {
            $currentHash = Get-TreeHash $dest
            if ($currentHash -eq [string]$skill.installedHash) { Remove-Item -LiteralPath $dest -Recurse -Force }
            else {
                $saved = Move-ToPreservedPath $dest 'user-modified'
                Write-Warning "Preserved modified managed skill as $(Split-Path -Leaf $saved)"
            }
        }
        if ($skill.backupPath) {
            $skillBackup = Get-FullPath ([string]$skill.backupPath)
            Assert-ChildPath $backupDir $skillBackup 'skill backup'
            if (Test-Path -LiteralPath $skillBackup) { Move-Item -LiteralPath $skillBackup -Destination $dest -Force }
        }
    }

    if (Test-Path -LiteralPath $targetPrompt) {
        $currentPromptHash = Get-HashValue $targetPrompt
        if ($currentPromptHash -eq [string]$state.prompt.installedHash) { Remove-Item -LiteralPath $targetPrompt -Force }
        else {
            $savedPrompt = Move-ToPreservedPath $targetPrompt 'user-modified'
            Write-Warning "Preserved modified managed prompt as $(Split-Path -Leaf $savedPrompt)"
        }
    }
    $promptBackupProperty = $state.prompt.PSObject.Properties['originalBackupPath']
    if ($promptBackupProperty -and $promptBackupProperty.Value) {
        $promptBackup = Get-FullPath ([string]$promptBackupProperty.Value)
        Assert-ChildPath $backupDir $promptBackup 'prompt backup'
        if (Test-Path -LiteralPath $promptBackup -PathType Leaf) { Move-Item -LiteralPath $promptBackup -Destination $targetPrompt -Force }
    }
    Remove-Item -LiteralPath $statePath -Force
    if ((Test-Path -LiteralPath $managedDir) -and -not (Get-ChildItem -LiteralPath $managedDir -Force | Select-Object -First 1)) { Remove-Item -LiteralPath $managedDir -Force }
    if ((Test-Path -LiteralPath $backupDir) -and -not (Get-ChildItem -LiteralPath $backupDir -Force | Select-Object -First 1)) { Remove-Item -LiteralPath $backupDir -Force }
    if ((Test-Path -LiteralPath $metadataDir) -and -not (Get-ChildItem -LiteralPath $metadataDir -Force | Select-Object -First 1)) { Remove-Item -LiteralPath $metadataDir -Force }
    Write-Host "Uninstalled Jack Codex from $CodexHome"
    exit 0
}

$SourcePrompt = Resolve-SourcePath $SourcePrompt 'jack-codex-v1.md'
$SkillsSource = Resolve-SourcePath $SkillsSource 'codex-skills'
if (-not (Test-Path -LiteralPath $SourcePrompt -PathType Leaf)) { throw "Prompt file not found: $SourcePrompt" }
if ((Split-Path -Leaf $SourcePrompt) -ne 'jack-codex-v1.md') { throw 'Only jack-codex-v1.md may be installed.' }
if (-not (Test-Path -LiteralPath $SkillsSource -PathType Container)) { throw "Skills directory not found: $SkillsSource" }
$sourceReparsePoint = Get-ChildItem -LiteralPath $SkillsSource -Recurse -Force | Where-Object { ($_.Attributes -band [System.IO.FileAttributes]::ReparsePoint) -ne 0 } | Select-Object -First 1
if ($sourceReparsePoint) { throw "Skills source contains a reparse point: $($sourceReparsePoint.FullName)" }

$codexHomeExisted = Test-Path -LiteralPath $CodexHome -PathType Container
$existingState = $null
if (Test-Path -LiteralPath $statePath -PathType Leaf) { $existingState = Read-Text $statePath | ConvertFrom-Json }
$sourceDirs = @(Get-ChildItem -LiteralPath $SkillsSource -Directory | Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') })
foreach ($dir in $sourceDirs) { if ($dir.Name -notmatch '^[A-Za-z0-9._-]+$') { throw "Invalid skill directory name: $($dir.Name)" } }
$previousSkills = @{}
if ($existingState) { foreach ($item in @($existingState.skills)) { $previousSkills[[string]$item.name] = $item } }
$affectedNames = @(@($sourceDirs | ForEach-Object { $_.Name }) + @($previousSkills.Keys) | Sort-Object -Unique)

$configExisted = Test-Path -LiteralPath $configPath -PathType Leaf
$agentsExisted = Test-Path -LiteralPath $agentsPath -PathType Leaf
$config = if ($configExisted) { Read-Text $configPath } else { '' }
$agents = if ($agentsExisted) { Read-Text $agentsPath } else { '' }
$instructionMatch = [regex]::Match($config, '(?m)^\s*model_instructions_file\s*=\s*[^\r\n]*')
$originalInstruction = if ($existingState) { $existingState.config.instructionLine } elseif ($instructionMatch.Success) { $instructionMatch.Value.TrimEnd("`r") } else { $null }
$originalHadInstruction = if ($existingState) { [bool]$existingState.config.hadInstructionLine } else { $instructionMatch.Success }
$originalConfigExisted = if ($existingState) { [bool]$existingState.config.existed } else { $configExisted }
$originalAgentsExisted = if ($existingState) { [bool]$existingState.agents.existed } else { $agentsExisted }
$originalConfigHash = if ($existingState) { $existingState.config.originalHash } elseif ($configExisted) { Get-HashValue $configPath } else { $null }
$originalAgentsHash = if ($existingState) { $existingState.agents.originalHash } elseif ($agentsExisted) { Get-HashValue $agentsPath } else { $null }

$transactionRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('jack-codex-transaction-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $transactionRoot | Out-Null
$rollbackSkillExisted = @{}
try {
    if ($configExisted) { Copy-Item -LiteralPath $configPath -Destination (Join-Path $transactionRoot 'config.toml') -Force }
    if ($agentsExisted) { Copy-Item -LiteralPath $agentsPath -Destination (Join-Path $transactionRoot 'AGENTS.md') -Force }
    if (Test-Path -LiteralPath $targetPrompt -PathType Leaf) { Copy-Item -LiteralPath $targetPrompt -Destination (Join-Path $transactionRoot 'prompt.md') -Force }
    $promptExistedAtStart = Test-Path -LiteralPath $targetPrompt -PathType Leaf
    if (Test-Path -LiteralPath $metadataDir -PathType Container) { Copy-DirectoryExact $metadataDir (Join-Path $transactionRoot 'metadata') }
    foreach ($name in $affectedNames) {
        $dest = Join-Path $skillsTarget $name
        $rollbackSkillExisted[$name] = Test-Path -LiteralPath $dest -PathType Container
        if ($rollbackSkillExisted[$name]) { Copy-DirectoryExact $dest (Join-Path (Join-Path $transactionRoot 'skills') $name) }
    }

    New-Item -ItemType Directory -Force -Path $CodexHome, $managedDir, $skillsTarget, $backupDir | Out-Null

    $promptOriginalBackup = $null
    if ($existingState) {
        $oldPromptBackupProperty = $existingState.prompt.PSObject.Properties['originalBackupPath']
        if ($oldPromptBackupProperty) { $promptOriginalBackup = [string]$oldPromptBackupProperty.Value }
        if (Test-Path -LiteralPath $targetPrompt -PathType Leaf) {
            $oldInstalledPromptHash = [string]$existingState.prompt.installedHash
            if ((Get-HashValue $targetPrompt) -ne $oldInstalledPromptHash) {
                $savedPrompt = Move-ToPreservedPath $targetPrompt 'user-modified'
                Write-Warning "Preserved modified managed prompt as $(Split-Path -Leaf $savedPrompt)"
            }
        }
    } elseif (Test-Path -LiteralPath $targetPrompt -PathType Leaf) {
        $promptOriginalBackup = Join-Path $backupDir ('prompt-original-' + [guid]::NewGuid().ToString('N') + '.md')
        Move-Item -LiteralPath $targetPrompt -Destination $promptOriginalBackup
    }
    Copy-Item -LiteralPath $SourcePrompt -Destination $targetPrompt -Force
    $promptHash = Get-HashValue $targetPrompt

    $configLine = 'model_instructions_file = "' + $targetPrompt.Replace([char]92, [char]47).Replace('"', '\"') + '"'
    $linePattern = '(?m)^\s*model_instructions_file\s*=\s*.*$'
    if ([regex]::IsMatch($config, $linePattern)) { $config = [regex]::Replace($config, $linePattern, $configLine, 1) }
    else { $config = $configLine + [Environment]::NewLine + $config }
    Write-Text $configPath ($config.TrimEnd() + [Environment]::NewLine)

    $agents = Remove-MarkerBlock $agents
    $block = $BeginMarker + [Environment]::NewLine + (Read-Text $targetPrompt).TrimEnd() + [Environment]::NewLine + $EndMarker
    if ([string]::IsNullOrWhiteSpace($agents)) { $agents = $block + [Environment]::NewLine }
    else { $agents = $agents.TrimEnd() + [Environment]::NewLine + [Environment]::NewLine + $block + [Environment]::NewLine }
    Write-Text $agentsPath $agents

    $sourceNames = @{}
    $skillState = @()
    foreach ($dir in $sourceDirs) {
        $sourceNames[$dir.Name] = $true
        $dest = Join-Path $skillsTarget $dir.Name
        Assert-ChildPath $skillsTarget $dest 'skill target'
        $backupPath = $null
        if ($previousSkills.ContainsKey($dir.Name)) {
            $previous = $previousSkills[$dir.Name]
            $backupPath = [string]$previous.backupPath
            if ($backupPath) { Assert-ChildPath $backupDir (Get-FullPath $backupPath) 'skill backup' }
            if ((Test-Path -LiteralPath $dest -PathType Container) -and (Get-TreeHash $dest) -ne [string]$previous.installedHash) {
                $savedSkill = Move-ToPreservedPath $dest 'user-modified'
                Write-Warning "Preserved modified managed skill as $(Split-Path -Leaf $savedSkill)"
            }
        } elseif (Test-Path -LiteralPath $dest -PathType Container) {
            $backupPath = Join-Path $backupDir ('skill-' + $dir.Name + '-' + [guid]::NewGuid().ToString('N'))
            Move-Item -LiteralPath $dest -Destination $backupPath
        }
        Copy-DirectoryExact $dir.FullName $dest
        $skillState += [ordered]@{ name = $dir.Name; installedHash = Get-TreeHash $dest; backupPath = $backupPath }
    }

    foreach ($name in @($previousSkills.Keys)) {
        if ($sourceNames.ContainsKey($name)) { continue }
        $previous = $previousSkills[$name]
        $dest = Join-Path $skillsTarget $name
        Assert-ChildPath $skillsTarget $dest 'retired skill target'
        if (Test-Path -LiteralPath $dest -PathType Container) {
            if ((Get-TreeHash $dest) -eq [string]$previous.installedHash) { Remove-Item -LiteralPath $dest -Recurse -Force }
            else {
                $savedSkill = Move-ToPreservedPath $dest 'user-modified'
                Write-Warning "Preserved modified retired skill as $(Split-Path -Leaf $savedSkill)"
            }
        }
        if ($previous.backupPath) {
            $retiredBackup = Get-FullPath ([string]$previous.backupPath)
            Assert-ChildPath $backupDir $retiredBackup 'retired skill backup'
            if (Test-Path -LiteralPath $retiredBackup -PathType Container) { Move-Item -LiteralPath $retiredBackup -Destination $dest -Force }
        }
    }

    $state = [ordered]@{
        schemaVersion = 2
        product = 'jack-codex'
        installedAt = (Get-Date).ToUniversalTime().ToString('o')
        codexHome = $CodexHome
        config = [ordered]@{ existed = $originalConfigExisted; originalHash = $originalConfigHash; hadInstructionLine = $originalHadInstruction; instructionLine = $originalInstruction; installedHash = Get-HashValue $configPath }
        agents = [ordered]@{ existed = $originalAgentsExisted; originalHash = $originalAgentsHash; installedHash = Get-HashValue $agentsPath }
        prompt = [ordered]@{ path = $targetPrompt; originalBackupPath = $promptOriginalBackup; installedHash = $promptHash }
        skills = $skillState
    }
    Write-Text $statePath (($state | ConvertTo-Json -Depth 8) + [Environment]::NewLine)
} catch {
    $failure = $_
    foreach ($createdPath in $script:TransactionCreatedPaths) {
        if (Test-Path -LiteralPath $createdPath) { Remove-Item -LiteralPath $createdPath -Recurse -Force -ErrorAction SilentlyContinue }
    }
    foreach ($name in $affectedNames) {
        $dest = Join-Path $skillsTarget $name
        if (Test-Path -LiteralPath $dest) { Remove-Item -LiteralPath $dest -Recurse -Force -ErrorAction SilentlyContinue }
        if ($rollbackSkillExisted[$name]) { Copy-DirectoryExact (Join-Path (Join-Path $transactionRoot 'skills') $name) $dest }
    }
    if (Test-Path -LiteralPath $configPath) { Remove-Item -LiteralPath $configPath -Force -ErrorAction SilentlyContinue }
    if ($configExisted) { Copy-Item -LiteralPath (Join-Path $transactionRoot 'config.toml') -Destination $configPath -Force }
    if (Test-Path -LiteralPath $agentsPath) { Remove-Item -LiteralPath $agentsPath -Force -ErrorAction SilentlyContinue }
    if ($agentsExisted) { Copy-Item -LiteralPath (Join-Path $transactionRoot 'AGENTS.md') -Destination $agentsPath -Force }
    if (Test-Path -LiteralPath $targetPrompt) { Remove-Item -LiteralPath $targetPrompt -Force -ErrorAction SilentlyContinue }
    if ($promptExistedAtStart) { Copy-Item -LiteralPath (Join-Path $transactionRoot 'prompt.md') -Destination $targetPrompt -Force }
    if (Test-Path -LiteralPath $metadataDir) { Remove-Item -LiteralPath $metadataDir -Recurse -Force -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath (Join-Path $transactionRoot 'metadata')) { Copy-DirectoryExact (Join-Path $transactionRoot 'metadata') $metadataDir }
    if (-not $codexHomeExisted -and (Test-Path -LiteralPath $CodexHome) -and -not (Get-ChildItem -LiteralPath $CodexHome -Force | Select-Object -First 1)) { Remove-Item -LiteralPath $CodexHome -Force }
    throw $failure
} finally {
    Remove-Item -LiteralPath $transactionRoot -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "Installed Jack Codex into $CodexHome"
