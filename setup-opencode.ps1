# CCG OpenCode Setup Script for Windows
# This script configures Oh-My-OpenCode with CCG multi-agent collaboration
# Requires: PowerShell 5.1+ (Windows PowerShell) or PowerShell 7+ (pwsh)

# Force UTF-8 encoding
$PSDefaultParameterValues['Out-File:Encoding'] = 'utf8'
$PSDefaultParameterValues['Set-Content:Encoding'] = 'utf8'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Write-Step {
    param([string]$Message)
    Write-Host "`n[*] $Message" -ForegroundColor Cyan
}

function Write-Success {
    param([string]$Message)
    Write-Host "[OK] $Message" -ForegroundColor Green
}

function Write-ErrorMsg {
    param([string]$Message)
    Write-Host "[ERROR] $Message" -ForegroundColor Red
}

function Write-WarningMsg {
    param([string]$Message)
    Write-Host "[WARN] $Message" -ForegroundColor Yellow
}

# Helper function to read password (compatible with PowerShell 5.1 and 7+)
function Read-Password {
    param([string]$Prompt)

    # Check if -MaskInput is supported (PowerShell 7.1+)
    # Use -gt 7 to handle future versions (8.0+) correctly
    if ($PSVersionTable.PSVersion.Major -gt 7 -or ($PSVersionTable.PSVersion.Major -eq 7 -and $PSVersionTable.PSVersion.Minor -ge 1)) {
        return Read-Host $Prompt -MaskInput
    } else {
        # Fallback for PowerShell 5.1 and earlier 7.x versions
        $secureString = Read-Host $Prompt -AsSecureString
        $bstr = [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($secureString)
        try {
            return [System.Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
        } finally {
            [System.Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
        }
    }
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "   CCG OpenCode Setup - Multi-Agent Collaboration" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

# ==============================================================================
# Step 1: Check template files exist
# ==============================================================================
Write-Step "Step 1: Checking template files..."

$templateJson = Join-Path $PSScriptRoot "templates\opencode\opencode.json"
$templateOhMy = Join-Path $PSScriptRoot "templates\opencode\oh-my-opencode.json"
$templateAgents = Join-Path $PSScriptRoot "templates\opencode\AGENTS.md"

$missingTemplates = $false

if (!(Test-Path $templateJson)) {
    Write-ErrorMsg "Template not found: $templateJson"
    $missingTemplates = $true
}

if (!(Test-Path $templateOhMy)) {
    Write-ErrorMsg "Template not found: $templateOhMy"
    $missingTemplates = $true
}

if (!(Test-Path $templateAgents)) {
    Write-ErrorMsg "Template not found: $templateAgents"
    $missingTemplates = $true
}

if ($missingTemplates) {
    Write-Host ""
    Write-ErrorMsg "Please run this script from the CCG repository root directory."
    Write-Host "  Expected location: cd C:\path\to\Coder-Codex-Gemini; .\setup-opencode.ps1" -ForegroundColor Yellow
    exit 1
}

Write-Success "All template files found"

# ==============================================================================
# Step 2: Check dependencies
# ==============================================================================
Write-Step "Step 2: Checking dependencies..."

# Check bun (required for oh-my-opencode)
$bunInstalled = $false
$bunCmd = Get-Command bun -ErrorAction SilentlyContinue
if ($bunCmd) {
    $bunInstalled = $true
    Write-Success "bun is installed"
} else {
    Write-WarningMsg "bun is not installed, installing automatically..."
    Write-Host "  This will run: irm bun.sh/install.ps1 | iex" -ForegroundColor Gray
    $confirmBun = Read-Host "  Continue? (Y/n)"
    if ($confirmBun -eq "n" -or $confirmBun -eq "N") {
        Write-ErrorMsg "bun is required. Please install manually: https://bun.sh"
        exit 1
    }
    powershell -c "irm bun.sh/install.ps1 | iex"
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Failed to install bun automatically"
        Write-Host "Please install bun manually: https://bun.sh" -ForegroundColor Yellow
        exit 1
    }
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
    $bunCmd = Get-Command bun -ErrorAction SilentlyContinue
    if ($bunCmd) {
        $bunInstalled = $true
        Write-Success "bun installed successfully"
    } else {
        Write-ErrorMsg "Failed to verify bun installation"
        exit 1
    }
}

# Check opencode CLI
$opencodeInstalled = $false
$opencodeCmd = Get-Command opencode -ErrorAction SilentlyContinue
if ($opencodeCmd) {
    $opencodeInstalled = $true
    Write-Success "opencode CLI is installed"
} else {
    Write-WarningMsg "opencode CLI is not installed"
    Write-Host "Installing opencode via Scoop..." -ForegroundColor Yellow

    # Check if scoop is available
    $scoopCmd = Get-Command scoop -ErrorAction SilentlyContinue
    if (-not $scoopCmd) {
        Write-ErrorMsg "Scoop is not installed"
        Write-Host "Please install Scoop first: https://scoop.sh" -ForegroundColor Yellow
        Write-Host "Or install opencode manually: https://opencode.ai/docs" -ForegroundColor Yellow
        exit 1
    }

    scoop bucket add extras 2>$null
    scoop install extras/opencode
    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Failed to install opencode"
        Write-Host "Please install opencode manually:" -ForegroundColor Yellow
        Write-Host "  scoop bucket add extras" -ForegroundColor White
        Write-Host "  scoop install extras/opencode" -ForegroundColor White
        Write-Host "Or visit: https://opencode.ai/docs" -ForegroundColor White
        exit 1
    }
    $opencodeInstalled = $true
    Write-Success "opencode installed successfully"
}

# ==============================================================================
# Step 3: Install Oh-My-OpenCode
# ==============================================================================
Write-Step "Step 3: Installing Oh-My-OpenCode..."

# Check if oh-my-opencode is already configured
$ohMyJsonCheck = "$env:USERPROFILE\.config\opencode\oh-my-opencode.json"
$skipOhMyInstall = $false

if (Test-Path $ohMyJsonCheck) {
    Write-WarningMsg "Oh-My-OpenCode appears to be already installed"
    Write-Host "  Found: $ohMyJsonCheck" -ForegroundColor Gray
    $reinstall = Read-Host "Re-run oh-my-opencode install? This may modify your existing config (y/N)"
    if ($reinstall -ne "y" -and $reinstall -ne "Y") {
        Write-WarningMsg "Skipping Oh-My-OpenCode installation"
        $skipOhMyInstall = $true
    }
}

if (-not $skipOhMyInstall) {
    Write-Host "Please select your subscription status:" -ForegroundColor White
    Write-Host "  1) Claude Max 20 + ChatGPT + Gemini (Recommended)" -ForegroundColor White
    Write-Host "  2) Claude Pro + ChatGPT + Gemini" -ForegroundColor White
    Write-Host "  3) Custom (interactive TUI)" -ForegroundColor White
    $subscriptionChoice = Read-Host "Enter choice [1-3]"

    switch ($subscriptionChoice) {
        "1" {
            bunx oh-my-opencode install --no-tui --claude=max20 --chatgpt=yes --gemini=yes
        }
        "2" {
            bunx oh-my-opencode install --no-tui --claude=yes --chatgpt=yes --gemini=yes
        }
        "3" {
            bunx oh-my-opencode install
        }
        default {
            Write-WarningMsg "Invalid choice, using default (Claude Max 20)"
            bunx oh-my-opencode install --no-tui --claude=max20 --chatgpt=yes --gemini=yes
        }
    }

    if ($LASTEXITCODE -ne 0) {
        Write-ErrorMsg "Failed to install Oh-My-OpenCode"
        Write-Host "Please try running manually: bunx oh-my-opencode install" -ForegroundColor Yellow
        exit 1
    }

    Write-Success "Oh-My-OpenCode installed"
} else {
    Write-Success "Oh-My-OpenCode installation skipped (using existing config)"
}

# ==============================================================================
# Step 4: Configure opencode.json
# ==============================================================================
Write-Step "Step 4: Configuring opencode.json..."

$configDir = "$env:USERPROFILE\.config\opencode"
$opencodeJson = "$configDir\opencode.json"

if (!(Test-Path $configDir)) {
    New-Item -ItemType Directory -Path $configDir -Force | Out-Null
}

# Function to configure opencode.json
function Configure-OpencodeJson {
    Write-Host ""
    Write-Host "Configure Anthropic API (for Claude models):" -ForegroundColor White
    Write-Host "  (You can also use 'opencode auth login' later for OAuth authentication)" -ForegroundColor Gray
    $anthropicBaseUrl = Read-Host "  Base URL (default: https://api.anthropic.com/v1)"
    if ([string]::IsNullOrWhiteSpace($anthropicBaseUrl)) {
        $anthropicBaseUrl = "https://api.anthropic.com/v1"
    }

    $anthropicApiKey = Read-Password "  API Key (leave empty to use OAuth)"

    # Copy and configure template
    $content = Get-Content $templateJson -Raw -Encoding UTF8

    if (-not [string]::IsNullOrWhiteSpace($anthropicApiKey)) {
        # Use .Replace() instead of -replace to avoid regex interpretation
        $content = $content.Replace("__ANTHROPIC_BASE_URL__", $anthropicBaseUrl)
        $content = $content.Replace("__ANTHROPIC_API_KEY__", $anthropicApiKey)
        Write-Success "Configured Anthropic API"
        Write-WarningMsg "Note: API Key is stored in plaintext in $opencodeJson"
    } else {
        # Replace with default/empty values for OAuth flow
        $content = $content.Replace("__ANTHROPIC_BASE_URL__", "https://api.anthropic.com/v1")
        $content = $content.Replace("__ANTHROPIC_API_KEY__", "")
        Write-WarningMsg "Anthropic API Key not configured."
        Write-WarningMsg "Please use 'opencode auth login' for OAuth authentication."
    }

    # Write content with UTF-8 without BOM (critical for JSON parsers)
    # PowerShell 5.x's "Set-Content -Encoding UTF8" writes BOM which may break JSON parsing
    [System.IO.File]::WriteAllText($opencodeJson, $content, [System.Text.UTF8Encoding]::new($false))

    # Set file permissions - try to restrict to current user, but don't fail if ACL fails
    try {
        $acl = Get-Acl $opencodeJson
        $acl.SetAccessRuleProtection($true, $false)
        # Use current user's SID for more reliable permission setting
        $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent()
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($currentUser.User, "FullControl", "Allow")
        $acl.SetAccessRule($rule)
        Set-Acl $opencodeJson $acl
    } catch {
        Write-WarningMsg "Could not restrict file permissions: $_"
    }
}

$skipOpencodeConfig = $false

if (Test-Path $opencodeJson) {
    Write-WarningMsg "opencode.json already exists"
    $overwrite = Read-Host "Overwrite with CCG template? (y/N)"
    if ($overwrite -ne "y" -and $overwrite -ne "Y") {
        Write-WarningMsg "Skipping opencode.json configuration"
        Write-WarningMsg "Please manually merge CCG settings from: $templateJson"
        $skipOpencodeConfig = $true
    } else {
        # Backup existing config
        $backupName = "$opencodeJson.backup.$(Get-Date -Format 'yyyyMMddHHmmss')"
        Copy-Item $opencodeJson $backupName
        Write-Success "Backed up existing config to $backupName"
    }
}

if (-not $skipOpencodeConfig) {
    Configure-OpencodeJson
    Write-Success "opencode.json configured (permissions restricted to current user)"
}

# ==============================================================================
# Step 5: Configure oh-my-opencode.json
# ==============================================================================
Write-Step "Step 5: Configuring oh-my-opencode.json..."

$ohMyJson = "$configDir\oh-my-opencode.json"

$skipOhMyConfig = $false

if (Test-Path $ohMyJson) {
    Write-WarningMsg "oh-my-opencode.json already exists"
    $overwrite = Read-Host "Overwrite with CCG template? (y/N)"
    if ($overwrite -ne "y" -and $overwrite -ne "Y") {
        Write-WarningMsg "Skipping oh-my-opencode.json configuration"
        Write-WarningMsg "Please manually merge CCG settings from: $templateOhMy"
        $skipOhMyConfig = $true
    } else {
        $backupName = "$ohMyJson.backup.$(Get-Date -Format 'yyyyMMddHHmmss')"
        Copy-Item $ohMyJson $backupName
    }
}

if (-not $skipOhMyConfig) {
    Copy-Item $templateOhMy $ohMyJson -Force
    Write-Success "oh-my-opencode.json configured"
}

# ==============================================================================
# Step 6: Configure AGENTS.md
# ==============================================================================
Write-Step "Step 6: Configuring AGENTS.md..."

$agentsMd = "$configDir\AGENTS.md"

$skipAgentsConfig = $false

if (Test-Path $agentsMd) {
    Write-WarningMsg "AGENTS.md already exists"
    $overwrite = Read-Host "Overwrite with CCG template? (y/N)"
    if ($overwrite -ne "y" -and $overwrite -ne "Y") {
        Write-WarningMsg "Skipping AGENTS.md configuration"
        $skipAgentsConfig = $true
    } else {
        $backupName = "$agentsMd.backup.$(Get-Date -Format 'yyyyMMddHHmmss')"
        Copy-Item $agentsMd $backupName
    }
}

if (-not $skipAgentsConfig) {
    Copy-Item $templateAgents $agentsMd -Force
    Write-Success "AGENTS.md configured"
}

# ==============================================================================
# Step 7: Authentication reminder
# ==============================================================================
Write-Step "Step 7: Authentication setup..."

Write-Host ""
Write-Host "Please complete authentication for each provider:" -ForegroundColor White
Write-Host ""
Write-Host "  1. Anthropic (Claude):" -ForegroundColor Cyan
Write-Host "     opencode auth login" -ForegroundColor White
Write-Host "     -> Select: Anthropic -> Claude Pro/Max" -ForegroundColor Gray
Write-Host ""
Write-Host "  2. OpenAI (ChatGPT/Codex):" -ForegroundColor Cyan
Write-Host "     opencode auth login" -ForegroundColor White
Write-Host "     -> Select: OpenAI -> ChatGPT Plus/Pro (Codex Subscription)" -ForegroundColor Gray
Write-Host ""
Write-Host "  3. Google (Gemini):" -ForegroundColor Cyan
Write-Host "     opencode auth login" -ForegroundColor White
Write-Host "     -> Select: Google -> OAuth with Google (Antigravity)" -ForegroundColor Gray
Write-Host ""

# ==============================================================================
# Done!
# ==============================================================================
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Success "CCG OpenCode setup completed!"
Write-Host "============================================================" -ForegroundColor Green
Write-Host ""

Write-Host "Configuration files:" -ForegroundColor Cyan
Write-Host "  - $opencodeJson" -ForegroundColor White
Write-Host "  - $ohMyJson" -ForegroundColor White
Write-Host "  - $agentsMd" -ForegroundColor White
Write-Host ""

Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Complete authentication: opencode auth login" -ForegroundColor White
Write-Host "  2. Start OpenCode: opencode" -ForegroundColor White
Write-Host "  3. Use Tab to switch between build/plan mode" -ForegroundColor White
Write-Host ""

Write-Host "Note: If using Antigravity plugin for Gemini, ensure google_auth is set to false" -ForegroundColor Yellow
Write-Host ""
