
import sys
import json
import logging
from flow_service import (
    app, 
    load_db, 
    get_order_decrypted, 
    ORDERS_DB, 
    BUNDLES_STORAGE, 
    logger
)

# CLI logging shares the core logger config
logger.setLevel(logging.INFO)

# --- CLI view helpers ---

def show_all_orders():
    """Display every encrypted order currently in memory."""
    if not ORDERS_DB:
        print("\n[Storage] No orders stored yet.\n")
        return

    print("\n[Storage] ALL ORDERS (encrypted view):")
    print("=" * 80)
    for order_id, order in ORDERS_DB.items():
        print(f"ID: {order_id}")
        print(f"  Customer (PII): {order.get('customer', 'N/A')}")
        print(f"  Items: {order.get('items', 'N/A')}")
        print(f"  Status: {order.get('status', 'Unknown')}")
        print("-" * 80)
    print()


def show_order_decrypted_cli(order_id: str):
    """Fetch and print the decrypted order details."""
    order = get_order_decrypted(order_id)
    print(f"\n[Decrypt] ORDER {order_id} (plaintext view):")
    print("=" * 80)
    if "error" in order:
        print(f"ERROR: {order['error']}")
    elif "decrypt_error" in order:
        print(f"DECRYPT ERROR: {order['decrypt_error']}")
        for key, value in order.items():
            print(f"{key}: {value}")
    else:
        for key, value in order.items():
            print(f"{key}: {value}")
    print("=" * 80 + "\n")


def show_raw_db():
    """Print the raw in-memory structures (debug helper)."""
    print("\n[DEBUG] ORDERS_DB:")
    print(json.dumps(ORDERS_DB, indent=2, ensure_ascii=False))
    print("\n[DEBUG] BUNDLES_STORAGE:")
    print(json.dumps(BUNDLES_STORAGE, indent=2, ensure_ascii=False))
    print()


def show_history(history):
    """Display conversation history."""
    if not history:
        print("\n[History] Conversation is empty\n")
        return

    print("\n[History] CONVERSATION LOG:")
    print("=" * 80)
    for i, (q, a) in enumerate(history, 1):
        print(f"{i}. You: {q}")
        print(f"   Agent: {a}")
        print("-" * 80)
    print()


def show_help():
    """List every supported slash command."""
    print("\n[Help] AVAILABLE COMMANDS:")
    print("=" * 80)
    print("/orders            - list encrypted orders")
    print("/decrypt ID        - decrypt order by ID, e.g. /decrypt ORD-001")
    print("/db                - dump raw in-memory DBs")
    print("/history           - show previous prompts and answers")
    print("/help              - this help screen")
    print("/exit              - quit the CLI")
    print("\nSAMPLE PROMPTS:")
    print("1. Create: Create an order for John Smith, john@example.com, +1-212-555-0100, Boston, 20 roses")
    print("2. Lookup: Show order ORD-001")
    print("=" * 80 + "\n")


# --- CLI entrypoint ---

if __name__ == "__main__":
    
    print("\nFlower Shop - Customer Support CLI")
    print("Type /help to see the list of commands\n")

    history = []

    while True:
        try:
            user_input = input("➤ ").strip()
        except EOFError:
            break

        if user_input.lower() == "/exit":
            logger.info("User ended the session")
            print("Goodbye!")
            break

        if user_input.lower() == "/orders":
            show_all_orders()
            continue

        if user_input.lower().startswith("/decrypt"):
            parts = user_input.split()
            if len(parts) == 2 and parts[1].startswith("ORD-"):
                show_order_decrypted_cli(parts[1])
            else:
                print("ERROR: Usage /decrypt ORD-XXX\n")
            continue

        if user_input.lower() == "/db":
            show_raw_db()
            continue

        if user_input.lower() == "/history":
            show_history(history)
            continue

        if user_input.lower() == "/help":
            show_help()
            continue

        if not user_input:
            continue

        try:
            logger.info("\n--- RECEIVED CUSTOMER REQUEST ---")
            logger.info(f"USER: {user_input}")
            
            # Invoke LangGraph workflow
            result = app.invoke({"user_input": user_input})
            agent_answer = result.get("agent_response", "")
            final_response_text = result.get("final_response", "")
            history.append((user_input, final_response_text))
            
            placeholder_answer = agent_answer or "(LLM did not return a response)"
            decrypted_answer = final_response_text or "(No final response)"

            print("\n" + "="*80)
            print("[STEP 3] SERVICE RESPONSE BEFORE DECRYPTION:")
            print(placeholder_answer)
            print("="*80 + "\n")

            print("[STEP 4] CUSTOMER-FACING ANSWER:")
            print(decrypted_answer)
            print()

        except RuntimeError as e:
            print(f"PROCESSING ERROR: {e}\n")
        except Exception as e:
            logger.critical(f"Critical failure: {e}", exc_info=True)
            print(f"SYSTEM ERROR: Unexpected issue occurred: {type(e).__name__}\n")
