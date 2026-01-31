<!--
   Copyright 2026 UCP Authors

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
-->

# UCP + Hedera Payment Demo

A complete demo of the Universal Commerce Protocol (UCP) with Hedera HBAR payments.

## Quick Start

```bash
# 1. Clone the SDK (required dependency)
mkdir sdk
git clone https://github.com/Universal-Commerce-Protocol/python-sdk.git sdk/python
pushd sdk/python
uv sync
popd

# 2. Clone this repo
git clone https://github.com/hedera-dev/tutorial-ucp-hedera.git
cd tutorial-ucp-hedera/rest

# 3. Run setup (installs deps, creates DB, configures Hedera)
./setup.sh

# 4. Start server (Terminal 1)
cd server
uv run server.py --products_db_path=/tmp/ucp_test/products.db \
                 --transactions_db_path=/tmp/ucp_test/transactions.db \
                 --port=8182

# 5. Run client (Terminal 2)
cd client/flower_shop
uv run simple_happy_path_client.py --server_url=http://localhost:8182
```

## Prerequisites

1. **Python 3.10+**
2. **uv package manager**: `curl -LsSf https://astral.sh/uv/install.sh | sh`
3. **Hedera testnet account**: Get free credentials at [portal.hedera.com](https://portal.hedera.com/)
   - Create an **ECDSA account** (NOT ED25519)
   - You'll receive an Account ID (0.0.XXXXX) and Private Key (0x...)

## Project Structure

```
sdk/
└── python/               # UCP Python SDK (clone separately)

tutorial-ucp-hedera/
└── rest/
    ├── setup.sh          # One-command setup script
    ├── README.md         # This file
    ├── server/           # UCP Merchant Server (FastAPI)
    │   ├── server.py     # Main entry point
    │   └── services/     # Business logic
    ├── client/
    │   └── flower_shop/  # Sample client
    └── test_data/        # Sample flower shop data
```

## What the Demo Does

The client (`simple_happy_path_client.py`) demonstrates a complete checkout flow:

1. **Discovery** - Query merchant capabilities via `/.well-known/ucp`
2. **Create Checkout** - Start a shopping session
3. **Add Items** - Add roses and ceramic pots to cart
4. **Apply Discount** - Use code "10OFF" for 10% off
5. **Select Fulfillment** - Choose shipping destination and option
6. **Hedera Payment** - Sign and submit HBAR transfer transaction
7. **Complete Order** - Finalize the purchase

## Expected Output

```
Using Hedera payment with account: 0.0.12345
Hedera merchant account: 0.0.67890
...
Total: $59.85 USD = 1197.00 HBAR
Transfer: 1197.00 HBAR from 0.0.12345 to 0.0.67890
Payment Successful!
Order ID: order_abc123
Hedera Transaction ID: 0.0.12345@1234567890.123456789
Hedera Explorer URL: https://hashscan.io/testnet/transaction/...
```

## Configuration

### Environment Variables

Both server and client use `.env` files (created by `setup.sh`):

| Variable | Description | Example |
|----------|-------------|---------|
| `HEDERA_NETWORK` | Network to use | `testnet` |
| `HEDERA_MERCHANT_ACCOUNT_ID` | Merchant's Hedera account | `0.0.12345` |
| `HEDERA_MERCHANT_PRIVATE_KEY` | Merchant's private key | `0x...` |
| `HEDERA_CUSTOMER_ACCOUNT_ID` | Customer's Hedera account | `0.0.12345` |
| `HEDERA_CUSTOMER_PRIVATE_KEY` | Customer's private key | `0x...` |

For testing, you can use the same account for both merchant and customer.

## Troubleshooting

### "Distribution not found" for ucp-sdk

Make sure you cloned and set up the SDK first:
```bash
mkdir sdk
git clone https://github.com/Universal-Commerce-Protocol/python-sdk.git sdk/python
cd sdk/python && uv sync && cd -
```

### "Hedera credentials required"

Set environment variables or create `.env` file:
```bash
export HEDERA_CUSTOMER_ACCOUNT_ID=0.0.12345
export HEDERA_CUSTOMER_PRIVATE_KEY=0xabcd...
```

### "Merchant does not support Hedera payments"

Ensure the server has `HEDERA_MERCHANT_ACCOUNT_ID` set in its `.env` file.

### "INSUFFICIENT_PAYER_BALANCE"

Your testnet account needs more HBAR. Visit [portal.hedera.com](https://portal.hedera.com/) to fund it.

### "Invalid key format"

Only ECDSA accounts are supported. Keys should start with `0x`.
ED25519 keys (starting with `302e`) are NOT supported.

## Resources

- [UCP Specification](https://ucp.dev/specs/shopping)
- [Hedera Documentation](https://docs.hedera.com/)
- [Hiero SDK Python](https://github.com/hiero-ledger/hiero-sdk-python)
- [HashScan Explorer](https://hashscan.io/)

## License

Apache 2.0 - See LICENSE file for details.
