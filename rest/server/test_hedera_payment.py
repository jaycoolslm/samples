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

# ruff: noqa: T201
"""Test script for Hedera payment handler.

This script verifies ECDSA account configuration by creating and submitting
a test transaction. Requires ECDSA accounts with hex-encoded private keys.
"""

from __future__ import annotations

import base64
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
  from hiero_sdk_python import AccountId, PrivateKey

AMOUNT_HBAR = 1 * (10**8)  # 1 HBAR in tinybars

EXPLORER_URLS = {
  "mainnet": "https://hashscan.io/mainnet",
  "testnet": "https://hashscan.io/testnet",
  "previewnet": "https://hashscan.io/previewnet",
}


def load_environment() -> None:
  """Load environment variables from .env file if available."""
  try:
    from dotenv import load_dotenv

    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
      load_dotenv(env_path)
      print(f"Loaded environment from {env_path}")
    else:
      print(f"No .env file found at {env_path}")
  except ImportError:
    print("python-dotenv not installed, using system environment variables")


def get_env_or_prompt(
  key: str,
  prompt_message: str,
  fallback: str | None = None,
  required: bool = True,
) -> str:
  """Get an environment variable or prompt the user for input."""
  value = os.getenv(key, "")
  if value:
    return value

  print(f"Warning: {key} not set")
  print()
  user_input = input(prompt_message).strip()

  if user_input:
    return user_input
  if fallback:
    print(f"Using fallback: {fallback}")
    return fallback
  if required:
    print(f"Error: {key} is required")
    sys.exit(1)

  return ""


def parse_accounts(
  merchant_str: str,
  customer_str: str,
  customer_key_str: str,
) -> tuple[AccountId, AccountId, PrivateKey]:
  """Parse account IDs and private key from string configuration."""
  from hiero_sdk_python import AccountId, PrivateKey

  try:
    merchant_id = AccountId.from_string(merchant_str)
    customer_id = AccountId.from_string(customer_str)
    customer_key = PrivateKey.from_string_ecdsa(customer_key_str)
    return merchant_id, customer_id, customer_key
  except Exception as e:
    print(f"Error parsing configuration: {e}")
    print("Ensure you're using an ECDSA private key (hex format: 0x...)")
    sys.exit(1)


def create_client(
  network_name: str,
  operator_id: AccountId,
  operator_key: PrivateKey,
):
  """Create and configure the Hedera client."""
  from hiero_sdk_python import Client, Network

  try:
    network = Network(network_name)
    client = Client(network)
    client.set_operator(operator_id, operator_key)
    print(f"Connected to Hedera {network_name}")
    print(f"  Operator: {client.operator_account_id}")
    return client
  except Exception as e:
    print(f"Error connecting to Hedera: {e}")
    sys.exit(1)


def create_transaction(
  client,
  customer_id: AccountId,
  customer_key: PrivateKey,
  merchant_id: AccountId,
):
  """Create and sign a transfer transaction."""
  from hiero_sdk_python import TransferTransaction

  try:
    transaction = (
      TransferTransaction()
      .add_hbar_transfer(customer_id, -AMOUNT_HBAR)
      .add_hbar_transfer(merchant_id, AMOUNT_HBAR)
      .set_transaction_memo("UCP Test Payment")
      .freeze_with(client)
      .sign(customer_key)
    )
    print("Transaction created and signed")
    return transaction
  except Exception as e:
    print(f"Error creating transaction: {e}")
    import traceback

    traceback.print_exc()
    sys.exit(1)


def encode_transaction(transaction) -> str:
  """Encode transaction to base64 for UCP."""
  try:
    tx_bytes = transaction.to_bytes()
    tx_base64 = base64.b64encode(tx_bytes).decode("utf-8")

    print()
    print("Signed transaction (base64-encoded):")
    print("-" * 50)
    preview = tx_base64[:80] + "..." if len(tx_base64) > 80 else tx_base64
    print(preview)
    print("-" * 50)
    print(f"Length: {len(tx_base64)} characters")
    return tx_base64
  except Exception as e:
    print(f"Error encoding transaction: {e}")
    sys.exit(1)


def submit_transaction(transaction, client, network_name: str) -> None:
  """Submit transaction to the Hedera network."""
  from hiero_sdk_python import ResponseCode

  print()
  print("Submitting to Hedera network...")
  try:
    receipt = transaction.execute(client)
    print("Transaction submitted")
    print(f"  Transaction ID: {receipt.transaction_id}")
    print()
    print(f"Status: {receipt.status}")

    if receipt.status == ResponseCode.SUCCESS:
      print()
      print("Payment successful!")
      base_url = EXPLORER_URLS.get(network_name, EXPLORER_URLS["testnet"])
      tx_url = f"{base_url}/transaction/{receipt.transaction_id}"
      print(f"View on HashScan: {tx_url}")
    else:
      print(f"Transaction failed with status: {receipt.status.name}")
  except Exception as e:
    print(f"Error submitting transaction: {e}")
    sys.exit(1)


def print_next_steps() -> None:
  """Print guidance for next steps."""
  print()
  print("=" * 50)
  print("Next steps:")
  print()
  print("1. Use this base64-encoded transaction in your UCP payment request:")
  print("   POST /checkouts/{id}/payments")
  print('   {"instrument": {"handler_id": "hedera_payment",')
  print('                   "signed_transaction": "..."}}')
  print()
  print("2. Run the full checkout flow with the Python client:")
  print("   cd ../client/flower_shop && uv run simple_happy_path_client.py")
  print()
  print("3. Read the full documentation:")
  print("   See ../README.md")


def main() -> None:
  """Run the Hedera payment test script."""
  try:
    import hiero_sdk_python  # noqa: F401
  except ImportError:
    print("Error: hiero-sdk-python not installed")
    print("Run: uv sync")
    sys.exit(1)

  load_environment()

  print()
  print("Hedera Payment Handler Test Script")
  print("=" * 50)
  print()

  network_name = os.getenv("HEDERA_NETWORK", "testnet")
  merchant_account_str = os.getenv("HEDERA_MERCHANT_ACCOUNT_ID", "")

  if not merchant_account_str:
    print("Error: HEDERA_MERCHANT_ACCOUNT_ID not set")
    print("Please set it in your .env file or environment")
    sys.exit(1)

  customer_account_str = get_env_or_prompt(
    "HEDERA_CUSTOMER_ACCOUNT_ID",
    "Enter customer account ID (or press Enter to use merchant account): ",
    fallback=merchant_account_str,
    required=False,
  )

  customer_key_str = get_env_or_prompt(
    "HEDERA_CUSTOMER_PRIVATE_KEY",
    "Enter your ECDSA private key (hex format starting with 0x): ",
    required=True,
  )

  merchant_id, customer_id, customer_key = parse_accounts(
    merchant_account_str, customer_account_str, customer_key_str
  )

  print(f"Network: {network_name}")
  print(f"Merchant Account: {merchant_id}")
  print(f"Customer Account: {customer_id}")
  print()

  client = create_client(network_name, customer_id, customer_key)
  print()

  transaction = create_transaction(
    client, customer_id, customer_key, merchant_id
  )
  encode_transaction(transaction)

  print()
  user_response = input("Submit transaction to Hedera network? (y/N): ")
  should_submit = user_response.strip().lower() == "y"

  if should_submit:
    submit_transaction(transaction, client, network_name)
  else:
    print()
    print("Transaction not submitted")

  print_next_steps()


if __name__ == "__main__":
  main()
