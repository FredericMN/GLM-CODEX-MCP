# CCG One-Click Setup Script for Windows
# This script automates the setup of Coder-Codex-Gemini MCP server

# Force UTF-8 encoding for file operations
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

# ==============================================================================
# Step 1: Check dependencies
# ==============================================================================
Write-Step "Step 1: Checking dependencies..."

# Check and install uv
$uvInstalled = $false
try {
    $null = uv --version 2>&1
    $uvInstalled = $true
    Write-Success "uv is installed"
} catch {
    Write-WarningMsg "uv is not installed, installing automatically..."
    try {
        powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
        # Refresh PATH
        $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [System.Environment]::GetEnvironmentVariable("Path", "User")
        $null = uv --version 2>&1
        $uvInstalled = $true
        Write-Success "uv installed successfully"
    } catch {
        Write-ErrorMsg "Failed to install uv automatically"
        Write-Host "Please install uv manually: https://github.com/astral-sh/uv" -ForegroundColor Yellow
        exit 1
    }
}

# Check claude CLI
$claudeInstalled = $false
try {
    $null = claude --version 2>&1
    $claudeInstalled = $true
    Write-Success "claude CLI is installed"
} catch {
    Write-ErrorMsg "claude CLI is not installed"
    Write-Host "Please install Claude Code CLI first: https://docs.anthropic.com/en/docs/claude-code" -ForegroundColor Yellow
    exit 1
}

# ==============================================================================
# Step 2: Install project dependencies
# ==============================================================================
Write-Step "Step 2: Installing project dependencies..."

try {
    uv sync
    Write-Success "Project dependencies installed"
} catch {
    Write-ErrorMsg "Failed to install dependencies"
    exit 1
}

# ==============================================================================
# Step 3: Register MCP server
# ==============================================================================
Write-Step "Step 3: Registering MCP server..."

# Temporarily relax error handling for native commands in Step 3
$oldErrorActionPreference = $ErrorActionPreference
$oldNativeCommandEap = $null
$ErrorActionPreference = "Continue"
if ($PSVersionTable.PSVersion.Major -ge 7) {
    $oldNativeCommandEap = $PSNativeCommandUseErrorActionPreference
    $PSNativeCommandUseErrorActionPreference = $false
}

try {
    # Try to remove existing ccg MCP server if it exists
    try {
        $null = claude mcp remove ccg --scope user 2>&1
        Write-WarningMsg "Removed existing ccg MCP server"
    } catch {
        # Ignore if it doesn't exist
    }

    # Check uv version to determine if --refresh is supported
    $mcpRegistered = $false
    $lastError = ""
    $useRefresh = $false
    $uvVersionKnown = $false

    try {
        $uvVersionOutput = uv --version 2>&1
        if ($uvVersionOutput -match "uv (\d+)\.(\d+)\.(\d+)") {
            $uvVersionKnown = $true
            $major = [int]$Matches[1]
            $minor = [int]$Matches[2]
            # --refresh requires uv >= 0.4.0
            if ($major -gt 0 -or ($major -eq 0 -and $minor -ge 4)) {
                $useRefresh = $true
            }
        }
    } catch {
        # If we can't determine version, don't use --refresh
    }

    if ($useRefresh) {
        # Try with --refresh first
        $refreshOutput = claude mcp add ccg --scope user --transport stdio -- uvx --refresh --from git+https://github.com/FredericMN/Coder-Codex-Gemini.git ccg-mcp 2>&1
        if ($LASTEXITCODE -eq 0) {
            $mcpRegistered = $true
            Write-Success "MCP server registered (with --refresh)"
        } elseif ($refreshOutput -match "(?i)(unknown|unrecognized|unexpected|invalid).*(option|flag|argument).*--refresh|--refresh.*(unknown|unrecognized|unexpected|invalid)") {
            # Fallback: --refresh was rejected (covers various CLI error message formats), try without it
            Write-WarningMsg "--refresh option was rejected, falling back to installation without --refresh..."
            $fallbackOutput = claude mcp add ccg --scope user --transport stdio -- uvx --from git+https://github.com/FredericMN/Coder-Codex-Gemini.git ccg-mcp 2>&1
            if ($LASTEXITCODE -eq 0) {
                $mcpRegistered = $true
                Write-Success "MCP server registered (without --refresh)"
            } else {
                $lastError = $fallbackOutput
            }
        } else {
            $lastError = $refreshOutput
        }
    } else {
        # uv version too old or unknown, skip --refresh
        if ($uvVersionKnown) {
            Write-WarningMsg "Your uv version does not support --refresh option (requires uv >= 0.4.0)"
        } else {
            Write-WarningMsg "Could not determine uv version, skipping --refresh option"
        }
        Write-WarningMsg "Installing without --refresh..."
        Write-WarningMsg "Consider upgrading uv: powershell -c `"irm https://astral.sh/uv/install.ps1 | iex`""

        $fallbackOutput = claude mcp add ccg --scope user --transport stdio -- uvx --from git+https://github.com/FredericMN/Coder-Codex-Gemini.git ccg-mcp 2>&1
        if ($LASTEXITCODE -eq 0) {
            $mcpRegistered = $true
            Write-Success "MCP server registered (without --refresh)"
        } else {
            $lastError = $fallbackOutput
        }
    }

    if (-not $mcpRegistered) {
        Write-ErrorMsg "Failed to register MCP server"
        Write-Host "Error details: $lastError" -ForegroundColor Red
        exit 1
    }
} finally {
    $ErrorActionPreference = $oldErrorActionPreference
    if ($PSVersionTable.PSVersion.Major -ge 7) {
        $PSNativeCommandUseErrorActionPreference = $oldNativeCommandEap
    }
}

# ==============================================================================
# Step 4: Install Skills
# ==============================================================================
Write-Step "Step 4: Installing Skills..."

$skillsDir = "$env:USERPROFILE\.claude\skills"
$ccgWorkflowSource = Join-Path $PSScriptRoot "skills\ccg-workflow"
$geminiCollabSource = Join-Path $PSScriptRoot "skills\gemini-collaboration"

try {
    # Create skills directory if it doesn't exist
    if (!(Test-Path $skillsDir)) {
        New-Item -ItemType Directory -Path $skillsDir -Force | Out-Null
        Write-Success "Created skills directory: $skillsDir"
    }

    # Copy ccg-workflow skill
    if (Test-Path $ccgWorkflowSource) {
        $dest = "$skillsDir\ccg-workflow"
        if (Test-Path $dest) {
            Remove-Item -Recurse -Force $dest
        }
        Copy-Item -Recurse $ccgWorkflowSource $dest
        Write-Success "Installed ccg-workflow skill"
    } else {
        Write-WarningMsg "ccg-workflow skill not found, skipping"
    }

    # Copy gemini-collaboration skill
    if (Test-Path $geminiCollabSource) {
        $dest = "$skillsDir\gemini-collaboration"
        if (Test-Path $dest) {
            Remove-Item -Recurse -Force $dest
        }
        Copy-Item -Recurse $geminiCollabSource $dest
        Write-Success "Installed gemini-collaboration skill"
    } else {
        Write-WarningMsg "gemini-collaboration skill not found, skipping"
    }
} catch {
    Write-ErrorMsg "Failed to install skills"
    exit 1
}

# ==============================================================================
# Step 5: Configure global CLAUDE.md
# ==============================================================================
Write-Step "Step 5: Configuring global CLAUDE.md..."

$claudeMdPath = "$env:USERPROFILE\.claude\CLAUDE.md"
$ccgMarker = "# CCG Configuration"

# Read CCG config from external file to avoid encoding issues
$ccgConfigPath = Join-Path $PSScriptRoot "templates\ccg-global-prompt.md"

try {
    if (!(Test-Path $claudeMdPath)) {
        # Create new file with CCG config
        if (Test-Path $ccgConfigPath) {
            Copy-Item $ccgConfigPath $claudeMdPath
            Write-Success "Created global CLAUDE.md"
        } else {
            Write-WarningMsg "CCG global prompt template not found at $ccgConfigPath"
            Write-WarningMsg "Please manually copy the CCG configuration to $claudeMdPath"
        }
    } else {
        # Check if CCG config already exists
        $content = Get-Content $claudeMdPath -Raw -Encoding UTF8
        if ($content -match [regex]::Escape($ccgMarker)) {
            Write-WarningMsg "CCG configuration already exists in CLAUDE.md, skipping"
        } else {
            # Append CCG config
            if (Test-Path $ccgConfigPath) {
                $ccgContent = Get-Content $ccgConfigPath -Raw -Encoding UTF8
                Add-Content -Path $claudeMdPath -Value "`n$ccgContent" -Encoding UTF8
                Write-Success "Appended CCG configuration to CLAUDE.md"
            } else {
                Write-WarningMsg "CCG global prompt template not found at $ccgConfigPath"
                Write-WarningMsg "Please manually copy the CCG configuration to $claudeMdPath"
            }
        }
    }
} catch {
    Write-ErrorMsg "Failed to configure global CLAUDE.md: $_"
    exit 1
}

# ==============================================================================
# Step 6: Configure Coder
# ==============================================================================
Write-Step "Step 6: Configuring Coder..."

$configDir = "$env:USERPROFILE\.ccg-mcp"
$configPath = "$configDir\config.toml"

$skipCoderConfig = $false

try {
    # Create config directory if it doesn't exist
    if (!(Test-Path $configDir)) {
        New-Item -ItemType Directory -Path $configDir -Force | Out-Null
    }

    # Check if config already exists
    if (Test-Path $configPath) {
        Write-WarningMsg "Config file already exists at $configPath"
        $overwrite = Read-Host "Overwrite? (y/N)"
        if ($overwrite -ne "y" -and $overwrite -ne "Y") {
            Write-WarningMsg "Skipping Coder configuration"
            $skipCoderConfig = $true
        }
    }

    if (-not $skipCoderConfig) {
        # Prompt for API Token (hidden input)
        $apiToken = Read-Host "Enter your API Token" -MaskInput
        if ([string]::IsNullOrWhiteSpace($apiToken)) {
            Write-ErrorMsg "API Token is required"
            exit 1
        }

        # Prompt for Base URL (optional)
        $baseUrl = Read-Host "Enter Base URL (default: https://open.bigmodel.cn/api/anthropic)"
        if ([string]::IsNullOrWhiteSpace($baseUrl)) {
            $baseUrl = "https://open.bigmodel.cn/api/anthropic"
        }

        # Prompt for Model (optional)
        $model = Read-Host "Enter Model (default: glm-4.7)"
        if ([string]::IsNullOrWhiteSpace($model)) {
            $model = "glm-4.7"
        }

        # Escape special characters for TOML string values (backslash and double quote)
        $safeApiToken = $apiToken -replace '\\', '\\' -replace '"', '\"'
        $safeBaseUrl = $baseUrl -replace '\\', '\\' -replace '"', '\"'
        $safeModel = $model -replace '\\', '\\' -replace '"', '\"'

        # Generate config.toml
        $configContent = @"
[coder]
api_token = "$safeApiToken"
base_url = "$safeBaseUrl"
model = "$safeModel"

[coder.env]
CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC = "1"
"@

        # Use UTF8 without BOM - critical for TOML parsers
        # PowerShell 5.x's "Set-Content -Encoding UTF8" writes BOM (EF BB BF) which breaks TOML parsing
        [System.IO.File]::WriteAllText($configPath, $configContent, [System.Text.UTF8Encoding]::new($false))

        # Set file permissions - only current user can read/write
        $acl = Get-Acl $configPath
        $acl.SetAccessRuleProtection($true, $false)
        $rule = New-Object System.Security.AccessControl.FileSystemAccessRule($env:USERNAME, "FullControl", "Allow")
        $acl.SetAccessRule($rule)
        Set-Acl $configPath $acl

        Write-Success "Coder configuration saved to $configPath"
    }

} catch {
    Write-ErrorMsg "Failed to configure Coder: $_"
    exit 1
}
# ==============================================================================
# Done!
# ==============================================================================
Write-Host "`n============================================================" -ForegroundColor Green
Write-Success "CCG setup completed successfully!"
Write-Host "============================================================`n" -ForegroundColor Green

Write-Host "Next steps:" -ForegroundColor Cyan
Write-Host "  1. Restart Claude Code CLI" -ForegroundColor White
Write-Host "  2. Verify MCP server: claude mcp list" -ForegroundColor White
Write-Host "  3. Check available skills: /ccg-workflow" -ForegroundColor White
Write-Host ""
