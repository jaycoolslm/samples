#!/usr/bin/env python3
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

"""UCP Python Samples - One-Command Setup.

This script sets up everything you need to run the UCP demo with Hedera payments:
1. Installs dependencies for server and client
2. Initializes the sample database
3. Creates .env files with your Hedera credentials

Usage:
    python setup.py

After setup, you'll have:
    - Server ready at: python/server/
    - Client ready at: python/client/flower_shop/
"""

import os
import subprocess
import sys
from pathlib import Path

# ANSI colors for pretty output
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_step(msg: str) -> None:
  """Print a step message."""
  print(f"\n{BLUE}{BOLD}==>{RESET} {msg}")


def print_success(msg: str) -> None:
  """Print a success message."""
  print(f"{GREEN}✓{RESET} {msg}")


def print_warning(msg: str) -> None:
  """Print a warning message."""
  print(f"{YELLOW}!{RESET} {msg}")


def print_error(msg: str) -> None:
  """Print an error message."""
  print(f"{RED}✗{RESET} {msg}")


def run_command(cmd: list[str], cwd: Path | None = None) -> bool:
  """Run a command and return True if successful."""
  try:
    subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True)
    return True
  except subprocess.CalledProcessError as e:
    print_error(f"Command failed: {' '.join(cmd)}")
    if e.stderr:
      print(f"  {e.stderr[:200]}")
    return False
  except FileNotFoundError:
    print_error(f"Command not found: {cmd[0]}")
    return False


def check_uv() -> bool:
  """Check if uv is installed."""
  try:
    subprocess.run(["uv", "--version"], capture_output=True, check=True)
    return True
  except (subprocess.CalledProcessError, FileNotFoundError):
    return False


def get_hedera_credentials() -> tuple[str, str]:
  """Prompt for Hedera credentials."""
  print(f"\n{BOLD}Hedera Testnet Credentials{RESET}")
  print("Get free credentials at: https://portal.hedera.com/")
  print("(Create an ECDSA account - NOT ED25519)")
  print()

  account_id = input("Hedera Account ID (e.g., 0.0.12345): ").strip()
  private_key = input("Hedera Private Key (0x...): ").strip()

  return account_id, private_key


def create_env_file(path: Path, account_id: str, private_key: str) -> None:
  """Create or update .env file."""
  env_content = f"""# Hedera Configuration (ECDSA Account Only)
HEDERA_NETWORK=testnet
HEDERA_MERCHANT_ACCOUNT_ID={account_id}
HEDERA_MERCHANT_PRIVATE_KEY={private_key}
HEDERA_CUSTOMER_ACCOUNT_ID={account_id}
HEDERA_CUSTOMER_PRIVATE_KEY={private_key}
"""
  path.write_text(env_content)


def main() -> int:
  """Run the setup."""
  print(f"\n{BOLD}UCP Python Samples - Setup{RESET}")
  print("=" * 40)

  # Determine paths
  script_dir = Path(__file__).parent.resolve()
  server_dir = script_dir / "server"
  client_dir = script_dir / "client" / "flower_shop"
  test_data_dir = script_dir / "test_data" / "flower_shop"
  db_dir = Path("/tmp/ucp_test")

  # Verify we're in the right place
  if not server_dir.exists():
    print_error(f"Server directory not found: {server_dir}")
    return 1

  # Step 1: Check uv
  print_step("Checking for uv package manager...")
  if not check_uv():
    print_error("uv is required but not installed")
    print("Install: curl -LsSf https://astral.sh/uv/install.sh | sh")
    return 1
  print_success("uv is installed")

  # Step 2: Install server dependencies
  print_step("Installing server dependencies...")
  if not run_command(["uv", "sync"], cwd=server_dir):
    return 1
  print_success("Server dependencies installed")

  # Step 3: Install client dependencies
  print_step("Installing client dependencies...")
  if not run_command(["uv", "sync"], cwd=client_dir):
    return 1
  print_success("Client dependencies installed")

  # Step 4: Initialize database
  print_step("Initializing sample database...")
  db_dir.mkdir(parents=True, exist_ok=True)

  import_cmd = [
    "uv", "run", "import_csv.py",
    f"--products_db_path={db_dir}/products.db",
    f"--transactions_db_path={db_dir}/transactions.db",
    f"--data_dir={test_data_dir}",
  ]
  if not run_command(import_cmd, cwd=server_dir):
    print_warning("Database initialization failed - you may need to run it manually")
  else:
    print_success(f"Database created at {db_dir}")

  # Step 5: Get Hedera credentials
  print_step("Configuring Hedera credentials...")

  server_env = server_dir / ".env"
  client_env = client_dir / ".env"

  # Check if .env files already exist
  if server_env.exists() and client_env.exists():
    print_warning(".env files already exist")
    response = input("Overwrite with new credentials? (y/N): ").strip().lower()
    if response != "y":
      print("Keeping existing .env files")
      account_id = private_key = None
    else:
      account_id, private_key = get_hedera_credentials()
  else:
    account_id, private_key = get_hedera_credentials()

  if account_id and private_key:
    create_env_file(server_env, account_id, private_key)
    create_env_file(client_env, account_id, private_key)
    print_success("Created .env files in server/ and client/flower_shop/")
  elif not server_env.exists():
    # Create placeholder .env files
    placeholder_id = "0.0.YOUR_ACCOUNT_ID"
    placeholder_key = "0xYOUR_ECDSA_KEY"
    create_env_file(server_env, placeholder_id, placeholder_key)
    create_env_file(client_env, placeholder_id, placeholder_key)
    print_warning("Created placeholder .env files - edit with your credentials")

  # Done!
  print(f"\n{GREEN}{BOLD}Setup Complete!{RESET}")
  print("=" * 40)
  print(f"""
{BOLD}Next Steps:{RESET}

1. Start the server:
   cd {server_dir}
   uv run server.py --products_db_path={db_dir}/products.db \\
                    --transactions_db_path={db_dir}/transactions.db \\
                    --port=8182

2. Run the client (in another terminal):
   cd {client_dir}
   uv run simple_happy_path_client.py --server_url=http://localhost:8182

{BOLD}Expected Output:{RESET}
- "Using Hedera payment with account: 0.0.XXXXX"
- "Transfer: X.XX HBAR from 0.0.XXXXX to 0.0.YYYYY"
- "Order ID: ..."

{BOLD}Resources:{RESET}
- Hedera Portal: https://portal.hedera.com/
- Hedera Docs: https://docs.hedera.com/
""")

  return 0


if __name__ == "__main__":
  sys.exit(main())
