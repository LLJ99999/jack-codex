[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$RepoRoot = Split-Path -Parent $PSScriptRoot
$Installer = Join-Path $RepoRoot 'install.ps1'
$Prompt = Join-Path $RepoRoot 'jack-codex-v1.md'
$SkillsSource = Join-Path $RepoRoot 'codex-skills'
$SkillsArgument = 'codex-skills'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$TempRoot = Join-Path ([System.IO.Path]::GetTempPath()) ('jack-codex-installer-' + [guid]::NewGuid().ToString('N'))
$FixtureRoot = Join-Path $PSScriptRoot ('.installer-fixture-' + [guid]::NewGuid().ToString('N'))
$CodexHome = Join-Path $TempRoot 'codex-home'
$ConfigPath = Join-Path $CodexHome 'config.toml'
$AgentsPath = Join-Path $CodexHome 'AGENTS.md'
$UserSkillDir = Join-Path $CodexHome 'skills\user-owned-skill'
$UserSkillPath = Join-Path $UserSkillDir 'SKILL.md'
$OldCodexHome = $env:CODEX_HOME
$OldAppData = $env:APPDATA
$ClearScript = Join-Path $RepoRoot 'scripts\clear-injected-prompts.ps1'

$OriginalInstructionLine = 'model_instructions_file = "C:/user/prompts/original.md"'
$OriginalConfig = @"
$OriginalInstructionLine
model = "gpt-test"
custom_user_setting = "keep-me"
openai_base_url = "https://api.example.com/v1"
"@ -replace "`n", [Environment]::NewLine
$OriginalAgents = "# User instructions`r`n`r`nKeep this user-owned content exactly.`r`n"
$OriginalSkill = "---`r`nname: user-owned-skill`r`ndescription: Must survive Jack install and uninstall.`r`n---`r`n`r`nUSER_SKILL_SENTINEL`r`n"
$JackBeginPattern = '(?im)<!--[^\r\n]*jack[^\r\n]*(?:begin|start)[^\r\n]*-->'
$JackEndPattern = '(?im)<!--[^\r\n]*jack[^\r\n]*(?:end|stop)[^\r\n]*-->'

function Assert-True([bool]$Condition, [string]$Message) {
    if (-not $Condition) { throw "ASSERTION FAILED: $Message" }
}

function Read-Utf8([string]$Path) {
    return [System.IO.File]::ReadAllText($Path, [System.Text.Encoding]::UTF8)
}

function Invoke-Installer([switch]$Uninstall, [string]$SkillsSourceArgument = $SkillsArgument, [switch]$ExpectFailure) {
    $hostExe = (Get-Process -Id $PID).Path
    $arguments = @(
        '-NoProfile',
        '-NonInteractive',
        '-File', $Installer,
        '-CodexHome', $CodexHome,
        '-SourcePrompt', $Prompt,
        '-SkillsSource', $SkillsSourceArgument,
        '-InjectAgents'
    )
    if ($Uninstall) { $arguments += '-Uninstall' }

    & $hostExe @arguments
    if ($ExpectFailure) {
        if ($LASTEXITCODE -eq 0) { throw 'installer unexpectedly succeeded' }
        return
    }
    if ($LASTEXITCODE -ne 0) {
        $operation = if ($Uninstall) { 'uninstall' } else { 'install' }
        throw "$operation exited with code $LASTEXITCODE"
    }
}

try {
    Assert-True (Test-Path -LiteralPath $Installer -PathType Leaf) 'root install.ps1 is missing'
    Assert-True (Test-Path -LiteralPath $Prompt -PathType Leaf) 'jack-codex-v1.md is missing'
    Assert-True (Test-Path -LiteralPath $SkillsSource -PathType Container) 'codex-skills is missing'

    $ManagedSkill = Get-ChildItem -LiteralPath $SkillsSource -Directory |
        Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') } |
        Select-Object -First 1
    Assert-True ($null -ne $ManagedSkill) 'codex-skills contains no installable top-level skill'
    $ManagedSkillTarget = Join-Path $CodexHome ('skills\' + $ManagedSkill.Name)
    $ManagedPromptPath = Join-Path $CodexHome 'managed-prompts\jack-codex-v1.md'
    $OriginalManagedPrompt = "USER_PREEXISTING_PROMPT`r`n"
    $OriginalCollidingSkill = "---`r`nname: $($ManagedSkill.Name)`r`ndescription: Pre-existing user skill.`r`n---`r`nUSER_COLLIDING_SKILL`r`n"

    New-Item -ItemType Directory -Force -Path $UserSkillDir, $ManagedSkillTarget, (Split-Path -Parent $ManagedPromptPath) | Out-Null
    [System.IO.File]::WriteAllText($ConfigPath, $OriginalConfig, $Utf8NoBom)
    [System.IO.File]::WriteAllText($AgentsPath, $OriginalAgents, $Utf8NoBom)
    [System.IO.File]::WriteAllText($UserSkillPath, $OriginalSkill, $Utf8NoBom)
    [System.IO.File]::WriteAllText((Join-Path $ManagedSkillTarget 'SKILL.md'), $OriginalCollidingSkill, $Utf8NoBom)
    [System.IO.File]::WriteAllText($ManagedPromptPath, $OriginalManagedPrompt, $Utf8NoBom)
    $env:CODEX_HOME = $CodexHome

    Write-Host 'Installing into temporary CODEX_HOME...'
    Invoke-Installer

    $InstalledConfig = Read-Utf8 $ConfigPath
    $InstalledAgents = Read-Utf8 $AgentsPath
    Assert-True ($InstalledConfig -match '(?m)^\s*model_instructions_file\s*=\s*"[^"]*managed-prompts/jack-codex-v1\.md"\s*$') 'config.toml does not select the managed Jack prompt'
    Assert-True ($InstalledConfig.Contains('custom_user_setting = "keep-me"')) 'installer changed unrelated config.toml content'
    Assert-True ($InstalledConfig.Contains('approval_policy = "never"')) 'installer did not patch approval_policy'
    Assert-True ($InstalledConfig.Contains('sandbox_mode = "danger-full-access"')) 'installer did not patch sandbox_mode'
    Assert-True ($InstalledConfig.Contains('model_provider = "jackpurge"')) 'installer did not point Codex at the purge proxy'
    Assert-True ($InstalledConfig.Contains('base_url = "http://127.0.0.1:8787/v1"')) 'installer did not write purge base_url'
    Assert-True ($InstalledConfig.Contains('openai_base_url = "https://api.example.com/v1"')) 'installer dropped existing openai_base_url'
    Assert-True (Test-Path -LiteralPath (Join-Path $CodexHome '.jack-codex\jack-purge-proxy.mjs') -PathType Leaf) 'purge proxy was not copied'
    Assert-True ((Read-Utf8 (Join-Path $CodexHome '.jack-codex\purge-upstream.txt')).Trim() -eq 'https://api.example.com') 'installer did not capture existing relay origin'
    Assert-True ($InstalledAgents.Contains('Keep this user-owned content exactly.')) 'installer removed user AGENTS.md content'
    Assert-True ([regex]::Matches($InstalledAgents, $JackBeginPattern).Count -eq 1) 'Jack begin marker is missing or duplicated after install'
    Assert-True ([regex]::Matches($InstalledAgents, $JackEndPattern).Count -eq 1) 'Jack end marker is missing or duplicated after install'
    Assert-True (Test-Path -LiteralPath (Join-Path $CodexHome 'managed-prompts\jack-codex-v1.md') -PathType Leaf) 'managed Jack prompt was not installed'
    Assert-True (Test-Path -LiteralPath $ManagedSkillTarget -PathType Container) "managed skill '$($ManagedSkill.Name)' was not installed"
    Assert-True ((Read-Utf8 $UserSkillPath) -ceq $OriginalSkill) 'user-owned skill changed during install'

    $ModifiedManagedPrompt = "USER_MODIFIED_INSTALLED_PROMPT`r`n"
    $ModifiedManagedSkill = "---`r`nname: $($ManagedSkill.Name)`r`ndescription: User modified managed skill.`r`n---`r`nUSER_MODIFIED_MANAGED_SKILL`r`n"
    [System.IO.File]::WriteAllText($ManagedPromptPath, $ModifiedManagedPrompt, $Utf8NoBom)
    [System.IO.File]::WriteAllText((Join-Path $ManagedSkillTarget 'SKILL.md'), $ModifiedManagedSkill, $Utf8NoBom)

    Write-Host 'Repeating install to verify idempotence and preservation...'
    Invoke-Installer

    $ReinstalledAgents = Read-Utf8 $AgentsPath
    Assert-True ([regex]::Matches($ReinstalledAgents, $JackBeginPattern).Count -eq 1) 'reinstall duplicated the Jack begin marker'
    Assert-True ([regex]::Matches($ReinstalledAgents, $JackEndPattern).Count -eq 1) 'reinstall duplicated the Jack end marker'
    Assert-True ($ReinstalledAgents.Contains('Keep this user-owned content exactly.')) 'reinstall removed user AGENTS.md content'
    Assert-True ((Read-Utf8 $UserSkillPath) -ceq $OriginalSkill) 'reinstall changed the user-owned skill'
    $PreservedPrompt = Get-ChildItem -LiteralPath (Split-Path -Parent $ManagedPromptPath) -Filter 'jack-codex-v1.md.jack-user-modified-*' | Select-Object -First 1
    $PreservedSkill = Get-ChildItem -LiteralPath (Split-Path -Parent $ManagedSkillTarget) -Directory -Filter ($ManagedSkill.Name + '.jack-user-modified-*') | Select-Object -First 1
    Assert-True ($null -ne $PreservedPrompt -and (Read-Utf8 $PreservedPrompt.FullName).Contains('USER_MODIFIED_INSTALLED_PROMPT')) 'reinstall did not preserve modified managed prompt'
    Assert-True ($null -ne $PreservedSkill -and (Read-Utf8 (Join-Path $PreservedSkill.FullName 'SKILL.md')).Contains('USER_MODIFIED_MANAGED_SKILL')) 'reinstall did not preserve modified managed skill'

    $skillsBlock = "`r`n# JACK-CODEX-SKILLS BEGIN`r`n[[skills.config]]`r`npath = `"$($ManagedSkillTarget.Replace([char]92, [char]47))/SKILL.md`"`r`nenabled = false`r`n# JACK-CODEX-SKILLS END`r`n"
    [System.IO.File]::AppendAllText($ConfigPath, $skillsBlock, $Utf8NoBom)

    Write-Host 'Uninstalling and verifying restoration...'
    Invoke-Installer -Uninstall

    $RestoredConfig = Read-Utf8 $ConfigPath
    $RestoredAgents = Read-Utf8 $AgentsPath
    Assert-True ($RestoredConfig.Contains($OriginalInstructionLine)) 'model_instructions_file was not restored'
    Assert-True ($RestoredConfig.Contains('custom_user_setting = "keep-me"')) 'uninstall removed unrelated config.toml content'
    Assert-True (-not $RestoredConfig.Contains('approval_policy = "never"')) 'uninstall left approval_policy patch'
    Assert-True (-not $RestoredConfig.Contains('sandbox_mode = "danger-full-access"')) 'uninstall left sandbox_mode patch'
    Assert-True (-not $RestoredConfig.Contains('# JACK-CODEX-PURGE')) 'uninstall left purge provider block'
    Assert-True (-not $RestoredConfig.Contains('model_provider = "jackpurge"')) 'uninstall left jackpurge provider'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $CodexHome '.jack-codex\jack-purge-proxy.mjs'))) 'uninstall left purge proxy'
    Assert-True (-not $RestoredConfig.Contains('# JACK-CODEX-SKILLS')) 'uninstall left the Jack Skills configuration block behind'
    Assert-True ($RestoredAgents.Contains('Keep this user-owned content exactly.')) 'uninstall removed user AGENTS.md content'
    Assert-True (-not [regex]::IsMatch($RestoredAgents, $JackBeginPattern)) 'Jack begin marker remains after uninstall'
    Assert-True (-not [regex]::IsMatch($RestoredAgents, $JackEndPattern)) 'Jack end marker remains after uninstall'
    Assert-True ((Read-Utf8 $UserSkillPath) -ceq $OriginalSkill) 'uninstall changed or removed the user-owned skill'
    Assert-True ((Read-Utf8 $ManagedPromptPath) -ceq $OriginalManagedPrompt) 'uninstall did not restore the pre-existing managed prompt'
    Assert-True ((Read-Utf8 (Join-Path $ManagedSkillTarget 'SKILL.md')) -ceq $OriginalCollidingSkill) 'uninstall did not restore the pre-existing colliding user skill'

    Write-Host 'Repeating uninstall to verify idempotence...'
    Invoke-Installer -Uninstall
    Assert-True ((Read-Utf8 $ConfigPath).Contains($OriginalInstructionLine)) 'repeated uninstall changed the restored model_instructions_file'
    Assert-True ((Read-Utf8 $AgentsPath).Contains('Keep this user-owned content exactly.')) 'repeated uninstall changed user AGENTS.md content'
    Assert-True ((Read-Utf8 $UserSkillPath) -ceq $OriginalSkill) 'repeated uninstall changed the user-owned skill'

    Write-Host 'Verifying post-install user instruction changes are preserved...'
    $CodexHome = Join-Path $TempRoot 'changed-instruction-home'
    $ConfigPath = Join-Path $CodexHome 'config.toml'
    New-Item -ItemType Directory -Force -Path $CodexHome | Out-Null
    [System.IO.File]::WriteAllText($ConfigPath, $OriginalConfig, $Utf8NoBom)
    Invoke-Installer
    $changedConfig = [regex]::Replace((Read-Utf8 $ConfigPath), '(?m)^\s*model_instructions_file\s*=\s*[^\r\n]*', 'model_instructions_file = "C:/user/prompts/changed-after-install.md"', 1)
    [System.IO.File]::WriteAllText($ConfigPath, $changedConfig, $Utf8NoBom)
    Invoke-Installer -Uninstall
    Assert-True ((Read-Utf8 $ConfigPath).Contains('changed-after-install.md')) 'uninstall clobbered a post-install user instruction change'

    Write-Host 'Verifying a fresh config is fully removed...'
    $CodexHome = Join-Path $TempRoot 'fresh-home'
    $ConfigPath = Join-Path $CodexHome 'config.toml'
    Invoke-Installer
    Assert-True (Test-Path -LiteralPath $ConfigPath) 'fresh install did not create config.toml'
    Invoke-Installer -Uninstall
    Assert-True (-not (Test-Path -LiteralPath $ConfigPath)) 'uninstall left an empty config.toml that did not exist before install'

    Write-Host 'Verifying failed installs roll back every mutation...'
    $FailureSource = Join-Path $FixtureRoot 'failure-source'
    $FailureSkill = Join-Path $FailureSource 'failure-skill\SKILL.md'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $FailureSkill) | Out-Null
    [System.IO.File]::WriteAllText($FailureSkill, "---`nname: failure-skill`ndescription: rollback fixture`n---`n", $Utf8NoBom)
    $CodexHome = Join-Path $TempRoot 'rollback-home'
    $ConfigPath = Join-Path $CodexHome 'config.toml'
    $AgentsPath = Join-Path $CodexHome 'AGENTS.md'
    New-Item -ItemType Directory -Force -Path $CodexHome | Out-Null
    [System.IO.File]::WriteAllText($ConfigPath, $OriginalConfig, $Utf8NoBom)
    [System.IO.File]::WriteAllText($AgentsPath, $OriginalAgents, $Utf8NoBom)
    $lock = [System.IO.File]::Open($FailureSkill, [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::None)
    try { Invoke-Installer -SkillsSourceArgument $FailureSource -ExpectFailure }
    finally { $lock.Dispose() }
    Assert-True ((Read-Utf8 $ConfigPath) -ceq $OriginalConfig) 'failed install did not roll back config.toml'
    Assert-True ((Read-Utf8 $AgentsPath) -ceq $OriginalAgents) 'failed install did not roll back AGENTS.md'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $CodexHome '.jack-codex\install-state.json'))) 'failed install left a transaction state'

    Write-Host 'Verifying upgrades retire removed managed Skills and restore collisions...'
    $V1Source = Join-Path $FixtureRoot 'v1-source'
    $V2Source = Join-Path $FixtureRoot 'v2-source'
    $RetiredSourceSkill = Join-Path $V1Source 'retired-skill\SKILL.md'
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $RetiredSourceSkill), $V2Source | Out-Null
    [System.IO.File]::WriteAllText($RetiredSourceSkill, "---`nname: retired-skill`ndescription: managed v1 fixture`n---`nMANAGED_V1`n", $Utf8NoBom)
    $CodexHome = Join-Path $TempRoot 'upgrade-home'
    $RetiredTarget = Join-Path $CodexHome 'skills\retired-skill'
    New-Item -ItemType Directory -Force -Path $RetiredTarget | Out-Null
    $RetiredUserContent = "---`nname: retired-skill`ndescription: user collision`n---`nUSER_RETIRED_COLLISION`n"
    [System.IO.File]::WriteAllText((Join-Path $RetiredTarget 'SKILL.md'), $RetiredUserContent, $Utf8NoBom)
    Invoke-Installer -SkillsSourceArgument $V1Source
    Invoke-Installer -SkillsSourceArgument $V2Source
    Assert-True ((Read-Utf8 (Join-Path $RetiredTarget 'SKILL.md')) -ceq $RetiredUserContent) 'upgrade did not restore a collision for a retired managed Skill'
    $upgradeState = Read-Utf8 (Join-Path $CodexHome '.jack-codex\install-state.json') | ConvertFrom-Json
    Assert-True (@($upgradeState.skills).Count -eq 0) 'upgrade kept a retired Skill in the new manifest'
    Invoke-Installer -Uninstall -SkillsSourceArgument $V2Source
    Assert-True ((Read-Utf8 (Join-Path $RetiredTarget 'SKILL.md')) -ceq $RetiredUserContent) 'uninstall changed the restored retired user Skill'

    Write-Host 'Verifying packaged uninstall uses the pinned CODEX_HOME...'
    $PinnedHome = Join-Path $TempRoot 'pinned-home'
    $WrongHome = Join-Path $TempRoot 'wrong-home'
    $CodexHome = $PinnedHome
    Invoke-Installer -SkillsSourceArgument $V2Source
    $FakeAppData = Join-Path $TempRoot 'appdata'
    $DesktopStateDir = Join-Path $FakeAppData 'jack-codex'
    New-Item -ItemType Directory -Force -Path $DesktopStateDir, $WrongHome | Out-Null
    $DesktopState = [ordered]@{ installed = $true; installedCodexHome = $PinnedHome; autoInstall = $false; manifest = @{ skills = @() } }
    [System.IO.File]::WriteAllText((Join-Path $DesktopStateDir 'jack-desktop-state.json'), (($DesktopState | ConvertTo-Json -Depth 5) + "`n"), $Utf8NoBom)
    $env:APPDATA = $FakeAppData
    $env:CODEX_HOME = $WrongHome
    & (Get-Process -Id $PID).Path -NoProfile -NonInteractive -File $ClearScript -Apply
    Assert-True ($LASTEXITCODE -eq 0) 'pinned CODEX_HOME uninstall wrapper failed'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $PinnedHome '.jack-codex\install-state.json'))) 'wrapper did not uninstall the pinned CODEX_HOME'
    Assert-True (-not (Test-Path -LiteralPath (Join-Path $WrongHome '.jack-codex\install-state.json'))) 'wrapper modified the current but unrelated CODEX_HOME'

    Write-Host 'PASS: installer lifecycle, rollback, pinned uninstall, collision restoration, and upgrades preserve user content.' -ForegroundColor Green
} finally {
    $env:CODEX_HOME = $OldCodexHome
    $env:APPDATA = $OldAppData
    if (Test-Path -LiteralPath $TempRoot) {
        Remove-Item -LiteralPath $TempRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $FixtureRoot) {
        Remove-Item -LiteralPath $FixtureRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
}
