<#
.SYNOPSIS
    RootTrace Initialization & Startup Script for Windows (PowerShell)
.DESCRIPTION
    Automates the startup of the entire RootTrace autonomous incident investigation stack:
    1. Validates .env configuration and deploys.json data files.
    2. Starts the host Ollama LLM service and verifies the Qwen model.
    3. Starts Docker Desktop daemon and waits for engine readiness.
    4. Launches all 8 Docker microservices (investigator, demo frontend, checkout, db, prometheus, loki, alloy, loadgen).
    5. Performs health checks and displays active dashboard URLs.
.PARAMETER Build
    Force a rebuild of Docker containers (--build).
.PARAMETER SkipOllama
    Skip starting the local Ollama background process (useful if using remote LLM endpoint).
.EXAMPLE
    .\scripts\init.ps1
.EXAMPLE
    .\scripts\init.ps1 -Build
#>

[CmdletBinding()]
param(
    [switch]$Build,
    [switch]$SkipOllama
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Set-Location $ProjectRoot

Write-Host ""
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "   ROOT-TRACE · Autonomous Incident Investigator Initializer    " -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "Project Root: $ProjectRoot" -ForegroundColor DarkGray
Write-Host ""

# -------------------------------------------------------------
# 1. Environment & Data Files
# -------------------------------------------------------------
Write-Host "[1/5] Checking environment configuration..." -ForegroundColor Yellow

$EnvFile = Join-Path $ProjectRoot ".env"
$EnvExample = Join-Path $ProjectRoot ".env.example"
if (-not (Test-Path $EnvFile)) {
    if (Test-Path $EnvExample) {
        Copy-Item $EnvExample $EnvFile
        Write-Host "  -> Created .env from .env.example" -ForegroundColor Green
    } else {
        Write-Host "  -> Warning: .env.example not found" -ForegroundColor DarkYellow
    }
} else {
    Write-Host "  -> .env file is present" -ForegroundColor Green
}

$DataDir = Join-Path $ProjectRoot "data"
if (-not (Test-Path $DataDir)) {
    New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
}
$DeploysFile = Join-Path $DataDir "deploys.json"
if (-not (Test-Path $DeploysFile)) {
    "[]" | Out-File -FilePath $DeploysFile -Encoding utf8
    Write-Host "  -> Initialized data/deploys.json" -ForegroundColor Green
} else {
    Write-Host "  -> data/deploys.json is present" -ForegroundColor Green
}

# -------------------------------------------------------------
# 2. Host Ollama LLM Service
# -------------------------------------------------------------
if (-not $SkipOllama) {
    Write-Host ""
    Write-Host "[2/5] Checking host Ollama LLM service..." -ForegroundColor Yellow

    $OllamaRunning = $false
    try {
        $res = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 -ErrorAction SilentlyContinue
        if ($res) { $OllamaRunning = $true }
    } catch {}

    if (-not $OllamaRunning) {
        Write-Host "  -> Ollama is not running. Attempting to start Ollama daemon..." -ForegroundColor DarkYellow
        $OllamaExe = $null

        $Cmd = Get-Command "ollama" -ErrorAction SilentlyContinue
        if ($Cmd) {
            $OllamaExe = $Cmd.Source
        } elseif (Test-Path "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe") {
            $OllamaExe = "$env:LOCALAPPDATA\Programs\Ollama\ollama.exe"
        }

        if ($OllamaExe) {
            Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden
            Write-Host "  -> Started Ollama serve in background ($OllamaExe)" -ForegroundColor DarkCyan

            # Wait up to 15s for Ollama to become responsive
            $Elapsed = 0
            while ($Elapsed -lt 15) {
                Start-Sleep -Seconds 2
                $Elapsed += 2
                try {
                    $res = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 2 -ErrorAction SilentlyContinue
                    if ($res) {
                        $OllamaRunning = $true
                        break
                    }
                } catch {}
            }
        } else {
            Write-Host "  -> Warning: ollama.exe not found in PATH or standard LocalAppData. Please start Ollama manually." -ForegroundColor DarkYellow
        }
    }

    if ($OllamaRunning) {
        Write-Host "  -> Ollama service is active on http://localhost:11434" -ForegroundColor Green
        try {
            $models = (Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -TimeoutSec 3).models.name
            Write-Host "  -> Available models: $($models -join ', ')" -ForegroundColor DarkGray
            if ($models -notcontains "qwen2.5:7b-8k" -and $models -notcontains "qwen2.5:7b") {
                Write-Host "  -> Notice: qwen2.5:7b-8k is recommended for RootTrace tool-calling." -ForegroundColor DarkYellow
            }
        } catch {}
    }
} else {
    Write-Host ""
    Write-Host "[2/5] Skipping Ollama check (-SkipOllama specified)" -ForegroundColor DarkGray
}

# -------------------------------------------------------------
# 3. Docker Desktop Engine
# -------------------------------------------------------------
Write-Host ""
Write-Host "[3/5] Checking Docker Desktop daemon..." -ForegroundColor Yellow

$DockerRunning = $false
docker info 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    $DockerRunning = $true
}

if (-not $DockerRunning) {
    Write-Host "  -> Docker is not running. Launching Docker Desktop engine..." -ForegroundColor DarkYellow
    $DockerDesktopExe = "$env:LOCALAPPDATA\Programs\DockerDesktop\Docker Desktop.exe"
    $DockerBackendExe = "$env:LOCALAPPDATA\Programs\DockerDesktop\resources\com.docker.backend.exe"
    $DockerProgFiles = "$env:ProgramFiles\Docker\Docker\Docker Desktop.exe"

    if (Test-Path $DockerBackendExe) {
        Start-Process -FilePath $DockerBackendExe -ArgumentList "-v" -WindowStyle Hidden
        Write-Host "  -> Launched com.docker.backend.exe in background" -ForegroundColor DarkCyan
    } elseif (Test-Path $DockerDesktopExe) {
        $WorkDir = "$env:LOCALAPPDATA\Programs\DockerDesktop\frontend"
        Start-Process -FilePath $DockerDesktopExe -WorkingDirectory $WorkDir
        Write-Host "  -> Launched Docker Desktop.exe" -ForegroundColor DarkCyan
    } elseif (Test-Path $DockerProgFiles) {
        Start-Process -FilePath $DockerProgFiles
        Write-Host "  -> Launched Docker Desktop from Program Files" -ForegroundColor DarkCyan
    }

    # Wait up to 60s for Docker to be ready
    $Timeout = 60
    $Elapsed = 0
    Write-Host "  -> Waiting for Docker daemon to become responsive..." -NoNewline
    while ($Elapsed -lt $Timeout) {
        Start-Sleep -Seconds 3
        $Elapsed += 3
        Write-Host "." -NoNewline
        docker info 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $DockerRunning = $true
            break
        }
    }
    Write-Host ""

    if (-not $DockerRunning) {
        Write-Error "Docker failed to become ready within $Timeout seconds. Please open Docker Desktop manually and retry."
        exit 1
    }
}

Write-Host "  -> Docker engine is responsive" -ForegroundColor Green

# -------------------------------------------------------------
# 4. Docker Compose Services
# -------------------------------------------------------------
Write-Host ""
Write-Host "[4/5] Starting application microservices via Docker Compose..." -ForegroundColor Yellow

$ComposeArgs = @("compose", "up", "-d")
if ($Build) {
    $ComposeArgs += "--build"
    Write-Host "  -> Running 'docker compose up -d --build'..." -ForegroundColor DarkCyan
} else {
    Write-Host "  -> Running 'docker compose up -d'..." -ForegroundColor DarkCyan
}

& docker @ComposeArgs
if ($LASTEXITCODE -ne 0) {
    Write-Error "docker compose failed to start containers. Exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}

# -------------------------------------------------------------
# 5. Health Checks & Verification
# -------------------------------------------------------------
Write-Host ""
Write-Host "[5/5] Verifying service health..." -ForegroundColor Yellow

$ServicesToCheck = @(
    @{ Name = "Investigator (API & UI)"; Url = "http://localhost:8000/health"; Expected = 200 },
    @{ Name = "ShopLite Demo Frontend";   Url = "http://localhost:8001/health"; Expected = 200 },
    @{ Name = "Checkout Microservice";    Url = "http://localhost:8002/health"; Expected = 200 },
    @{ Name = "Database Service";         Url = "http://localhost:8003/health"; Expected = 200 },
    @{ Name = "Prometheus TSDB";          Url = "http://localhost:9090/-/healthy"; Expected = 200 },
    @{ Name = "Grafana Loki";             Url = "http://localhost:3100/ready"; Expected = 200 }
)

# Brief wait for services like Loki to stabilize
Start-Sleep -Seconds 4

foreach ($svc in $ServicesToCheck) {
    $status = "Waiting..."
    $retries = 6
    while ($retries -gt 0) {
        try {
            $res = Invoke-WebRequest -Uri $svc.Url -UseBasicParsing -TimeoutSec 3 -ErrorAction SilentlyContinue
            if ($res.StatusCode -eq $svc.Expected) {
                $status = "Healthy ($($res.StatusCode))"
                break
            }
        } catch {}
        Start-Sleep -Seconds 2
        $retries--
    }

    if ($status -like "Healthy*") {
        Write-Host "  -> [OK] $($svc.Name) is $status" -ForegroundColor Green
    } else {
        Write-Host "  -> [WARN] $($svc.Name) did not report ready ($($svc.Url))" -ForegroundColor DarkYellow
    }
}

Write-Host ""
Write-Host "=================================================================" -ForegroundColor Green
Write-Host "   ROOT-TRACE STACK IS UP AND READY!                            " -ForegroundColor Green
Write-Host "=================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  • Investigator Console (UI & API) : http://localhost:8000" -ForegroundColor Cyan
Write-Host "  • ShopLite Demo Storefront        : http://localhost:8001" -ForegroundColor White
Write-Host "  • Prometheus Time-Series Metrics  : http://localhost:9090" -ForegroundColor White
Write-Host "  • Grafana Loki Logs Pipeline      : http://localhost:3100" -ForegroundColor White
Write-Host "  • Grafana Alloy Debug Interface   : http://localhost:12345" -ForegroundColor White
Write-Host "  • Host Ollama LLM Runner          : http://localhost:11434" -ForegroundColor White
Write-Host ""
Write-Host "To inject test incidents from the terminal:" -ForegroundColor DarkGray
Write-Host "  python scripts/inject_fault.py db_errors" -ForegroundColor DarkGray
Write-Host "  python scripts/inject_fault.py db_latency" -ForegroundColor DarkGray
Write-Host "  python scripts/inject_fault.py reset" -ForegroundColor DarkGray
Write-Host ""
