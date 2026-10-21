#requires -Version 5.1
<#
.SYNOPSIS
    AEO Suite - development environment checker (chunk 0.1).

.DESCRIPTION
    Verifies the required local toolchain for the no-Docker development
    setup (ADR-0001) on Windows. No external modules, PS 5.1 compatible.

    Exit code 0 = all required tools present and new enough.
    Exit code 1 = at least one required tool missing or outdated.

    Optional tools (uv, pnpm) are reported but do not fail the check.
#>

$ErrorActionPreference = 'Continue'
$script:Failures = 0

function Write-Check {
    param([string]$Status, [string]$Detail)
    $color = @{ OK = 'Green'; MISSING = 'Red'; OUTDATED = 'Red'; 'NOT FOUND' = 'Yellow'; INFO = 'DarkGray' }[$Status]
    Write-Host ("  [{0}] " -f $Status.PadRight(9)) -ForegroundColor $color -NoNewline
    Write-Host $Detail
}

function Get-FirstVersion {
    param([string]$Text)
    if ($Text -match '(\d+(\.\d+){1,3})') { return $Matches[1] }
    return $null
}

function Test-Tool {
    param(
        [string]$Label,
        [string[]]$ProbeCandidates,   # array of "cmd|arg1,arg2" probes, tried in order
        [System.Version]$MinVersion,  # $null = presence check only
        [string]$InstallHint,
        [switch]$Optional
    )
    Write-Host ("{0}" -f $Label.PadRight(10)) -NoNewline -ForegroundColor White

    $found = $false
    foreach ($probe in $ProbeCandidates) {
        $parts = $probe.Split('|')
        $cmd = $parts[0]
        $argList = @()
        if ($parts.Count -gt 1 -and $parts[1] -ne '') { $argList = $parts[1].Split(',') }

        if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { continue }
        try {
            $out = (& $cmd @argList 2>$null | Select-Object -First 1)
        } catch { continue }
        if (-not $out) { continue }

        $ver = Get-FirstVersion -Text ([string]$out)
        if ($MinVersion -and $ver) {
            try {
                $parsed = [System.Version]$ver
                if ($parsed -lt $MinVersion) {
                    Write-Check -Status 'OUTDATED' -Detail ("found {0}, need >= {1}" -f $ver, $MinVersion)
                    Write-Check -Status 'INFO' -Detail $InstallHint
                    if (-not $Optional) { $script:Failures++ }
                    return
                }
            } catch { }
        }
        Write-Check -Status 'OK' -Detail $out
        return
    }

    if ($Optional) {
        Write-Check -Status 'NOT FOUND' -Detail 'optional - install when convenient'
        Write-Check -Status 'INFO' -Detail $InstallHint
    } else {
        Write-Check -Status 'MISSING' -Detail 'required'
        Write-Check -Status 'INFO' -Detail $InstallHint
        $script:Failures++
    }
}

Write-Host ''
Write-Host '=== AEO Suite dev environment check (chunk 0.1) ===' -ForegroundColor Cyan
Write-Host 'Development runs WITHOUT Docker and WITHOUT Redis (ADR-0001/0002).' -ForegroundColor DarkGray
Write-Host ''

# ---- Required tools ----
Test-Tool -Label 'git' `
    -ProbeCandidates @('git|--version') `
    -MinVersion ([System.Version]'2.40.0') `
    -InstallHint 'winget install --id Git.Git'

Test-Tool -Label 'Python' `
    -ProbeCandidates @('py|-3,--version', 'python|--version') `
    -MinVersion ([System.Version]'3.12.0') `
    -InstallHint 'winget install --id Python.Python.3.12   (Django 6.0 floor is 3.12)'

Test-Tool -Label 'Node.js' `
    -ProbeCandidates @('node|--version') `
    -MinVersion ([System.Version]'20.0.0') `
    -InstallHint 'winget install --id OpenJS.NodeJS.LTS   (22 LTS recommended)'

Test-Tool -Label 'PostgreSQL' `
    -ProbeCandidates @('psql|--version') `
    -MinVersion ([System.Version]'16.0') `
    -InstallHint 'winget install --id PostgreSQL.PostgreSQL.16   (if installed but not on PATH, add e.g. C:\Program Files\PostgreSQL\16\bin)'

Test-Tool -Label 'Rust/cargo' `
    -ProbeCandidates @('cargo|--version') `
    -MinVersion $null `
    -InstallHint 'winget install --id Rustlang.Rustup   (stable toolchain; needed for crawler/ from chunk 1.1)'

# ---- Optional tools ----
Test-Tool -Label 'uv' `
    -ProbeCandidates @('uv|--version') `
    -MinVersion $null -Optional `
    -InstallHint "powershell -ExecutionPolicy ByPass -c `"irm https://astral.sh/uv/install.ps1 | iex`""

Test-Tool -Label 'pnpm' `
    -ProbeCandidates @('pnpm|--version') `
    -MinVersion $null -Optional `
    -InstallHint 'corepack enable   (then corepack prepare pnpm@latest --activate)'

Write-Host ''
if ($script:Failures -gt 0) {
    Write-Host ("RESULT: {0} required item(s) missing or outdated - fix and re-run." -f $script:Failures) -ForegroundColor Red
    exit 1
} else {
    Write-Host 'RESULT: all required tools present. You are ready for chunk 0.2.' -ForegroundColor Green
    exit 0
}
