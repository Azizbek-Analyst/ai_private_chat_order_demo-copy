# flower_service.py

import os
import json
import logging
from datetime import datetime
from typing import TypedDict, Optional, Any
import time # <<< timing helper

import requests
import google.generativeai as genai
from langgraph.graph import StateGraph, END
from dotenv import load_dotenv

load_dotenv()

# --- Configuration and Logging ---

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configs
CRYPTOR_SERVICE_URL = os.getenv("CRYPTOR_API_URL", "https://private-layer-397444089703.europe-west1.run.app")
API_KEY = os.getenv("API_KEY", "dev-secret-demo")
TENANT = os.getenv("TENANT", "ai_private_demo")
HEADERS = {"x-api-key": API_KEY}

# LLM setup
genai.configure(api_key=os.getenv("GEMINI_API_KEY","Key"))
SERVICE_MODEL = genai.GenerativeModel("gemini-2.5-flash")

# DB files
DB_FILE = "orders_db.json"
BUNDLES_FILE = "bundles_db.json"

# In-memory DB
ORDERS_DB = {}
BUNDLES_STORAGE = {}
ORDER_COUNTER = 1


# --- Data types ---

class ServiceState(TypedDict):
    """State schema for the LangGraph workflow."""
    user_input: str
    encrypted_input: Optional[str]
    bundles: list
    tenant_id: str
    action: Optional[str]
    tool_result: Optional[str]
    agent_response: Optional[str]
    final_response: Optional[str]


# --- Database helpers ---

def load_db():
    """Load orders and bundles from disk."""
    global ORDERS_DB, BUNDLES_STORAGE, ORDER_COUNTER
    logger.info("--- Initializing storage ---")
    
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                ORDERS_DB = data.get("orders", {})
                ORDER_COUNTER = data.get("counter", 1)
            logger.info(f"Orders loaded: {len(ORDERS_DB)}")
        except Exception as e:
            logger.error(f"Error loading {DB_FILE}: {e}")
    else:
        logger.warning(f"{DB_FILE} not found, creating empty store.")
    
    if os.path.exists(BUNDLES_FILE):
        try:
            with open(BUNDLES_FILE, "r", encoding="utf-8") as f:
                BUNDLES_STORAGE = json.load(f)
            logger.info(f"Bundles loaded: {len(BUNDLES_STORAGE)}")
        except Exception as e:
            logger.error(f"Error loading {BUNDLES_FILE}: {e}")
    else:
        logger.warning(f"{BUNDLES_FILE} not found, creating empty store.")
    
    logger.info("-" * 50)

def save_db():
    """Persist orders data to disk."""
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"orders": ORDERS_DB, "counter": ORDER_COUNTER},
            f,
            indent=2,
            ensure_ascii=False,
        )
    logger.info(f"Order store saved: {DB_FILE}")

def save_bundles(order_id: str, bundles: list):
    """Persist bundles linked to an order."""
    BUNDLES_STORAGE[order_id] = bundles
    with open(BUNDLES_FILE, "w", encoding="utf-8") as f:
        json.dump(BUNDLES_STORAGE, f, indent=2, ensure_ascii=False)
    logger.info(f"Bundles for {order_id} saved: {BUNDLES_FILE}")

def get_bundles(order_id: str) -> list:
    """Fetch bundles for a specific order."""
    bundles = BUNDLES_STORAGE.get(order_id, [])
    logger.info(f"Bundles fetched for {order_id}: {len(bundles)} items.")
    return bundles


# --- Business logic helpers ---

def get_order(order_id: str) -> dict:
    """Fetch encrypted order by ID."""
    logger.info(f"DB_QUERY: Lookup order {order_id}")
    order = ORDERS_DB.get(order_id)
    if not order:
        logger.warning(f"DB_ERROR: Order {order_id} not found")
        return {"error": "Order not found"}
    logger.info(f"DB_RESULT: Order {order_id} found (encrypted)")
    return {**order, "order_id": order_id}


def get_order_decrypted(order_id: str) -> dict:
    """Decrypt order record through the Cryptor Service."""
    logger.info(f"DB_QUERY: Fetch + decrypt order {order_id}")
    order = ORDERS_DB.get(order_id)
    if not order:
        return {"error": "Order not found"}

    bundles = get_bundles(order_id)
    if not bundles:
        logger.warning(f"WARN: Bundles for {order_id} missing, returning encrypted data.")
        return {**order, "order_id": order_id, "note": "Bundles not found for decryption"}

    order_text = json.dumps(order, ensure_ascii=False)
    
    decrypt_payload = {
        "tenant_id": TENANT,
        "text_with_placeholders": order_text,
        "bundles": bundles,
    }
    
    start_time = time.time() # <<< timing measurement

    try:
        resp = requests.post(
            f"{CRYPTOR_SERVICE_URL}/v1/decrypt", json=decrypt_payload, headers=HEADERS
        )
        resp.raise_for_status()
        decrypted_text = resp.json()["text"]
        decrypted_order = json.loads(decrypted_text)
        
        duration_ms = (time.time() - start_time) * 1000 # <<< duration calc
        logger.info(f"CRYPTOR_SUCCESS: Order {order_id} decrypted. Time: {duration_ms:.2f} ms")
        
        return {**decrypted_order, "order_id": order_id}
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000 # <<< duration calc
        logger.error(f"CRYPTOR_ERROR: Failed to decrypt order {order_id}: {e}. Time: {duration_ms:.2f} ms")
        return {**order, "order_id": order_id, "decrypt_error": f"Cryptor service error: {str(e)}"}


def get_all_orders() -> dict:
    """Return every encrypted order."""
    logger.info(f"DB_QUERY: Fetch all orders (total: {len(ORDERS_DB)})")
    # No external calls here; runtime is negligible.
    orders_list = [{**order, "order_id": order_id} for order_id, order in ORDERS_DB.items()]
    return {"orders": orders_list, "total": len(orders_list)}


def create_order(
    customer: str, email: str, phone: str, address: str, items: str, bundles: list
) -> dict:
    """Create a new order with encrypted fields."""
    # No external calls here; runtime is negligible.
    global ORDER_COUNTER
    order_id = f"ORD-{ORDER_COUNTER:03d}"
    ORDER_COUNTER += 1

    logger.info(f"DB: Creating order {order_id} (encrypted data).")
    
    ORDERS_DB[order_id] = {
        "customer": customer,
        "email": email,
        "phone": phone,
        "address": address,
        "items": items,
        "status": "processing",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    save_db()
    save_bundles(order_id, bundles)
    
    logger.info(f"DB_SUCCESS: Order {order_id} created.")
    return {"order_id": order_id, "status": "created"}


# --- LangGraph nodes (agent) ---


def process_input(state: ServiceState) -> ServiceState:
    """Step 1: Detect and encrypt PII via the Cryptor Service."""
    logger.info("\n--- STEP 1: PII DETECTION & ENCRYPTION LAYER ---")
    
    payload = {
        "tenant_id": TENANT,
        "text": state["user_input"],
        "threshold": 0.35,
        "schema": "v1",
    }
    
    logger.info(f"PRIVATE_REQ: POST {CRYPTOR_SERVICE_URL}/v1/detect-encrypt")
    start_time = time.time() # <<< timing measurement
    
    try:
        resp = requests.post(f"{CRYPTOR_SERVICE_URL}/v1/detect-encrypt", json=payload, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()
        
        duration_ms = (time.time() - start_time) * 1000 # <<< duration calc
        logger.info(f"PRIVATE_RESP: PII items detected: {len(data['bundles'])}. Time: {duration_ms:.2f} ms")
        
        return {
            **state,
            "encrypted_input": data["text_with_placeholders"],
            "bundles": data["bundles"],
            "tenant_id": data["tenant_id"],
        }
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000 # <<< duration calc
        logger.error(f"PRIVATE_ERROR: Failed to encrypt: {e}. Time: {duration_ms:.2f} ms")
        raise RuntimeError(f"Cryptor detect-encrypt failure: {e}")


def determine_action(state: ServiceState) -> ServiceState:
    """Step 2: Decide which business action to run (get/create/etc)."""
    logger.info("\n--- STEP 2: ACTION SELECTION (LLM) ---")
    logger.info(f"LLM_INPUT: {state['encrypted_input']}")
    
    prompt = f"""You are the backend action selector. Analyze the customer's request below (PII already replaced with placeholders) and decide which operation to run.
Request: {state['encrypted_input']}

Rules for create_order:
- Fields 'customer', 'email', 'phone', 'address' MUST contain the placeholders exactly as provided.
- Field 'items' must include the full text description of the products from the request. Always wrap the value of 'items' in double quotes.

Return ONLY a JSON object shaped as one of the following:
- Lookup by ID: {{"action": "get_order", "order_id": "ORD-XXX"}}
- List orders: {{"action": "get_all_orders"}}
- Create order: {{"action": "create_order", "customer": "[PERSON_X]", "email": "[EMAIL_X]", "phone": "[PHONE_X]", "address": "[LOCATION_X]", "items": "text description"}}
"""

    start_time = time.time() # <<< timing measurement
    
    try:
        response = SERVICE_MODEL.generate_content(prompt)
        response_text = response.text.strip()
        
        duration_ms = (time.time() - start_time) * 1000 # <<< duration calc
        
        # Extract the JSON payload robustly from the model output
        start = response_text.find("{")
        end = response_text.rfind("}") + 1
        action_data = json.loads(response_text[start:end])
        
        logger.info(f"LLM_ACTION: {action_data['action']}.")

        return {**state, "action": json.dumps(action_data)}
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000 # <<< duration calc
        logger.error(f"LLM_ERROR: Action selection failed: {e}. Time: {duration_ms:.2f} ms")
        raise RuntimeError(f"Language model action failure: {e}")


def execute_action(state: ServiceState) -> ServiceState:
    """Step 3: Execute the chosen business action."""
    logger.info("\n--- STEP 3: BUSINESS LOGIC EXECUTION ---")
    
    action_data: dict[str, Any] = json.loads(state["action"])
    action_type = action_data.get("action")
    
    logger.info(f"AGENT: Running action: {action_type}")
    
    new_bundles = []
    start_time = time.time() # Timing measurement

    try:
        if action_type == "get_order":
            order_id = action_data.get("order_id", "")
            logger.info(f"Fetching order {order_id} plus bundles")
            result = get_order(order_id)
            # Collect bundles for downstream decrypt
            order_bundles = get_bundles(order_id)
            new_bundles.extend(order_bundles)
            
        elif action_type == "get_all_orders":
            logger.info("Fetching all orders and bundles")
            result = get_all_orders()
            # Collect bundles for every order returned
            order_list = result.get("orders", [])
            for order in order_list:
                order_id = order.get("order_id")
                if order_id:
                    new_bundles.extend(get_bundles(order_id))
            
        elif action_type == "create_order":
            result = create_order(
                action_data.get("customer", ""),
                action_data.get("email", ""),
                action_data.get("phone", ""),
                action_data.get("address", ""),
                action_data.get("items", ""),
                state["bundles"],
            )
        else:
            logger.error(f"ACTION_ERROR: Unknown action: {action_type}")
            result = {"error": f"Unknown action: {action_type}"}

        # --- BUNDLE MERGE & DEDUP ---
        combined_bundles = state["bundles"] + new_bundles

        def bundle_key(bundle: dict[str, Any]) -> Optional[str]:
            if not isinstance(bundle, dict):
                return None
            # detect-encrypt bundles expose placeholders, DB bundles only include the id.
            if "placeholder" in bundle:
                return bundle["placeholder"]
            return bundle.get("id")

        unique_bundles_dict = {}
        for bundle in combined_bundles:
            key = bundle_key(bundle)
            if not key:
                continue
            unique_bundles_dict[key] = bundle

        final_bundles = list(unique_bundles_dict.values())
        # -----------------------------------------------
        
        duration_ms = (time.time() - start_time) * 1000 # Timing
        logger.info(f"ACTION_SUCCESS: {action_type} done. Bundles collected: {len(final_bundles)}. Time: {duration_ms:.2f} ms")

        return {
            **state, 
            "tool_result": json.dumps(result, ensure_ascii=False),
            # Keep the merged bundles for the final decrypt
            "bundles": final_bundles
        }
        
    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000 # Timing
        # str(e) keeps just the message (e.g., missing placeholder)
        error_message = str(e) 
        logger.error(f"ACTION_ERROR: {action_type} failed: {error_message}. Time: {duration_ms:.2f} ms")
        raise RuntimeError(f"Business logic failure: {error_message}")


def format_response(state: ServiceState) -> ServiceState:
    """Step 4: Generate the reply, decrypt, and return it."""
    logger.info("\n--- STEP 4: GENERATE & RESPOND TO CUSTOMER ---")
    
    prompt = f"""You are a friendly customer support agent for a flower shop. Write a concise response using the tool output below.
Always keep PII placeholders (like [PERSON_X], [EMAIL_X]) exactly as provided.

Customer request: {state['encrypted_input']}
Operation result: {state['tool_result']}"""

    start_time = time.time() # <<< timing measurement

    try:
        response = SERVICE_MODEL.generate_content(prompt)
        agent_response = response.text
        
        llm_duration_ms = (time.time() - start_time) * 1000 # <<< duration calc
        logger.info(f"LLM_RESP_RAW: Response with placeholders generated. Time: {llm_duration_ms:.2f} ms")

        decrypt_payload = {
            "tenant_id": state["tenant_id"],
            "text_with_placeholders": agent_response,
            "bundles": state["bundles"],
        }

        logger.info(f"CRYPTOR_REQ: POST {CRYPTOR_SERVICE_URL}/v1/decrypt ({len(state['bundles'])} bundles)")
        decrypt_start = time.time()
        try:
            resp = requests.post(f"{CRYPTOR_SERVICE_URL}/v1/decrypt", json=decrypt_payload, headers=HEADERS)
            resp.raise_for_status()
            data = resp.json()

            decrypt_duration_ms = (time.time() - decrypt_start) * 1000
            final_response = data["text"]
            logger.info(f"CRYPTOR_RESP: Final answer decrypted. Time: {decrypt_duration_ms:.2f} ms")

            return {**state, "agent_response": agent_response, "final_response": final_response}

        except Exception as decrypt_error:
            decrypt_duration_ms = (time.time() - decrypt_start) * 1000
            logger.error(f"CRYPTOR_ERROR: Final decrypt failed: {decrypt_error}. Time: {decrypt_duration_ms:.2f} ms")
            raise RuntimeError(f"Final response decrypt failed: {decrypt_error}")
        
    except Exception as e:
        llm_duration_ms = (time.time() - start_time) * 1000 # <<< duration calc
        logger.error(f"LLM_ERROR: Response generation failed: {e}. Time: {llm_duration_ms:.2f} ms")
        raise RuntimeError(f"Response generation failed: {e}")


# --- LangGraph workflow (unchanged) ---

def create_workflow():
    """Build and compile the LangGraph workflow."""
    workflow = StateGraph(ServiceState)
    workflow.add_node("process_input", process_input)
    workflow.add_node("determine_action", determine_action)
    workflow.add_node("execute_action", execute_action)
    workflow.add_node("format_response", format_response)

    workflow.set_entry_point("process_input")
    workflow.add_edge("process_input", "determine_action")
    workflow.add_edge("determine_action", "execute_action")
    workflow.add_edge("execute_action", "format_response")
    workflow.add_edge("format_response", END)
    
    return workflow.compile()

# Initialization
load_db()
app = create_workflow()
