#!/bin/bash
#   Copyright 2026 UCP Authors
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

# UCP + Hedera Demo - One-Command Setup
# Sets up everything: SDK check, dependencies, database, and Hedera credentials

set -e

# Colors
GREEN='\033[92m'
YELLOW='\033[93m'
RED='\033[91m'
BLUE='\033[94m'
BOLD='\033[1m'
RESET='\033[0m'

# Paths
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVER_DIR="$SCRIPT_DIR/server"
CLIENT_DIR="$SCRIPT_DIR/client/flower_shop"
TEST_DATA_DIR="$SCRIPT_DIR/test_data/flower_shop"
DB_DIR="/tmp/ucp_test"
SDK_DIR="$SCRIPT_DIR/../sdk/python"

print_step() {
    echo -e "\n${BLUE}${BOLD}==>${RESET} $1"
}

print_success() {
    echo -e "${GREEN}✓${RESET} $1"
}

print_warning() {
    echo -e "${YELLOW}!${RESET} $1"
}

print_error() {
    echo -e "${RED}✗${RESET} $1"
}

create_env_file() {
    local path="$1"
    local account_id="$2"
    local private_key="$3"

    cat > "$path" << EOF
# Hedera Configuration (ECDSA Account Only)
HEDERA_NETWORK=testnet
HEDERA_MERCHANT_ACCOUNT_ID=$account_id
HEDERA_MERCHANT_PRIVATE_KEY=$private_key
HEDERA_CUSTOMER_ACCOUNT_ID=$account_id
HEDERA_CUSTOMER_PRIVATE_KEY=$private_key
EOF
}

echo -e "\n${BOLD}UCP + Hedera Demo - Setup${RESET}"
echo "========================================"

# Step 0: Check for SDK
print_step "Checking for UCP Python SDK..."
if [ ! -d "$SDK_DIR" ]; then
    print_error "UCP Python SDK not found at: $SDK_DIR"
    echo
    echo "Please clone the SDK first:"
    echo "  mkdir -p sdk"
    echo "  git clone https://github.com/Universal-Commerce-Protocol/python-sdk.git sdk/python"
    echo "  cd sdk/python && uv sync && cd -"
    echo
    exit 1
fi
print_success "SDK found at $SDK_DIR"

# Step 1: Check uv
print_step "Checking for uv package manager..."
if ! command -v uv &> /dev/null; then
    print_error "uv is required but not installed"
    echo "Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi
print_success "uv is installed"

# Step 2: Install server dependencies
print_step "Installing server dependencies..."
(cd "$SERVER_DIR" && uv sync)
print_success "Server dependencies installed"

# Step 3: Install client dependencies
print_step "Installing client dependencies..."
(cd "$CLIENT_DIR" && uv sync)
print_success "Client dependencies installed"

# Step 4: Initialize database
print_step "Initializing sample database..."
mkdir -p "$DB_DIR"
if (cd "$SERVER_DIR" && uv run import_csv.py \
    --products_db_path="$DB_DIR/products.db" \
    --transactions_db_path="$DB_DIR/transactions.db" \
    --data_dir="$TEST_DATA_DIR"); then
    print_success "Database created at $DB_DIR"
else
    print_warning "Database initialization failed - you may need to run it manually"
fi

# Step 5: Configure Hedera credentials
print_step "Configuring Hedera credentials..."

SERVER_ENV="$SERVER_DIR/.env"
CLIENT_ENV="$CLIENT_DIR/.env"

if [ -f "$SERVER_ENV" ] && [ -f "$CLIENT_ENV" ]; then
    print_warning ".env files already exist"
    read -p "Overwrite with new credentials? (y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keeping existing .env files"
        ACCOUNT_ID=""
        PRIVATE_KEY=""
    else
        echo -e "\n${BOLD}Hedera Testnet Credentials${RESET}"
        echo "Get free credentials at: https://portal.hedera.com/"
        echo "(Create an ECDSA account - NOT ED25519)"
        echo
        read -p "Hedera Account ID (e.g., 0.0.12345): " ACCOUNT_ID
        read -p "Hedera Private Key (0x...): " PRIVATE_KEY
    fi
else
    echo -e "\n${BOLD}Hedera Testnet Credentials${RESET}"
    echo "Get free credentials at: https://portal.hedera.com/"
    echo "(Create an ECDSA account - NOT ED25519)"
    echo
    read -p "Hedera Account ID (e.g., 0.0.12345): " ACCOUNT_ID
    read -p "Hedera Private Key (0x...): " PRIVATE_KEY
fi

if [ -n "$ACCOUNT_ID" ] && [ -n "$PRIVATE_KEY" ]; then
    create_env_file "$SERVER_ENV" "$ACCOUNT_ID" "$PRIVATE_KEY"
    create_env_file "$CLIENT_ENV" "$ACCOUNT_ID" "$PRIVATE_KEY"
    print_success "Created .env files in server/ and client/flower_shop/"
elif [ ! -f "$SERVER_ENV" ]; then
    create_env_file "$SERVER_ENV" "0.0.YOUR_ACCOUNT_ID" "0xYOUR_ECDSA_KEY"
    create_env_file "$CLIENT_ENV" "0.0.YOUR_ACCOUNT_ID" "0xYOUR_ECDSA_KEY"
    print_warning "Created placeholder .env files - edit with your credentials"
fi

# Done!
echo -e "\n${GREEN}${BOLD}Setup Complete!${RESET}"
echo "========================================"
echo
echo -e "${BOLD}Next Steps:${RESET}"
echo
echo "1. Start the server:"
echo "   cd server"
echo "   uv run server.py --products_db_path=$DB_DIR/products.db \\"
echo "                    --transactions_db_path=$DB_DIR/transactions.db \\"
echo "                    --port=8182"
echo
echo "2. Run the client (in another terminal):"
echo "   cd client/flower_shop"
echo "   uv run simple_happy_path_client.py --server_url=http://localhost:8182"
echo
echo -e "${BOLD}Expected Output:${RESET}"
echo '- "Using Hedera payment with account: 0.0.XXXXX"'
echo '- "Transfer: X.XX HBAR from 0.0.XXXXX to 0.0.YYYYY"'
echo '- "Order ID: ..."'
echo
echo -e "${BOLD}Resources:${RESET}"
echo "- Hedera Portal: https://portal.hedera.com/"
echo "- Hedera Docs: https://docs.hedera.com/"
