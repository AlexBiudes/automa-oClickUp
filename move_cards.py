import os
import time
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import CLICKUP_API_TOKEN, CLICKUP_LIST_ID, validate_config
from connectors.clickup_client import ClickUpClient

# Set up logging to stdout
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s [%(name)s] %(message)s'
)
logger = logging.getLogger("card_mover")

def update_single_task(client, task, idx, total):
    task_id = task["id"]
    task_name = task["name"]
    logger.info(f"[{idx}/{total}] Moving task '{task_name}' (ID: {task_id}) to status 'finalizada'...")
    try:
        client.update_task_status(task_id, "finalizada")
        logger.info(f"  ✅ Task {task_id} moved successfully.")
        return True
    except Exception as e:
        logger.error(f"  ❌ Failed to move task {task_id}: {e}")
        return False

def main():
    try:
        validate_config()
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        return

    logger.info("Initializing ClickUp Client...")
    client = ClickUpClient(CLICKUP_API_TOKEN)
    list_id = CLICKUP_LIST_ID

    logger.info(f"Fetching tasks from list {list_id} in status 'validação coordenador'...")
    
    # Retrieve tasks in status 'validação coordenador'
    all_tasks = []
    page = 0
    while True:
        params = [
            ("statuses[]", "validação coordenador"),
            ("include_closed", "false"),
            ("page", page)
        ]
        try:
            res_data = client._request("GET", f"list/{list_id}/task", params=params)
        except Exception as e:
            logger.error(f"Failed to fetch tasks on page {page}: {e}")
            break
            
        tasks = res_data.get("tasks", [])
        if not tasks:
            break
            
        # Check for duplicates to prevent potential infinite loops
        existing_ids = {t['id'] for t in all_tasks}
        new_tasks = [t for t in tasks if t['id'] not in existing_ids]
        if not new_tasks:
            break
            
        all_tasks.extend(new_tasks)
        page += 1

    logger.info(f"Found {len(all_tasks)} tasks in status 'validação coordenador'.")

    if not all_tasks:
        logger.info("No tasks to move.")
        return

    moved_count = 0
    total_tasks = len(all_tasks)
    
    logger.info(f"Starting parallel execution with 30 workers...")
    
    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = {
            executor.submit(update_single_task, client, task, idx, total_tasks): task 
            for idx, task in enumerate(all_tasks, 1)
        }
        
        for future in as_completed(futures):
            success = future.result()
            if success:
                moved_count += 1

    logger.info(f"Finished! Successfully moved {moved_count} out of {total_tasks} tasks to 'finalizada'.")

if __name__ == '__main__':
    main()
