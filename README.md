## Features
  - `/orders`, `/decrypt ORD-XXX`, `/db`, `/history`, `/help`, `/exit` commands in `cli.py`.
  - LangGraph workflow in `flow_service.py` that calls the Private Layer Cryptor API for detect+encrypt/decrypt and Gemini for action selection/response.
  - Local persistence in `orders_db.json` and `bundles_db.json` so encrypted orders and placeholder bundles survive restarts.

  ## Prerequisites
  - Python 3.10+
  - Access to the Private Layer Cryptor endpoint and a Google Gemini API key.

  ## Installation
  ```bash
  python -m venv .venv
  source .venv/bin/activate  # or .venv\Scripts\activate on Windows
  pip install -r requirements.txt

  ## Configuration

  Create a .env file (loaded via python-dotenv) with:

  API_KEY=your_private_layer_key
  TENANT=your_tenant_id
  CRYPTOR_API_URL=https://your-cryptor-endpoint
  GEMINI_API_KEY=your_gemini_key

  ## Running the CLI

  python cli.py

  Then type natural language prompts (e.g., “Create an order for …”) or use the slash commands listed by /help.

  ## Data Storage

  - orders_db.json: encrypted orders plus an auto-increment counter.
  - bundles_db.json: placeholder bundles required to decrypt responses.
    Delete these files to reset the demo state.

  ## Troubleshooting

  - If decryption fails, inspect /db output to ensure bundles exist.
  - Make sure API_KEY/GEMINI_API_KEY are valid; otherwise steps 1 or 4 in the workflow will raise RuntimeError.


Example: 

export  GEMINI_API_KEY="AIzaSyAT84ZM_ClVll5V2e9nzQOSYD7cPWeiHbQ"  
python cli.py

Message: Create an order for John Smith, john@example.com, +1-212-555-0100, Boston, 20 roses