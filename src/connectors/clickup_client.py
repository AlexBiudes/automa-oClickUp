import time
import requests
import logging

logger = logging.getLogger("validation_tool")

class ClickUpClient:
    def __init__(self, api_token: str):
        self.api_token = api_token
        self.headers = {
            "Authorization": self.api_token,
            "Content-Type": "application/json"
        }
        self.base_url = "https://api.clickup.com/api/v2"

    def _request(self, method: str, path: str, json_data: dict = None, params: dict = None, retries: int = 3) -> dict:
        url = f"{self.base_url}/{path}"
        for attempt in range(retries):
            try:
                response = requests.request(
                    method=method,
                    url=url,
                    headers=self.headers,
                    json=json_data,
                    params=params,
                    timeout=15
                )
                if response.status_code == 429:
                    # ClickUp rate limiting, sleep and retry
                    retry_after = int(response.headers.get("Retry-After", 5))
                    logger.warning(f"Rate limited by ClickUp. Sleeping for {retry_after}s (attempt {attempt + 1}/{retries})")
                    time.sleep(retry_after)
                    continue
                
                response.raise_for_status()
                return response.json()
            except requests.exceptions.RequestException as e:
                if attempt == retries - 1:
                    logger.error(f"Request to {url} failed: {e}")
                    raise
                time.sleep(2 ** attempt)
        raise Exception("Failed to execute ClickUp request after retries")

    def get_tasks_to_validate(self, list_id: str) -> list:
        """Retrieves tasks in status 'para começar' and 'conferir dados' from the specified list."""
        logger.info(f"Fetching open tasks from ClickUp List {list_id}")
        
        # Paginate to get all tasks
        page = 0
        all_tasks = []
        while True:
            params = [
                ("statuses[]", "para começar"),
                ("include_closed", "false"),
                ("page", page)
            ]
            res_data = self._request("GET", f"list/{list_id}/task", params=params)
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
            
        logger.info(f"Found {len(all_tasks)} tasks to validate.")
        return all_tasks

    def update_task_status(self, task_id: str, status: str) -> dict:
        """Updates the status of a specific ClickUp task."""
        logger.info(f"Updating status of ClickUp task {task_id} to '{status}'")
        payload = {
            "status": status
        }
        return self._request("PUT", f"task/{task_id}", json_data=payload)

    def add_task_comment(self, task_id: str, comment_text: str) -> dict:
        """Adds a comment to a specific ClickUp task."""
        logger.info(f"Adding comment to ClickUp task {task_id}")
        payload = {
            "comment_text": comment_text,
            "assignee": None
        }
        return self._request("POST", f"task/{task_id}/comment", json_data=payload)
