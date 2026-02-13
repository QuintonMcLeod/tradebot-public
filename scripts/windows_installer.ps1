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

try {
    # Fix Working Directory (Admin elevation defaults to System32)
    # We want to be in the project root (one level up from scripts/)
    Set-Location -Path "$PSScriptRoot\.."
    
    Write-Header "Tradebot SCI - Windows Auto-Installer"

    # 2. Check/Install Python 3.12
    Write-Info "Checking for Python..."
    $PythonPath = Get-Command "python" -ErrorAction SilentlyContinue
    $PythonVersion = ""
    
    if ($PythonPath) {
        try {
            # Try to run python --version. If it's corrupted, this might throw or exit code != 0
            $ProcessInfo = Start-Process "python" -ArgumentList "--version" -NoNewWindow -Wait -PassThru -ErrorAction SilentlyContinue
            if ($ProcessInfo.ExitCode -eq 0) {
                 $PythonVersion = python --version 2>&1
            } else {
                 Write-Info "Existing Python found but returned error code $($ProcessInfo.ExitCode). Treating as missing/broken."
            }
        } catch {
            Write-Info "Existing Python is broken (caused error during check). Ignoring."
        }
    }

    # Logic: If no python, OR python is weird store shim, OR python is not 3.11+
    $NeedPython = $true
    if ($PythonVersion -match "3\.(11|12|13)") {
        Write-Success "Python found: $PythonVersion"
        $NeedPython = $false
    } else {
        if ($PythonVersion) {
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
    Write-Info "Bootstrapping pip..."
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
    Write-Info "Installing Python Dependencies via Poetry..."
    # [ANTIGRAVITY] Auto-fix stale poetry.lock (common after git pull)
    Write-Info "Syncing poetry.lock with pyproject.toml..."
    $Poetry = Get-Command "poetry" -ErrorAction SilentlyContinue
    if ($Poetry) {
        poetry lock
        poetry install --with gui
    } else {
        # Fallback absolute path check
        $PoetryPath = "$env:APPDATA\Python\Scripts\poetry.exe"
        if (Test-Path $PoetryPath) {
            & $PoetryPath lock
            & $PoetryPath install --with gui
        } else {
            # Try to find it dynamically like in bash script
            $Found = Get-ChildItem "$env:APPDATA\Python" -Filter "poetry.exe" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($Found) {
                 & $Found.FullName lock
                 & $Found.FullName install --with gui
            } else {
                throw "Poetry installed but not found. Please restart PowerShell."
            }
        }
    }

    # Install GUI Dependencies (NPM) - CRITICAL FOR ELECTRON
    Write-Info "Installing GUI Dependencies (npm)..."
    Push-Location "src/tradebot_sci/electron_gui"
    try {
        if (Get-Command "npm" -ErrorAction SilentlyContinue) {
             # /c /q makes it a bit quieter, but we want to see errors if any
             Start-Process "npm.cmd" -ArgumentList "install" -NoNewWindow -Wait
        } else {
             Write-ErrorMsg "npm not found! GUI will not work."
        }
    } catch {
        Write-ErrorMsg "Failed to run npm install: $($_.Exception.Message)"
    }
    Pop-Location

    # 5. Create Launch Script & Shortcut
    Write-Header "Creating Shortcuts..."

    $WinDir = "$PWD".Replace("/", "\")
    $BashPath = Get-Command "bash.exe" -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source
    
    # 5a. Create launch_windows.bat in scripts folder (not desktop)
    $LauncherBat = "$PWD\scripts\launch_windows.bat"
    
    $Content = "@echo off`r`n"
    $Content += "cd /d `"$WinDir`"`r`n"
    
    if (-not $BashPath) {
        # Native Windows Launch
        $Content += "cd src\tradebot_sci\electron_gui`r`n"
        $Content += "npm start`r`n"
        $Content += "if %errorlevel% neq 0 (`r`n"
        $Content += "  echo GUI Launch Failed. Installing dependencies...`r`n"
        $Content += "  npm install && npm start`r`n"
        $Content += ")`r`n"
    } else {
        # Git Bash Launch
        $Content += "bash scripts/tradebot.sh --gui`r`n"
    }
    # Pause only on error
    $Content += "if %errorlevel% neq 0 pause`r`n"

    Set-Content -Path $LauncherBat -Value $Content
    Write-Success "Created Launcher Script: $LauncherBat"

    # 5b. Create proper .lnk Shortcut on Desktop
    $DesktopPath = [Environment]::GetFolderPath("Desktop")
    $ShortcutFile = "$DesktopPath\Tradebot SCI.lnk"
    
    $WScriptShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WScriptShell.CreateShortcut($ShortcutFile)
    
    # Target is the batch file
    $Shortcut.TargetPath = $LauncherBat
    $Shortcut.WorkingDirectory = $WinDir
    $Shortcut.Description = "Launch Tradebot SCI"
    
    # Icon: Use the .ico file for Windows compatibility
    $IconPath = "$WinDir\src\tradebot_sci\electron_gui\assets\icon.ico"
    if (Test-Path $IconPath) {
        $Shortcut.IconLocation = $IconPath
    }
    
    $Shortcut.Save()
    Write-Success "Shortcut created on Desktop: $ShortcutFile"

    # 6. Setup .env
    if (-not (Test-Path ".env")) {
        Copy-Item ".env.example" ".env"
        Write-Info "Created .env file. Please edit it with your API keys!"
    }

    Write-Header "INSTALLATION COMPLETE"
    Write-Success "You can now double-click the 'Tradebot SCI' icon on your desktop!"

} catch {
    Write-ErrorMsg "Installation Failed!"
    Write-ErrorMsg $_.Exception.Message
    Write-Host "StackTrace:"
    Write-Host $_.ScriptStackTrace
}

Read-Host "Press Enter to exit..."
