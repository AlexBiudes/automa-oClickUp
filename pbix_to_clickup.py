import os
import sys
import zipfile
import json
import argparse
import requests

def load_env(env_path=".env"):
    """Loads environment variables from a .env file if it exists."""
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ[key.strip()] = val.strip()

def get_clickup_headers():
    token = os.environ.get("CLICKUP_API_TOKEN")
    if not token:
        raise ValueError("CLICKUP_API_TOKEN is not defined in the environment or .env file.")
    return {
        "Authorization": token,
        "Content-Type": "application/json"
    }

def test_connection(list_id=None):
    """Validates the connection to ClickUp API and verifies the specified List ID."""
    print("=== Validating ClickUp Connection ===")
    
    token = os.environ.get("CLICKUP_API_TOKEN")
    if not token:
        print("❌ Error: CLICKUP_API_TOKEN is not set.")
        return False
        
    if not list_id:
        list_id = os.environ.get("CLICKUP_LIST_ID")
        
    if not list_id:
        print("❌ Error: CLICKUP_LIST_ID is not set.")
        return False
        
    print(f"Token (masked): {token[:6]}...{token[-4:] if len(token) > 10 else ''}")
    print(f"List ID: {list_id}")
    
    url = f"https://api.clickup.com/api/v2/list/{list_id}"
    try:
        response = requests.get(url, headers=get_clickup_headers())
        if response.status_code == 200:
            list_data = response.json()
            print("✅ Connection Successful!")
            print(f"📋 List Name: '{list_data.get('name')}'")
            print(f"📂 Folder Name: '{list_data.get('folder', {}).get('name')}'")
            print(f"🚀 Space ID: '{list_data.get('space', {}).get('id')}'")
            return True
        else:
            print(f"❌ Connection Failed. HTTP Status: {response.status_code}")
            print(f"Details: {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error during request: {e}")
        return False

def analyze_pbix(pbix_path, output_json=None):
    """Parses a PBIX file and outputs the page/subpage hierarchy in JSON format."""
    print(f"=== Analyzing PBIX Layout: {pbix_path} ===")
    
    if not os.path.exists(pbix_path):
        print(f"❌ Error: File not found at '{pbix_path}'")
        return
        
    try:
        import re
        with zipfile.ZipFile(pbix_path, 'r') as z:
            namelist = z.namelist()
            if 'Report/Layout' not in namelist:
                print("❌ Error: Report/Layout was not found inside the PBIX file.")
                return
                
            layout_data = z.read('Report/Layout')
            
            # Try decoding (Report/Layout is typically UTF-16-LE or UTF-8 with BOM)
            try:
                layout_str = layout_data.decode('utf-16')
            except UnicodeDecodeError:
                try:
                    layout_str = layout_data.decode('utf-8-sig')
                except UnicodeDecodeError:
                    layout_str = layout_data.decode('utf-8', errors='ignore')
                    
            layout_json = json.loads(layout_str)
            sections = layout_json.get('sections', [])
            
            print(f"Found {len(sections)} raw sections/pages inside the report.")
            
            visible_pages = []
            hidden_pages = []
            
            for section in sections:
                display_name = section.get('displayName')
                if display_name:
                    display_name = display_name.strip()
                name = section.get('name')
                
                # Ignore system-generated pages with blank or default technical names if any
                if not display_name or display_name.startswith('ReportSection'):
                    continue
                    
                # Check config for visibility
                config_str = section.get('config', '{}')
                is_hidden = False
                try:
                    config = json.loads(config_str)
                    # 1 means hidden, 0 or not present means visible
                    visibility = config.get('visibility')
                    if visibility == 1 or visibility == '1':
                        is_hidden = True
                except Exception:
                    pass
                
                page_info = {
                    "displayName": display_name,
                    "name": name,
                    "isHidden": is_hidden
                }
                
                if is_hidden:
                    hidden_pages.append(page_info)
                else:
                    visible_pages.append(page_info)
            
            # Grouping structure
            # Initialize groups with visible pages
            groups = {vp['displayName']: [] for vp in visible_pages}
            global_navigation_group_name = "Menús e Navegação Global"
            groups[global_navigation_group_name] = []
            
            # Independent/Unmatched hidden pages will start their own mother page task group
            independent_pages = []
            
            def normalize(text):
                text = text.lower()
                text = re.sub(r'[\_\-\s]+', ' ', text)
                return text.strip()
            
            for hp in hidden_pages:
                hp_name = hp['displayName']
                hp_norm = normalize(hp_name)
                
                # 1. Check if it's a global page
                if any(k in hp_norm for k in ['menu', 'capa', 'glossario', 'glossário', 'ajuda', 'config', 'depara', 'validador', 'home']):
                    groups[global_navigation_group_name].append(hp_name)
                    continue
                
                # 2. Find best matching visible page
                best_match = None
                best_score = 0
                
                for vp in visible_pages:
                    vp_name = vp['displayName']
                    vp_norm = normalize(vp_name)
                    
                    score = 0
                    
                    # Word-based matching
                    vp_words = set(vp_norm.split())
                    hp_words = set(hp_norm.split())
                    common_words = vp_words.intersection(hp_words)
                    
                    # Special key cases
                    if vp_norm == 'dre' and 'dre' in hp_norm and 'benchmk' not in hp_norm:
                        score = 100
                    elif vp_norm == 'dfc' and 'dfc' in hp_norm:
                        score = 100
                    elif vp_norm == 'ebitda' and 'ebitda' in hp_norm:
                        score = 100
                    elif vp_norm == 'rentabilidade' and 'rentab' in hp_norm:
                        score = 90
                    elif vp_norm == 'blatv' and ('blat' in hp_norm or 'bl a' in hp_norm):
                        score = 95
                    elif vp_norm == 'blpaspl' and ('blpas' in hp_norm or 'bl p' in hp_norm):
                        score = 95
                    elif vp_norm.startswith('aging list adto') and 'adto' in hp_norm and 'fornec' in hp_norm:
                        if 'fornec' in vp_norm or 'client' in vp_norm:
                            score = 80
                    elif vp_norm.startswith('aging list clientes') and 'aging' in hp_norm and 'client' in hp_norm and 'adto' not in hp_norm:
                        score = 90
                    elif vp_norm.startswith('aging list fornecedores') and 'aging' in hp_norm and 'fornec' in hp_norm and 'adto' not in hp_norm:
                        score = 90
                    elif vp_norm in hp_norm or hp_norm in vp_norm:
                        score = len(vp_norm)
                    elif len(common_words) > 0:
                        score = len(common_words) * 2
                        
                    if score > best_score:
                        best_score = score
                        best_match = vp_name
                
                if best_score >= 3:
                    groups[best_match].append(hp_name)
                else:
                    # Treat as independent card (gets its own Mother Page task group)
                    independent_pages.append(hp_name)
            
            # Format the output structure as a list of groups
            structure = []
            
            # First, add the visible pages and their grouped subpages
            for vp in visible_pages:
                vp_name = vp['displayName']
                structure.append({
                    "mother_page": vp_name,
                    "subpages": groups[vp_name]
                })
                
            # Add the global navigation group if it has any pages
            if groups[global_navigation_group_name]:
                structure.append({
                    "mother_page": global_navigation_group_name,
                    "subpages": groups[global_navigation_group_name]
                })
                
            # Add unmatched hidden pages as independent Mother page tasks
            for ip_name in independent_pages:
                structure.append({
                    "mother_page": ip_name,
                    "subpages": []
                })
                
            # Output structure
            if not output_json:
                output_json = "pages_structure.json"
                
            with open(output_json, 'w', encoding='utf-8') as f:
                json.dump(structure, f, indent=2, ensure_ascii=False)
                
            print(f"✅ Analysis complete! Structure saved to: {output_json}")
            print("\nPreview of Detected Structure:")
            for item in structure:
                sub_str = f" -> Subpages: {', '.join(item['subpages'])}" if item['subpages'] else " (No subpages)"
                print(f"  📂 Mother Page: '{item['mother_page']}'{sub_str}")
                
    except Exception as e:
        print(f"❌ Failed to parse PBIX layout: {e}")

def create_tasks_in_clickup(structure_json, list_id=None):
    """Reads page structure from JSON and creates tasks and subtasks in ClickUp."""
    print("=== Creating Tasks in ClickUp ===")
    
    if not os.path.exists(structure_json):
        print(f"❌ Error: Structure JSON file not found at '{structure_json}'")
        return
        
    try:
        with open(structure_json, 'r', encoding='utf-8') as f:
            structure = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load structure JSON: {e}")
        return
        
    if not list_id:
        list_id = os.environ.get("CLICKUP_LIST_ID")
        
    if not list_id:
        print("❌ Error: CLICKUP_LIST_ID is not set.")
        return
        
    headers = get_clickup_headers()
    base_url = f"https://api.clickup.com/api/v2/list/{list_id}/task"
    
    for item in structure:
        mother_page = item.get("mother_page")
        subpages = item.get("subpages", [])
        
        print(f"\nCreating Mother Page Task: '{mother_page}'...")
        
        # Create Mother Page Task
        parent_payload = {
            "name": mother_page,
            "description": f"Card principal para a página '{mother_page}' e suas respectivas sub-páginas."
        }
        
        try:
            res = requests.post(base_url, json=parent_payload, headers=headers)
            if res.status_code != 200 and res.status_code != 201:
                print(f"  ❌ Failed to create task '{mother_page}'. HTTP: {res.status_code}")
                print(f"  Details: {res.text}")
                continue
                
            parent_task = res.json()
            parent_id = parent_task.get("id")
            parent_url = parent_task.get("url")
            print(f"  ✅ Created Mother Task! ID: {parent_id} - URL: {parent_url}")
            
            # Create subtasks for mother page itself
            subtask_names = [f"Mapeamento — {mother_page}", f"Desenvolvimento — {mother_page}"]
            for st_name in subtask_names:
                sub_payload = {
                    "name": st_name,
                    "parent": parent_id
                }
                sub_res = requests.post(base_url, json=sub_payload, headers=headers)
                if sub_res.status_code in (200, 201):
                    print(f"    ✅ Created subtask: '{st_name}'")
                else:
                    print(f"    ❌ Failed to create subtask '{st_name}'. HTTP: {sub_res.status_code}")
            
            # Create subtasks for each subpage
            for subpage in subpages:
                print(f"  Adding subtasks for Subpage: '{subpage}'...")
                sub_page_tasks = [f"Mapeamento — {subpage}", f"Desenvolvimento — {subpage}"]
                for st_name in sub_page_tasks:
                    sub_payload = {
                        "name": st_name,
                        "parent": parent_id
                    }
                    sub_res = requests.post(base_url, json=sub_payload, headers=headers)
                    if sub_res.status_code in (200, 201):
                        print(f"    ✅ Created subtask: '{st_name}'")
                    else:
                        print(f"    ❌ Failed to create subtask '{st_name}'. HTTP: {sub_res.status_code}")
                        
        except Exception as e:
            print(f"  ❌ Error creating tasks for '{mother_page}': {e}")
            
    print("\n🎉 All tasks have been successfully processed!")

def main():
    load_env()
    
    parser = argparse.ArgumentParser(description="PBIX to ClickUp Tasks Generator")
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # test-connection subcommand
    subparsers.add_parser("test-connection", help="Validates the ClickUp token and list ID connections.")
    
    # analyze subcommand
    analyze_parser = subparsers.add_parser("analyze", help="Extracts layout and page list from PBIX.")
    analyze_parser.add_argument("pbix_path", help="Path to the .pbix file.")
    analyze_parser.add_argument("--output", "-o", default="pages_structure.json", help="Path to save the structure JSON.")
    
    # create subcommand
    create_parser = subparsers.add_parser("create", help="Generates tasks in ClickUp based on structure JSON.")
    create_parser.add_argument("structure_json", help="Path to pages_structure.json file.")
    create_parser.add_argument("--list-id", "-l", help="ClickUp list ID (overrides .env CLICKUP_LIST_ID).")
    
    args = parser.parse_args()
    
    if args.command == "test-connection":
        test_connection()
    elif args.command == "analyze":
        analyze_pbix(args.pbix_path, args.output)
    elif args.command == "create":
        create_tasks_in_clickup(args.structure_json, args.list_id)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
