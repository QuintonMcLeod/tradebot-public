<#
.SYNOPSIS
Tradebot SCI - One-Click Windows Installer
Automates the installation of Python, Node.js, Git, and project dependencies.

.DESCRIPTION
This script is designed for "newbie" Windows users. It performs:
1. Python 3.12 Check/Install (Automatic Download)
2. Node.js Check/Install (Automatic Download)
3. Poetry Bootstrap
4. Virtual Environment Creation
5. Dependency Installation
6. Desktop Shortcut Creation

.USAGE
Right-click > Run with PowerShell
#>

$ErrorActionPreference = "Stop"

function Write-Header {
    param($Text)
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host "   $Text" -ForegroundColor Cyan
    Write-Host "==========================================" -ForegroundColor Cyan
    Write-Host ""
}

function Write-Success {
    param($Text)
    Write-Host "[SUCCESS] $Text" -ForegroundColor Green
}

function Write-ErrorMsg {
    param($Text)
    Write-Host "[ERROR] $Text" -ForegroundColor Red
}

function Write-Info {
    param($Text)
    Write-Host "[INFO] $Text" -ForegroundColor Gray
}

# 1. Request Admin Privileges (needed for installing Python/Node)
if (-not ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole] "Administrator")) {
    Write-Host "Requesting Administrator privileges to install dependencies..." -ForegroundColor Yellow
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit
}

Write-Header "Tradebot SCI - Windows Auto-Installer"

# 2. Check/Install Python 3.12
$PythonPath = Get-Command "python" -ErrorAction SilentlyContinue
$PythonVersion = ""
if ($PythonPath) {
    $PythonVersion = python --version 2>&1
}

# Logic: If no python, OR python is weird store shim, OR python is not 3.11+
$NeedPython = $true
if ($PythonPath) {
    if ($PythonVersion -match "3\.(11|12|13)") {
        Write-Success "Python found: $PythonVersion"
        $NeedPython = $false
    } else {
        Write-Info "Python found but version ($PythonVersion) is not 3.11+. Upgrading..."
    }
}

if ($NeedPython) {
    Write-Header "Installing Python 3.12..."
    $PyInstaller = "$env:TEMP\python-3.12.1-amd64.exe"
    $PyUrl = "https://www.python.org/ftp/python/3.12.1/python-3.12.1-amd64.exe"
    
    Write-Info "Downloading Python 3.12 (25MB)..."
    Invoke-WebRequest -Uri $PyUrl -OutFile $PyInstaller
    
    Write-Info "Installing Python (Silent)... This may take a minute."
    # Install with AllUsers=1 PrependPath=1 to fix PATH issues
    Start-Process -FilePath $PyInstaller -ArgumentList "/quiet InstallAllUsers=1 PrependPath=1 Include_test=0" -Wait
    
    # Refresh Env Vars
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    Write-Success "Python 3.12 Installed."
}

# 3. Check/Install Node.js
if (-not (Get-Command "node" -ErrorAction SilentlyContinue)) {
    Write-Header "Installing Node.js (LTS)..."
    # Use Winget if available, else MSI
    if (Get-Command "winget" -ErrorAction SilentlyContinue) {
        Write-Info "Using Winget to install Node.js..."
        winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements --silent
    } else {
        $NodeMsi = "$env:TEMP\node-v20.msi"
        $NodeUrl = "https://nodejs.org/dist/v20.11.0/node-v20.11.0-x64.msi"
        Write-Info "Downloading Node.js..."
        Invoke-WebRequest -Uri $NodeUrl -OutFile $NodeMsi
        Write-Info "Installing Node.js..."
        Start-Process msiexec.exe -ArgumentList "/i `"$NodeMsi`" /qn" -Wait
    }
    # Refresh Path
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path","User")
    Write-Success "Node.js Installed."
} else {
    Write-Success "Node.js is already installed."
}

# 4. Bootstrap Project
Write-Header "Setting up Trade Bot..."

# Ensure Pip
python -m ensurepip --default-pip
python -m pip install --upgrade pip

# Install Poetry
Write-Info "Installing Poetry..."
python -m pip install poetry

# Setup Virtual Env
if (-not (Test-Path ".venv")) {
    Write-Info "Creating virtual environment..."
    python -m venv .venv
}

# Install Dependencies
Write-Info "Installing Dependencies via Poetry..."
$Poetry = Get-Command "poetry" -ErrorAction SilentlyContinue
if ($Poetry) {
    poetry install --with gui
} else {
    # Fallback absolute path check
    $PoetryPath = "$env:APPDATA\Python\Scripts\poetry.exe"
    if (Test-Path $PoetryPath) {
        & $PoetryPath install --with gui
    } else {
        Write-ErrorMsg "Poetry installed but not found in PATH. Please restart PowerShell and run again."
        Read-Host "Press Enter to Exit"
        exit
    }
}

# 5. Create Shortcut
Write-Header "Creating Shortcuts..."

$TargetScript = "$PWD\scripts\tradebot.sh"
$WinDir = "$PWD".Replace("/", "\")
$BashPath = Get-Command "bash.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source

$BatFile = "$env:USERPROFILE\Desktop\Tradebot SCI.bat"
$Content = "@echo off`r`ncd /d `"$WinDir`"`r`nbash scripts/tradebot.sh --gui`r`npause"
if (-not $BashPath) {
    # If no git bash, try simple python launch
    $Content = "@echo off`r`ncd /d `"$WinDir`"`r`ncall .venv\Scripts\activate`r`npython -m tradebot_sci --mode gui`r`npause"
}

Set-Content -Path $BatFile -Value $Content
Write-Success "Shortcut created on Desktop: $BatFile"

# 6. Setup .env
if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Info "Created .env file. Please edit it with your API keys!"
}

Write-Header "INSTALLATION COMPLETE"
Write-Success "You can now double-click the 'Tradebot SCI' icon on your desktop!"
Read-Host "Press Enter to exit..."
