$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-Native {
    param(
        [Parameter(Mandatory = $true)]
        [string] $FilePath,
        [Parameter(ValueFromRemainingArguments = $true)]
        [string[]] $Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Invoke-Step {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [scriptblock] $Action
    )

    Write-Host ""
    Write-Host "==> $Name"
    try {
        & $Action
    }
    catch {
        Write-Error "Step failed: $Name"
        Write-Error $_
        exit 1
    }
}

$ProjectRoot = Split-Path -Parent $PSCommandPath
Set-Location -LiteralPath $ProjectRoot

Invoke-Step "Phase 1: clean local caches and compiled Python artifacts" {
    $cacheDirectories = @("__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache")
    foreach ($cacheName in $cacheDirectories) {
        Get-ChildItem -LiteralPath $ProjectRoot -Recurse -Force -Directory -Filter $cacheName |
            Where-Object {
                $_.FullName.StartsWith($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)
            } |
            Remove-Item -Recurse -Force
    }

    foreach ($pattern in @("*.pyc", "*.pyo")) {
        Get-ChildItem -LiteralPath $ProjectRoot -Recurse -Force -File -Filter $pattern |
            Where-Object {
                $_.FullName.StartsWith($ProjectRoot, [System.StringComparison]::OrdinalIgnoreCase)
            } |
            Remove-Item -Force
    }
}

Invoke-Step "Phase 2: create isolated virtual environment and install dependencies" {
    if (Test-Path -LiteralPath ".venv") {
        Remove-Item -LiteralPath ".venv" -Recurse -Force
    }

    if (Get-Command py -ErrorAction SilentlyContinue) {
        $created = $false
        foreach ($version in @("-3.12", "-3.11", "-3.10", "-3")) {
            & py $version -m venv .venv
            if ($LASTEXITCODE -eq 0) {
                $created = $true
                break
            }
        }
        if (-not $created) {
            throw "Unable to create a virtual environment with Python 3.10 or newer."
        }
    }
    elseif (Get-Command python -ErrorAction SilentlyContinue) {
        Invoke-Native "python" "-m" "venv" ".venv"
    }
    else {
        throw "No Python launcher found. Install Python 3.10 or newer."
    }

    $VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $VenvPython)) {
        throw "Virtual environment Python was not created at $VenvPython."
    }

    Invoke-Native $VenvPython "-m" "pip" "install" "--upgrade" "pip"
    Invoke-Native $VenvPython "-m" "pip" "install" ".[dev]"
}

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

Invoke-Step "Phase 3a: ruff format check" {
    Invoke-Native $VenvPython "-m" "ruff" "format" "--check" "."
}

Invoke-Step "Phase 3b: ruff lint with safe fixes" {
    Invoke-Native $VenvPython "-m" "ruff" "check" "." "--fix"
}

Invoke-Step "Phase 3c: mypy strict type check" {
    Invoke-Native $VenvPython "-m" "mypy" "--strict" "src" "tests"
}

Invoke-Step "Phase 3d: pytest full suite" {
    Invoke-Native $VenvPython "-m" "pytest"
}

Invoke-Step "Phase 4: build wheel and source distribution with Hatch" {
    if (Test-Path -LiteralPath "dist") {
        Remove-Item -LiteralPath "dist" -Recurse -Force
    }

    Invoke-Native $VenvPython "-m" "hatch" "build"

    $wheels = @(Get-ChildItem -LiteralPath "dist" -Filter "*.whl" -File)
    $sdists = @(Get-ChildItem -LiteralPath "dist" -Filter "*.tar.gz" -File)
    if ($wheels.Count -lt 1 -or $sdists.Count -lt 1) {
        throw "Expected both wheel (*.whl) and source distribution (*.tar.gz) in dist/."
    }
}

Invoke-Step "Phase 5: initialize Git repository and create first commit" {
    & git rev-parse --is-inside-work-tree *> $null
    if ($LASTEXITCODE -ne 0) {
        Invoke-Native "git" "init"
    }

    Invoke-Native "git" "add" "-A"
    & git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "No staged changes to commit."
    }
    else {
        Invoke-Native "git" "commit" "-m" "chore: initial production-ready package structure with fair chain complex verification"
    }
}

Write-Host ""
Write-Host "Setup, verification, build, and Git registration completed successfully."
