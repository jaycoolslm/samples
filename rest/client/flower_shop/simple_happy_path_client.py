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

"""Simple Happy Path Client Script for UCP SDK with Hedera Payment.

This script demonstrates a basic "happy path" user journey with Hedera payments:
0. Discovery: Querying the merchant to see what they support.
1. Creating a new checkout session (cart).
2. Adding items to the checkout session.
3. Applying a discount code.
4. Triggering fulfillment option generation.
5. Selecting a fulfillment destination.
6. Selecting a fulfillment option.
7. Completing the checkout by processing a Hedera HBAR payment.

Usage:
  export HEDERA_CUSTOMER_ACCOUNT_ID=0.0.XXXXX
  export HEDERA_CUSTOMER_PRIVATE_KEY=0xabcd...
  uv run simple_happy_path_client.py --server_url=http://localhost:8182
"""

import argparse
import base64
import json
import logging
import os
from pathlib import Path
import uuid

import httpx
from dotenv import load_dotenv
from hiero_sdk_python import (
  AccountId,
  Client,
  Network,
  PrivateKey,
  TransferTransaction,
)
from ucp_sdk.models.schemas.shopping import checkout_create_req
from ucp_sdk.models.schemas.shopping import checkout_update_req
from ucp_sdk.models.schemas.shopping import payment_create_req
from ucp_sdk.models.schemas.shopping.types import buyer
from ucp_sdk.models.schemas.shopping.types import item_create_req
from ucp_sdk.models.schemas.shopping.types import item_update_req
from ucp_sdk.models.schemas.shopping.types import line_item_create_req
from ucp_sdk.models.schemas.shopping.types import line_item_update_req


def load_env_file() -> None:
  """Load environment variables from .env file if it exists."""
  env_path = Path(__file__).parent / ".env"
  if env_path.exists():
    load_dotenv(env_path)


def get_hedera_merchant_account(discovery_data: dict) -> str | None:
  """Extract Hedera merchant account from discovery data.

  Args:
      discovery_data: The discovery response from the merchant.

  Returns:
      The merchant's Hedera account ID, or None if not found.
  """
  handlers = discovery_data.get("payment", {}).get("handlers", [])
  for handler in handlers:
    if handler.get("name") == "com.hedera.hbar":
      config = handler.get("config", {})
      return config.get("merchant_account_id")
  return None


def create_hedera_payment(
  customer_account_id: str,
  customer_private_key: str,
  merchant_account_id: str,
  amount_hbar: float,
  checkout_id: str,
  network_name: str = "testnet",
) -> str:
  """Create and sign a Hedera transfer transaction.

  Args:
      customer_account_id: The customer's Hedera account ID (e.g., 0.0.12345).
      customer_private_key: The customer's private key (hex format with 0x).
      merchant_account_id: The merchant's Hedera account ID.
      amount_hbar: The amount to transfer in HBAR.
      checkout_id: The checkout session ID for memo.
      network_name: The Hedera network (testnet or mainnet).

  Returns:
      Base64-encoded signed transaction bytes.
  """
  logger = logging.getLogger(__name__)

  # Parse account IDs
  customer_acct = AccountId.from_string(customer_account_id)
  merchant_acct = AccountId.from_string(merchant_account_id)

  # Parse private key (remove 0x prefix if present)
  key_hex = customer_private_key
  if key_hex.startswith("0x"):
    key_hex = key_hex[2:]
  private_key = PrivateKey.from_string(key_hex)

  # Create network and client
  if network_name == "mainnet":
    network = Network(network="mainnet")
  else:
    network = Network(network="testnet")

  client = Client(network)
  client.set_operator(customer_acct, private_key)

  # Convert HBAR to tinybars (1 HBAR = 100,000,000 tinybars)
  amount_tinybars = int(amount_hbar * 100_000_000)

  logger.info(
    "Transfer: %.2f HBAR from %s to %s",
    amount_hbar,
    customer_account_id,
    merchant_account_id,
  )

  # Create transfer transaction
  transfer_tx = (
    TransferTransaction()
    .add_hbar_transfer(customer_acct, -amount_tinybars)
    .add_hbar_transfer(merchant_acct, amount_tinybars)
    .set_transaction_memo(f"UCP Checkout: {checkout_id}")
    .freeze_with(client)
    .sign(private_key)
  )

  # Get transaction bytes and encode as base64
  tx_bytes = transfer_tx.to_bytes()
  return base64.b64encode(tx_bytes).decode("utf-8")


def get_headers() -> dict[str, str]:
  """Generate necessary headers for UCP requests."""
  return {
    "UCP-Agent": 'profile="https://agent.example/profile"',
    "request-signature": "test",
    "idempotency-key": str(uuid.uuid4()),
    "request-id": str(uuid.uuid4()),
  }


def remove_none_values(obj):
  """Recursively remove keys with None values from a dictionary or list."""
  if isinstance(obj, dict):
    return {k: remove_none_values(v) for k, v in obj.items() if v is not None}
  elif isinstance(obj, list):
    return [remove_none_values(v) for v in obj]
  else:
    return obj


def log_interaction(
  filename: str,
  method: str,
  url: str,
  headers: dict[str, str],
  json_body: dict[str, object] | None,
  response: httpx.Response,
  step_description: str,
  replacements: dict[str, str] | None = None,
  extractions: dict[str, str] | None = None,
):
  """Log the request and response to a markdown file."""
  replacements = replacements or {}

  extractions = extractions or {}

  with Path(filename).open("a", encoding="utf-8") as f:
    f.write(f"## {step_description}\n\n")

    # --- Request (Curl) ---
    # Apply replacements to URL
    display_url = url
    for val, var_name in replacements.items():
      if val in display_url:
        display_url = display_url.replace(val, f"${var_name}")

    curl_cmd = f"export RESPONSE=$(curl -s -X {method} {display_url} \\\n"

    # Headers
    # We generally don't tokenize headers in this simple script,
    # but could if needed.
    for k, v in headers.items():
      curl_cmd += f"  -H '{k}: {v}' \\\n"

    # Body
    if json_body:
      curl_cmd += "  -H 'Content-Type: application/json' \\\n"
      clean_body = remove_none_values(json_body)
      json_str = json.dumps(clean_body, indent=2)

      # Apply replacements to body
      for val, var_name in replacements.items():
        # Simple string replacement - safer to do on the JSON string
        # than traversing the dict for this doc-gen purpose.
        if val in json_str:
          json_str = json_str.replace(val, f"${var_name}")

      curl_cmd += f"  -d '{json_str}')\n"
    else:
      curl_cmd = curl_cmd.rstrip(" \\\n") + ")\n"

    f.write("### Request\n\n```bash\n" + curl_cmd + "```\n\n")

    # --- Response ---

    f.write("### Response\n\n")

    try:
      resp_json = response.json()
      clean_resp = remove_none_values(resp_json)
      f.write("```json\n" + json.dumps(clean_resp, indent=2) + "\n```\n\n")
    except json.JSONDecodeError:
      f.write(f"```\n{response.text}\n```\n\n")

    # --- Extract Variables ---
    if extractions:
      f.write("### Extract Variables\n\n```bash\n")
      for var_name, jq_expr in extractions.items():
        # We assume the user has the response in a variable or pipe.
        # For the snippet, we'll assume they pipe the previous curl output.
        f.write(f"export {var_name}=$(echo $RESPONSE | jq -r '{jq_expr}')\n")
      f.write("```\n\n")


def main() -> None:
  """Run the happy path client with Hedera payment."""
  # Load .env file first
  load_env_file()

  parser = argparse.ArgumentParser()

  parser.add_argument(
    "--server_url",
    default="http://localhost:8182",
    help="Base URL of the UCP Server",
  )

  parser.add_argument(
    "--export_requests_to",
    default=None,
    help="Path to export requests and responses as markdown.",
  )

  parser.add_argument(
    "--hedera_customer_account_id",
    default=os.environ.get("HEDERA_CUSTOMER_ACCOUNT_ID"),
    help="Hedera customer account ID (e.g., 0.0.12345)",
  )

  parser.add_argument(
    "--hedera_customer_private_key",
    default=os.environ.get("HEDERA_CUSTOMER_PRIVATE_KEY"),
    help="Hedera customer private key (hex format with 0x prefix)",
  )

  parser.add_argument(
    "--hedera_network",
    default=os.environ.get("HEDERA_NETWORK", "testnet"),
    help="Hedera network (testnet or mainnet)",
  )

  args = parser.parse_args()

  # Configure Logging

  logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
  )

  logger = logging.getLogger(__name__)

  # Validate Hedera credentials at startup (fail fast)
  hedera_customer_account = args.hedera_customer_account_id
  hedera_customer_key = args.hedera_customer_private_key
  hedera_network = args.hedera_network

  if not hedera_customer_account or not hedera_customer_key:
    logger.error(
      "Hedera credentials required. Set HEDERA_CUSTOMER_ACCOUNT_ID and "
      "HEDERA_CUSTOMER_PRIVATE_KEY environment variables or use CLI args."
    )
    return

  logger.info("Using Hedera payment with account: %s", hedera_customer_account)

  client = httpx.Client(base_url=args.server_url)

  # Clear the export file if it exists
  if args.export_requests_to:
    with Path(args.export_requests_to).open("w", encoding="utf-8") as f:
      f.write("# UCP Happy Path Interaction Log\n\n")
      f.write("### Configuration\n\n")
      f.write(f"```bash\nexport SERVER_URL={args.server_url}\n```\n\n")
      f.write(
        "> **Note:** In the bash snippets below, `jq` is used to extract"
        " values from the JSON response.\n"
      )
      f.write(
        "> It is assumed that the response body of the previous `curl`"
        " command is captured in a variable named `$RESPONSE`.\n\n"
      )

  # Track dynamic values to replace in subsequent requests
  # Map: actual_value -> variable_name
  global_replacements: dict[str, str] = {args.server_url: "SERVER_URL"}

  try:
    # ==========================================================================

    # STEP 0: Discovery

    # ==========================================================================

    logger.info("STEP 0: Discovery - Asking merchant what they support...")

    url = "/.well-known/ucp"

    response = client.get(url)

    if args.export_requests_to:
      log_interaction(
        args.export_requests_to,
        "GET",
        f"{args.server_url}{url}",
        {},
        None,
        response,
        "Step 0: Discovery",
        replacements=global_replacements,
      )

    if response.status_code != 200:
      logger.error("Discovery failed: %s", response.text)

      return

    discovery_data = response.json()

    supported_handlers = discovery_data.get("payment", {}).get("handlers", [])

    logger.info(
      "Merchant supports %d payment handlers:", len(supported_handlers)
    )

    for h in supported_handlers:
      logger.info(" - %s (%s)", h["id"], h["name"])

    # Extract Hedera merchant account
    hedera_merchant_account = get_hedera_merchant_account(discovery_data)
    if not hedera_merchant_account:
      logger.error(
        "Merchant does not support Hedera payments (com.hedera.hbar). Aborting."
      )
      return

    logger.info("Hedera merchant account: %s", hedera_merchant_account)

    # ==========================================================================

    # STEP 1: Create a Checkout Session

    # ==========================================================================

    logger.info("\nSTEP 1: Creating a new Checkout Session...")

    # We start with one item: "Red Rose"

    item1 = item_create_req.ItemCreateRequest(
      id="bouquet_roses", title="Red Rose"
    )

    line_item1 = line_item_create_req.LineItemCreateRequest(
      quantity=1, item=item1
    )

    # We initialize the payment section with the handlers we discovered.

    # We do NOT select an instrument yet (selected_instrument_id=None).

    payment_req = payment_create_req.PaymentCreateRequest(
      instruments=[],
      selected_instrument_id=None,
      handlers=supported_handlers,  # Pass back what we found (or a subset)
    )

    # We include the buyer to trigger address lookup on the server

    buyer_req = buyer.Buyer(full_name="John Doe", email="john.doe@example.com")

    create_payload = checkout_create_req.CheckoutCreateRequest(
      currency="USD",
      line_items=[line_item1],
      payment=payment_req,
      buyer=buyer_req,
    )

    headers = get_headers()

    url = "/checkout-sessions"

    json_body = create_payload.model_dump(
      mode="json", by_alias=True, exclude_none=True
    )

    response = client.post(
      url,
      json=json_body,
      headers=headers,
    )

    checkout_data = response.json()

    checkout_id = checkout_data.get("id")

    # Extract IDs for documentation

    extractions = {}
    if checkout_id:
      global_replacements[checkout_id] = "CHECKOUT_ID"
      extractions["CHECKOUT_ID"] = ".id"

    # We also want to capture the line item ID if possible,
    # though it might change order. We'll grab the first one.

    if checkout_data.get("line_items"):
      li_id = checkout_data["line_items"][0]["id"]
      global_replacements[li_id] = "LINE_ITEM_1_ID"
      extractions["LINE_ITEM_1_ID"] = ".line_items[0].id"

    if args.export_requests_to:
      log_interaction(
        args.export_requests_to,
        "POST",
        f"{args.server_url}{url}",
        headers,
        json_body,
        response,
        "Step 1: Create Checkout Session",
        replacements=global_replacements,
        extractions=extractions,
      )

    if response.status_code not in [200, 201]:
      logger.error("Failed to create checkout: %s", response.text)

      return

    logger.info("Successfully created checkout session: %s", checkout_id)

    logger.info(
      "Current Total: %s cents", checkout_data["totals"][-1]["amount"]
    )

    # ==========================================================================

    # STEP 2: Add More Items (Update Checkout)

    # ==========================================================================

    logger.info("\nSTEP 2: Adding a second item (Ceramic Pot)...")

    # Update Item 1 (Roses) - Keep quantity 1

    item1_update = item_update_req.ItemUpdateRequest(
      id="bouquet_roses", title="Red Rose"
    )

    line_item1_update = line_item_update_req.LineItemUpdateRequest(
      id=checkout_data["line_items"][0]["id"],
      quantity=1,
      item=item1_update,
    )

    # Add Item 2 (Ceramic Pot) - Quantity 2

    item2_update = item_update_req.ItemUpdateRequest(
      id="pot_ceramic", title="Ceramic Pot"
    )

    line_item2_update = line_item_update_req.LineItemUpdateRequest(
      quantity=2,
      item=item2_update,
    )

    # Construct the Update Payload

    update_payload = checkout_update_req.CheckoutUpdateRequest(
      id=checkout_id,
      line_items=[line_item1_update, line_item2_update],
      currency=checkout_data["currency"],
      payment=checkout_data["payment"],
    )

    headers = get_headers()

    url = f"/checkout-sessions/{checkout_id}"

    json_body = update_payload.model_dump(
      mode="json", by_alias=True, exclude_none=True
    )

    response = client.put(
      url,
      json=json_body,
      headers=headers,
    )

    checkout_data = response.json()

    extractions = {}

    # Capture the new line item ID

    # Assuming it's the second one since we just added it

    if len(checkout_data.get("line_items", [])) > 1:
      li_2_id = checkout_data["line_items"][1]["id"]

      global_replacements[li_2_id] = "LINE_ITEM_2_ID"

      extractions["LINE_ITEM_2_ID"] = ".line_items[1].id"

    if args.export_requests_to:
      log_interaction(
        args.export_requests_to,
        "PUT",
        f"{args.server_url}{url}",
        headers,
        json_body,
        response,
        "Step 2: Add Items (Update Checkout)",
        replacements=global_replacements,
        extractions=extractions,
      )

    if response.status_code != 200:
      logger.error("Failed to add items: %s", response.text)

      return

    logger.info("Successfully added items.")

    logger.info("New Total: %s cents", checkout_data["totals"][-1]["amount"])

    logger.info("Item Count: %d", len(checkout_data["line_items"]))

    # ==========================================================================

    # STEP 3: Apply Discount

    # ==========================================================================

    logger.info("\nSTEP 3: Applying Discount (10%% OFF)...")

    # Re-construct line items for update

    # We need IDs from the current session

    li_1 = next(
      li
      for li in checkout_data["line_items"]
      if li["item"]["id"] == "bouquet_roses"
    )

    li_2 = next(
      li
      for li in checkout_data["line_items"]
      if li["item"]["id"] == "pot_ceramic"
    )

    item1_update = item_update_req.ItemUpdateRequest(
      id="bouquet_roses", title="Red Rose"
    )

    line_item1_update = line_item_update_req.LineItemUpdateRequest(
      id=li_1["id"],
      quantity=1,
      item=item1_update,
    )

    item2_update = item_update_req.ItemUpdateRequest(
      id="pot_ceramic", title="Ceramic Pot"
    )

    line_item2_update = line_item_update_req.LineItemUpdateRequest(
      id=li_2["id"],
      quantity=2,
      item=item2_update,
    )

    # Construct the Update Payload

    update_payload = checkout_update_req.CheckoutUpdateRequest(
      id=checkout_id,
      line_items=[line_item1_update, line_item2_update],
      currency=checkout_data["currency"],
      payment=checkout_data["payment"],
    )

    update_dict = update_payload.model_dump(
      mode="json", by_alias=True, exclude_none=True
    )

    update_dict["discounts"] = {"codes": ["10OFF"]}

    headers = get_headers()

    url = f"/checkout-sessions/{checkout_id}"

    json_body = update_dict

    response = client.put(
      url,
      json=json_body,
      headers=headers,
    )

    if args.export_requests_to:
      log_interaction(
        args.export_requests_to,
        "PUT",
        f"{args.server_url}{url}",
        headers,
        json_body,
        response,
        "Step 3: Apply Discount",
        replacements=global_replacements,
      )

    if response.status_code != 200:
      logger.error("Failed to apply discount: %s", response.text)

      return

    checkout_data = response.json()

    logger.info("Successfully applied discount.")

    logger.info("New Total: %s cents", checkout_data["totals"][-1]["amount"])

    discounts_applied = checkout_data.get("discounts", {}).get("applied", [])

    if discounts_applied:
      logger.info(
        "Applied Discounts: %s", [d["code"] for d in discounts_applied]
      )

    else:
      logger.warning("No discounts applied!")

    # ==========================================================================

    # STEP 4: Select Fulfillment Option

    # ==========================================================================

    logger.info("\nSTEP 4: Selecting Fulfillment Option...")

    # Ensure fulfillment options are generated

    if not checkout_data.get("fulfillment") or not checkout_data[
      "fulfillment"
    ].get("methods"):
      logger.info("STEP 4: Triggering fulfillment option generation...")

      # Re-construct line items for update to satisfy strict validation

      # We need IDs from the current session

      li_1 = next(
        li
        for li in checkout_data["line_items"]
        if li["item"]["id"] == "bouquet_roses"
      )

      li_2 = next(
        li
        for li in checkout_data["line_items"]
        if li["item"]["id"] == "pot_ceramic"
      )

      item1_update = item_update_req.ItemUpdateRequest(
        id="bouquet_roses", title="Red Rose"
      )

      line_item1_update = line_item_update_req.LineItemUpdateRequest(
        id=li_1["id"],
        quantity=1,
        item=item1_update,
      )

      item2_update = item_update_req.ItemUpdateRequest(
        id="pot_ceramic", title="Ceramic Pot"
      )

      line_item2_update = line_item_update_req.LineItemUpdateRequest(
        id=li_2["id"],
        quantity=2,
        item=item2_update,
      )

      # Construct full update payload

      trigger_req = checkout_update_req.CheckoutUpdateRequest(
        id=checkout_id,
        line_items=[line_item1_update, line_item2_update],
        currency=checkout_data["currency"],
        payment=checkout_data["payment"],
        fulfillment={"methods": [{"type": "shipping"}]},
      )

      trigger_payload = trigger_req.model_dump(
        mode="json", by_alias=True, exclude_none=True
      )

      url = f"/checkout-sessions/{checkout_id}"

      headers = get_headers()

      response = client.put(url, json=trigger_payload, headers=headers)

      checkout_data = response.json()

      # Extract Fulfillment Method ID (though not always needed if we have
      # just 1)

      extractions = {}

      if checkout_data.get("fulfillment") and checkout_data["fulfillment"].get(
        "methods"
      ):
        method_id = checkout_data["fulfillment"]["methods"][0]["id"]

        global_replacements[method_id] = "FULFILLMENT_METHOD_ID"

        extractions["FULFILLMENT_METHOD_ID"] = ".fulfillment.methods[0].id"

        # Also destinations

        destinations = checkout_data["fulfillment"]["methods"][0].get(
          "destinations", []
        )

        if destinations:
          # Assuming addr_1 is first

          dest_id = destinations[0]["id"]

          global_replacements[dest_id] = "DESTINATION_ID"

          extractions["DESTINATION_ID"] = (
            ".fulfillment.methods[0].destinations[0].id"
          )

      if args.export_requests_to:
        log_interaction(
          args.export_requests_to,
          "PUT",
          f"{args.server_url}{url}",
          headers,
          trigger_payload,
          response,
          "Step 4: Trigger Fulfillment",
          replacements=global_replacements,
          extractions=extractions,
        )

      if response.status_code == 200:
        checkout_data = response.json()

      else:
        logger.warning("Failed to trigger fulfillment: %s", response.text)

    if checkout_data.get("fulfillment") and checkout_data["fulfillment"].get(
      "methods"
    ):
      method = checkout_data["fulfillment"]["methods"][0]

      if method.get("destinations"):
        dest_id = method["destinations"][0]["id"]

        logger.info("STEP 5: Selecting destination: %s", dest_id)

        # 1. Select Destination to calculate options

        # We must send full payload again

        trigger_req.fulfillment = {
          "methods": [{"type": "shipping", "selected_destination_id": dest_id}]
        }

        payload = trigger_req.model_dump(
          mode="json", by_alias=True, exclude_none=True
        )

        url = f"/checkout-sessions/{checkout_id}"

        headers = get_headers()

        response = client.put(
          url,
          json=payload,
          headers=headers,
        )

        if args.export_requests_to:
          log_interaction(
            args.export_requests_to,
            "PUT",
            f"{args.server_url}{url}",
            headers,
            payload,
            response,
            "Step 5: Select Destination",
            replacements=global_replacements,
          )

        if response.status_code != 200:
          logger.error("Failed to select destination: %s", response.text)

          return

        checkout_data = response.json()

        # 2. Select Option

        method = checkout_data["fulfillment"]["methods"][0]

        if method.get("groups") and method["groups"][0].get("options"):
          option_id = method["groups"][0]["options"][0]["id"]

          logger.info("STEP 6: Selecting option: %s", option_id)

          trigger_req.fulfillment = {
            "methods": [
              {
                "type": "shipping",
                "selected_destination_id": dest_id,
                "groups": [{"selected_option_id": option_id}],
              }
            ]
          }

          payload = trigger_req.model_dump(
            mode="json", by_alias=True, exclude_none=True
          )

          headers = get_headers()

          response = client.put(
            url,
            json=payload,
            headers=headers,
          )

          if args.export_requests_to:
            log_interaction(
              args.export_requests_to,
              "PUT",
              f"{args.server_url}{url}",
              headers,
              payload,
              response,
              "Step 6: Select Option",
              replacements=global_replacements,
            )

          if response.status_code != 200:
            logger.error("Failed to select option: %s", response.text)

            return

          checkout_data = response.json()

          logger.info("Fulfillment option selected.")

          logger.info(
            "Updated Total: %s cents", checkout_data["totals"][-1]["amount"]
          )

    # ==========================================================================

    # STEP 7: Complete Checkout (Hedera Payment)

    # ==========================================================================

    logger.info("\nSTEP 7: Processing Hedera Payment...")

    # Verify merchant supports Hedera payment
    target_handler = "hedera_payment"
    if not any(
      h.get("name") == "com.hedera.hbar" for h in supported_handlers
    ):
      logger.error(
        "Merchant does not support Hedera payments. Aborting."
      )
      return

    # Convert USD cents to HBAR (using $0.05/HBAR rate)
    total_usd = checkout_data["totals"][-1]["amount"] / 100.0
    amount_hbar = total_usd / 0.05

    logger.info("Total: $%.2f USD = %.2f HBAR", total_usd, amount_hbar)

    # Create and sign Hedera transaction
    credential = create_hedera_payment(
      customer_account_id=hedera_customer_account,
      customer_private_key=hedera_customer_key,
      merchant_account_id=hedera_merchant_account,
      amount_hbar=amount_hbar,
      checkout_id=checkout_id,
      network_name=hedera_network,
    )

    final_payload = {
      "payment_data": {
        "id": f"instr_hedera_{uuid.uuid4().hex[:8]}",
        "handler_id": target_handler,
        "handler_name": "com.hedera.hbar",
        "type": "crypto",
        "credential": credential,
      }
    }

    headers = get_headers()

    url = f"/checkout-sessions/{checkout_id}/complete"

    response = client.post(
      url,
      json=final_payload,
      headers=headers,
    )

    final_data = response.json()

    extractions = {}

    if final_data.get("order") and final_data["order"].get("id"):
      order_id = final_data["order"]["id"]

      global_replacements[order_id] = "ORDER_ID"

      extractions["ORDER_ID"] = ".order.id"

    if args.export_requests_to:
      log_interaction(
        args.export_requests_to,
        "POST",
        f"{args.server_url}{url}",
        headers,
        final_payload,
        response,
        "Step 7: Complete Checkout (Hedera Payment)",
        replacements=global_replacements,
        extractions=extractions,
      )

    if response.status_code != 200:
      logger.error("Payment failed: %s", response.text)

      return

    logger.info("Payment Successful!")

    logger.info("Checkout Status: %s", final_data["status"])

    logger.info("Order ID: %s", final_data["order"]["id"])

    logger.info("Order Permalink: %s", final_data["order"]["permalink_url"])

    # Log Hedera-specific metadata if present
    order_metadata = final_data.get("order", {}).get("metadata", {})
    if order_metadata.get("hedera_transaction_id"):
      logger.info(
        "Hedera Transaction ID: %s", order_metadata["hedera_transaction_id"]
      )
    if order_metadata.get("hedera_explorer_url"):
      logger.info(
        "Hedera Explorer URL: %s", order_metadata["hedera_explorer_url"]
      )

    # ==========================================================================

    # DONE

    # ==========================================================================

    logger.info("\nHappy Path completed successfully with Hedera payment.")

  except Exception:  # pylint: disable=broad-exception-caught
    logger.exception("An unexpected error occurred:")

  finally:
    client.close()


if __name__ == "__main__":
  main()
