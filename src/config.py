import os
from dotenv import load_dotenv

# Load environment variables from .env file
# Try loading from parent folder as well, since this is in src/
load_dotenv()
load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

# ClickUp Configuration
CLICKUP_API_TOKEN = os.getenv("CLICKUP_API_TOKEN")
CLICKUP_LIST_ID = os.getenv("CLICKUP_LIST_ID", "901712259298")

# Google Cloud / BigQuery Configuration
# Default to gcp_key.json in the workspace root
GCP_KEY_PATH = os.getenv("GCP_KEY_PATH", os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'gcp_key.json')))

# Ensure GOOGLE_APPLICATION_CREDENTIALS points to our service account key
if os.path.exists(GCP_KEY_PATH):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(GCP_KEY_PATH)
elif os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
    GCP_KEY_PATH = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")

# Path to the specifications file
SPEC_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'specs', 'validation_spec.json'))

def validate_config():
    """Validates that all necessary configurations are set."""
    if not CLICKUP_API_TOKEN:
        raise ValueError("CLICKUP_API_TOKEN is not defined in the environment or .env file.")
    if not CLICKUP_LIST_ID:
        raise ValueError("CLICKUP_LIST_ID is not defined in the environment or .env file.")
    
    # In cloud environments, GOOGLE_APPLICATION_CREDENTIALS might be implicit, so we only check GCP_KEY_PATH if it's set
    if not os.path.exists(GCP_KEY_PATH) and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
        raise ValueError(f"GCP service account key not found and GOOGLE_APPLICATION_CREDENTIALS is not set.")
    return True
