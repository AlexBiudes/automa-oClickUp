import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# ClickUp Configuration
CLICKUP_API_TOKEN = os.getenv("CLICKUP_API_TOKEN")
CLICKUP_LIST_ID = os.getenv("CLICKUP_LIST_ID", "901712259298")

# Google Cloud / BigQuery Configuration
# Default to gcp_key.json in the workspace root
GCP_KEY_PATH = os.getenv("GCP_KEY_PATH", "gcp_key.json")

# Ensure GOOGLE_APPLICATION_CREDENTIALS points to our service account key
if os.path.exists(GCP_KEY_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(GCP_KEY_PATH)

def validate_config():
    """Validates that all necessary configurations are set."""
    if not CLICKUP_API_TOKEN:
        raise ValueError("CLICKUP_API_TOKEN is not defined in the environment or .env file.")
    if not CLICKUP_LIST_ID:
        raise ValueError("CLICKUP_LIST_ID is not defined in the environment or .env file.")
    if not os.path.exists(GCP_KEY_PATH) and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise ValueError(f"GCP service account key not found at '{GCP_KEY_PATH}' and GOOGLE_APPLICATION_CREDENTIALS is not set.")
    return True
