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
logger = logging.getLogger("conferir_to_coordenador_mover")

def update_single_task(client, task, idx, total):
    task_id = task["id"]
    task_name = task["name"]
    logger.info(f"[{idx}/{total}] Mover task '{task_name}' (ID: {task_id}) para status 'validação coordenador'...")
    try:
        client.update_task_status(task_id, "validação coordenador")
        logger.info(f"  ✅ Task {task_id} movida com sucesso.")
        return True
    except Exception as e:
        logger.error(f"  ❌ Falha ao mover task {task_id}: {e}")
        return False

def main():
    try:
        validate_config()
    except Exception as e:
        logger.error(f"Erro na validação da configuração: {e}")
        return

    logger.info("Inicializando ClickUp Client...")
    client = ClickUpClient(CLICKUP_API_TOKEN)
    list_id = CLICKUP_LIST_ID

    logger.info(f"Buscando tasks na lista {list_id} com status 'conferir dados'...")
    
    # Retrieve tasks in status 'conferir dados'
    all_tasks = []
    page = 0
    while True:
        params = [
            ("statuses[]", "conferir dados"),
            ("include_closed", "false"),
            ("page", page)
        ]
        try:
            res_data = client._request("GET", f"list/{list_id}/task", params=params)
        except Exception as e:
            logger.error(f"Falha ao buscar tasks na página {page}: {e}")
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

    logger.info(f"Encontradas {len(all_tasks)} tasks com status 'conferir dados'.")

    if not all_tasks:
        logger.info("Nenhuma task para mover.")
        return

    moved_count = 0
    total_tasks = len(all_tasks)
    
    logger.info(f"Iniciando execução paralela com 10 workers...")
    
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(update_single_task, client, task, idx, total_tasks): task 
            for idx, task in enumerate(all_tasks, 1)
        }
        
        for future in as_completed(futures):
            success = future.result()
            if success:
                moved_count += 1

    logger.info(f"Concluído! Mapeou/moveu com sucesso {moved_count} de {total_tasks} tasks para 'validação coordenador'.")

if __name__ == '__main__':
    main()
