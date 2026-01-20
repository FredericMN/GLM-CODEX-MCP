#!/bin/bash
# CCG OpenCode Setup Script for macOS (macOS-only)
# This script configures Oh-My-OpenCode with CCG multi-agent collaboration
#
# Supported platforms:
#   - macOS (this script)
#   - Windows: use setup-opencode.ps1 or setup-opencode.bat
#   - Linux: not supported (please install manually following README instructions)
set -euo pipefail

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Helper functions
write_step() {
    echo -e "\n${CYAN}[*] $1${NC}"
}

write_success() {
    echo -e "${GREEN}[OK] $1${NC}"
}

write_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

write_warning() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

# Function to escape special characters for sed replacement (using | as delimiter)
escape_sed_replacement() {
    # Escape: & \ | (since we use | as sed delimiter)
    # Note: backslash must be escaped first to avoid double-escaping
    local input="$1"
    input="${input//\\/\\\\}"  # Escape backslashes first
    input="${input//&/\\&}"    # Escape &
    input="${input//|/\\|}"    # Escape | (our delimiter)
    printf '%s' "$input"
}

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}   CCG OpenCode Setup - Multi-Agent Collaboration${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# ==============================================================================
# Step 0: Check OS compatibility
# ==============================================================================
write_step "Step 0: Checking OS compatibility..."

if [[ "$OSTYPE" != "darwin"* ]]; then
    write_error "This script only supports macOS."
    echo "  Detected OS: $OSTYPE"
    echo ""
    echo "For other platforms:"
    echo "  - Windows: Use setup-opencode.ps1 or setup-opencode.bat"
    echo "  - Linux: Please install manually following the README instructions"
    exit 1
fi

write_success "macOS detected"

# ==============================================================================
# Step 1: Check template files exist
# ==============================================================================
write_step "Step 1: Checking template files..."

TEMPLATE_JSON="$SCRIPT_DIR/templates/opencode/opencode.json"
TEMPLATE_OH_MY="$SCRIPT_DIR/templates/opencode/oh-my-opencode.json"
TEMPLATE_AGENTS="$SCRIPT_DIR/templates/opencode/AGENTS.md"

MISSING_TEMPLATES=false

if [ ! -f "$TEMPLATE_JSON" ]; then
    write_error "Template not found: $TEMPLATE_JSON"
    MISSING_TEMPLATES=true
fi

if [ ! -f "$TEMPLATE_OH_MY" ]; then
    write_error "Template not found: $TEMPLATE_OH_MY"
    MISSING_TEMPLATES=true
fi

if [ ! -f "$TEMPLATE_AGENTS" ]; then
    write_error "Template not found: $TEMPLATE_AGENTS"
    MISSING_TEMPLATES=true
fi

if [ "$MISSING_TEMPLATES" = true ]; then
    echo ""
    write_error "Please run this script from the CCG repository root directory."
    echo "  Expected location: cd /path/to/Coder-Codex-Gemini && ./setup-opencode.sh"
    exit 1
fi

write_success "All template files found"

# ==============================================================================
# Step 2: Check dependencies
# ==============================================================================
write_step "Step 2: Checking dependencies..."

# Check Homebrew first (required for opencode installation)
if ! command -v brew &> /dev/null; then
    write_error "Homebrew is not installed."
    echo "  Please install Homebrew first: https://brew.sh"
    echo "  Run: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 1
fi
write_success "Homebrew is installed"

# Check bun (required for oh-my-opencode)
if command -v bun &> /dev/null; then
    write_success "bun is installed"
else
    write_warning "bun is not installed, installing automatically..."
    echo "  This will run: curl -fsSL https://bun.sh/install | bash"
    read -p "  Continue? (Y/n): " CONFIRM_BUN
    if [ "$CONFIRM_BUN" = "n" ] || [ "$CONFIRM_BUN" = "N" ]; then
        write_error "bun is required. Please install manually: https://bun.sh"
        exit 1
    fi
    if curl -fsSL https://bun.sh/install | bash; then
        export PATH="$HOME/.bun/bin:$PATH"
        write_success "bun installed successfully"
    else
        write_error "Failed to install bun automatically"
        echo "Please install bun manually: https://bun.sh"
        exit 1
    fi
fi

# Check opencode CLI
if command -v opencode &> /dev/null; then
    write_success "opencode CLI is installed"
else
    write_warning "opencode CLI is not installed"
    echo "Installing opencode via Homebrew..."
    if brew install anomalyco/tap/opencode; then
        write_success "opencode installed successfully"
    else
        write_error "Failed to install opencode"
        echo "Please install opencode manually: https://opencode.ai/docs"
        exit 1
    fi
fi

# ==============================================================================
# Step 3: Install Oh-My-OpenCode
# ==============================================================================
write_step "Step 3: Installing Oh-My-OpenCode..."

# Check if oh-my-opencode is already configured
OH_MY_JSON_CHECK="$HOME/.config/opencode/oh-my-opencode.json"
SKIP_OH_MY_INSTALL=false

if [ -f "$OH_MY_JSON_CHECK" ]; then
    write_warning "Oh-My-OpenCode appears to be already installed"
    echo "  Found: $OH_MY_JSON_CHECK"
    read -p "Re-run oh-my-opencode install? This may modify your existing config (y/N): " REINSTALL
    if [ "$REINSTALL" != "y" ] && [ "$REINSTALL" != "Y" ]; then
        write_warning "Skipping Oh-My-OpenCode installation"
        SKIP_OH_MY_INSTALL=true
    fi
fi

if [ "$SKIP_OH_MY_INSTALL" = false ]; then
    echo "Please select your subscription status:"
    echo "  1) Claude Max 20 + ChatGPT + Gemini (Recommended)"
    echo "  2) Claude Pro + ChatGPT + Gemini"
    echo "  3) Custom (interactive TUI)"
    read -p "Enter choice [1-3]: " SUBSCRIPTION_CHOICE

    case $SUBSCRIPTION_CHOICE in
        1)
            if ! bunx oh-my-opencode install --no-tui --claude=max20 --chatgpt=yes --gemini=yes; then
                write_error "Failed to install Oh-My-OpenCode"
                echo "Please try running manually: bunx oh-my-opencode install"
                exit 1
            fi
            ;;
        2)
            if ! bunx oh-my-opencode install --no-tui --claude=yes --chatgpt=yes --gemini=yes; then
                write_error "Failed to install Oh-My-OpenCode"
                echo "Please try running manually: bunx oh-my-opencode install"
                exit 1
            fi
            ;;
        3)
            if ! bunx oh-my-opencode install; then
                write_error "Failed to install Oh-My-OpenCode"
                echo "Please try running manually: bunx oh-my-opencode install"
                exit 1
            fi
            ;;
        *)
            write_warning "Invalid choice, using default (Claude Max 20)"
            if ! bunx oh-my-opencode install --no-tui --claude=max20 --chatgpt=yes --gemini=yes; then
                write_error "Failed to install Oh-My-OpenCode"
                echo "Please try running manually: bunx oh-my-opencode install"
                exit 1
            fi
            ;;
    esac

    write_success "Oh-My-OpenCode installed"
else
    write_success "Oh-My-OpenCode installation skipped (using existing config)"
fi

# ==============================================================================
# Step 4: Configure opencode.json
# ==============================================================================
write_step "Step 4: Configuring opencode.json..."

CONFIG_DIR="$HOME/.config/opencode"
OPENCODE_JSON="$CONFIG_DIR/opencode.json"

mkdir -p "$CONFIG_DIR"

# Function to configure opencode.json
configure_opencode_json() {
    echo ""
    echo "Configure Anthropic API (for Claude models):"
    echo "  (You can also use 'opencode auth login' later for OAuth authentication)"
    read -p "  Base URL (default: https://api.anthropic.com/v1): " ANTHROPIC_BASE_URL
    ANTHROPIC_BASE_URL=${ANTHROPIC_BASE_URL:-"https://api.anthropic.com/v1"}

    read -s -p "  API Key (leave empty to use OAuth): " ANTHROPIC_API_KEY
    echo ""

    # Copy template
    cp "$TEMPLATE_JSON" "$OPENCODE_JSON"

    if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
        # Escape special characters for sed
        ESCAPED_BASE_URL=$(escape_sed_replacement "$ANTHROPIC_BASE_URL")
        ESCAPED_API_KEY=$(escape_sed_replacement "$ANTHROPIC_API_KEY")

        # Replace placeholders
        sed -i.tmp "s|__ANTHROPIC_BASE_URL__|$ESCAPED_BASE_URL|g" "$OPENCODE_JSON"
        sed -i.tmp "s|__ANTHROPIC_API_KEY__|$ESCAPED_API_KEY|g" "$OPENCODE_JSON"
        rm -f "$OPENCODE_JSON.tmp"
        write_success "Configured Anthropic API"
        write_warning "Note: API Key is stored in plaintext in $OPENCODE_JSON"
    else
        # Remove the placeholder options block for OAuth flow
        # Replace with empty/default values
        sed -i.tmp "s|__ANTHROPIC_BASE_URL__|https://api.anthropic.com/v1|g" "$OPENCODE_JSON"
        sed -i.tmp "s|__ANTHROPIC_API_KEY__||g" "$OPENCODE_JSON"
        rm -f "$OPENCODE_JSON.tmp"
        write_warning "Anthropic API Key not configured."
        write_warning "Please use 'opencode auth login' for OAuth authentication."
    fi

    # Set file permissions - only current user can read/write
    chmod 600 "$OPENCODE_JSON"
}

if [ -f "$OPENCODE_JSON" ]; then
    write_warning "opencode.json already exists"
    read -p "Overwrite with CCG template? (y/N): " OVERWRITE
    if [ "$OVERWRITE" != "y" ] && [ "$OVERWRITE" != "Y" ]; then
        write_warning "Skipping opencode.json configuration"
        write_warning "Please manually merge CCG settings from: $TEMPLATE_JSON"
    else
        # Backup existing config
        cp "$OPENCODE_JSON" "$OPENCODE_JSON.backup.$(date +%Y%m%d%H%M%S)"
        write_success "Backed up existing config"
        configure_opencode_json
        write_success "opencode.json configured (permissions restricted to current user)"
    fi
else
    configure_opencode_json
    write_success "opencode.json created (permissions restricted to current user)"
fi

# ==============================================================================
# Step 5: Configure oh-my-opencode.json
# ==============================================================================
write_step "Step 5: Configuring oh-my-opencode.json..."

OH_MY_JSON="$CONFIG_DIR/oh-my-opencode.json"

if [ -f "$OH_MY_JSON" ]; then
    write_warning "oh-my-opencode.json already exists"
    read -p "Overwrite with CCG template? (y/N): " OVERWRITE
    if [ "$OVERWRITE" != "y" ] && [ "$OVERWRITE" != "Y" ]; then
        write_warning "Skipping oh-my-opencode.json configuration"
        write_warning "Please manually merge CCG settings from: $TEMPLATE_OH_MY"
    else
        cp "$OH_MY_JSON" "$OH_MY_JSON.backup.$(date +%Y%m%d%H%M%S)"
        cp "$TEMPLATE_OH_MY" "$OH_MY_JSON"
        write_success "oh-my-opencode.json configured"
    fi
else
    cp "$TEMPLATE_OH_MY" "$OH_MY_JSON"
    write_success "oh-my-opencode.json created"
fi

# ==============================================================================
# Step 6: Configure AGENTS.md
# ==============================================================================
write_step "Step 6: Configuring AGENTS.md..."

AGENTS_MD="$CONFIG_DIR/AGENTS.md"

if [ -f "$AGENTS_MD" ]; then
    write_warning "AGENTS.md already exists"
    read -p "Overwrite with CCG template? (y/N): " OVERWRITE
    if [ "$OVERWRITE" != "y" ] && [ "$OVERWRITE" != "Y" ]; then
        write_warning "Skipping AGENTS.md configuration"
    else
        cp "$AGENTS_MD" "$AGENTS_MD.backup.$(date +%Y%m%d%H%M%S)"
        cp "$TEMPLATE_AGENTS" "$AGENTS_MD"
        write_success "AGENTS.md configured"
    fi
else
    cp "$TEMPLATE_AGENTS" "$AGENTS_MD"
    write_success "AGENTS.md created"
fi

# ==============================================================================
# Step 7: Authentication reminder
# ==============================================================================
write_step "Step 7: Authentication setup..."

echo ""
echo "Please complete authentication for each provider:"
echo ""
echo "  ${CYAN}1. Anthropic (Claude):${NC}"
echo "     opencode auth login"
echo "     → Select: Anthropic → Claude Pro/Max"
echo ""
echo "  ${CYAN}2. OpenAI (ChatGPT/Codex):${NC}"
echo "     opencode auth login"
echo "     → Select: OpenAI → ChatGPT Plus/Pro (Codex Subscription)"
echo ""
echo "  ${CYAN}3. Google (Gemini):${NC}"
echo "     opencode auth login"
echo "     → Select: Google → OAuth with Google (Antigravity)"
echo ""

# ==============================================================================
# Done!
# ==============================================================================
echo ""
echo -e "${GREEN}============================================================${NC}"
write_success "CCG OpenCode setup completed!"
echo -e "${GREEN}============================================================${NC}"
echo ""

echo "Configuration files:"
echo "  - $OPENCODE_JSON"
echo "  - $OH_MY_JSON"
echo "  - $AGENTS_MD"
echo ""

echo "Next steps:"
echo "  1. Complete authentication: opencode auth login"
echo "  2. Start OpenCode: opencode"
echo "  3. Use Tab to switch between build/plan mode"
echo ""

echo -e "${YELLOW}Note: If using Antigravity plugin for Gemini, ensure google_auth is set to false${NC}"
echo ""
