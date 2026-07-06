import os
import requests

def load_env(env_path=".env"):
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ[key.strip()] = val.strip()

def main():
    load_env()
    token = os.environ.get("CLICKUP_API_TOKEN")
    folder_id = "90177689613"
    
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    
    url = f"https://api.clickup.com/api/v2/folder/{folder_id}/list"
    try:
        res = requests.get(url, headers=headers)
        if res.status_code == 200:
            lists = res.json().get("lists", [])
            print("Lists in ClickUp Folder:")
            for l in lists:
                print(f" - ID: {l.get('id')} | Name: '{l.get('name')}'")
        else:
            print(f"Error: {res.status_code} - {res.text}")
    except Exception as e:
        print(f"Exception: {e}")

if __name__ == '__main__':
    main()
