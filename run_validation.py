import os
import sys
import argparse
import logging
import json
import config
from connectors.clickup_client import ClickUpClient
from connectors.bigquery_client import BigQueryClient
from connectors.powerbi_client import PowerBIClient
from validators.data_validator import DataValidator

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("validation_tool")

def run_balance_validation(dry_run=False):
    """
    Main function to orchestrate ClickUp task fetching, BQ validation, and ClickUp updating.
    """
    logger.info("=== Starting Trial Balance Validation ===")
    
    # 1. Validate configs
    try:
        config.validate_config()
    except ValueError as e:
        logger.error(f"Configuration validation failed: {e}")
        sys.exit(1)
        
    # 2. Initialize clients
    clickup_client = ClickUpClient(config.CLICKUP_API_TOKEN)
    bigquery_client = BigQueryClient(config.GCP_KEY_PATH)
    validator = DataValidator(clickup_client, bigquery_client)
    
    # 3. Get tasks
    try:
        tasks = clickup_client.get_tasks_to_validate(config.CLICKUP_LIST_ID)
    except Exception as e:
        logger.error(f"Failed to fetch tasks from ClickUp: {e}")
        sys.exit(1)
        
    if not tasks:
        logger.info("No tasks in 'para começar' status found to validate. Process complete.")
        return
        
    # 4. Iterate and validate
    success_count = 0
    failure_count = 0
    
    for task in tasks:
        logger.info("--------------------------------------------------")
        result = validator.validate_card(task)
        
        task_id = result["task_id"]
        task_name = result["task_name"]
        uaid = result["uaid"]
        success = result["success"]
        next_status = result["next_status"]
        comment = result["comment"]
        
        logger.info(f"Task: '{task_name}'")
        logger.info(f"UAID: {uaid}")
        logger.info(f"Validation Result: {'SUCCESS' if success else 'FAILED'}")
        logger.info(f"Action: Move to status '{next_status}'")
        
        if success:
            success_count += 1
        else:
            failure_count += 1
            
        if dry_run:
            logger.info("[DRY RUN] Would comment on ClickUp task:")
            print(f"\n--- COMMENT CONTENT FOR TASK {task_id} ---\n{comment}\n--------------------------------------\n")
            logger.info(f"[DRY RUN] Would update task status to '{next_status}'")
        else:
            # Write comment
            try:
                clickup_client.add_task_comment(task_id, comment)
                logger.info("✅ Comment added successfully.")
            except Exception as e:
                logger.error(f"❌ Failed to add comment: {e}")
                
            # Update status (only if it needs to change)
            current_status = task.get("status", {}).get("status")
            if current_status != next_status:
                try:
                    clickup_client.update_task_status(task_id, next_status)
                    logger.info(f"✅ Status updated to '{next_status}' successfully.")
                except Exception as e:
                    logger.error(f"❌ Failed to update status: {e}")
            else:
                logger.info(f"Status is already '{next_status}'. No update needed.")
                
    logger.info("==================================================")
    logger.info(f"Validation summary: Total Processed: {len(tasks)} | Passed: {success_count} | Failed: {failure_count}")
    logger.info("=== Process finished ===")


def map_powerbi_tables():
    """
    Scans local Power BI Desktop instances and maps semantic model tables to BigQuery tables.
    """
    logger.info("=== Starting Power BI Semantic Model Mapping ===")
    pbi_client = PowerBIClient()
    instances = pbi_client.find_local_instances()
    
    if not instances:
        logger.warning(
            "❌ No running Power BI Desktop instances found.\n"
            "Please make sure Power BI Desktop is open with your .pbix file loaded, then run this command again."
        )
        return
        
    # Use the first instance found
    instance = instances[0]
    port = instance["port"]
    workspace = instance["workspace"]
    logger.info(f"Connecting to Power BI instance on port {port} (Workspace: {workspace})")
    
    try:
        mappings = pbi_client.map_semantic_model_tables(port)
        output_file = "pbi_table_mapping.json"
        
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(mappings, f, indent=2, ensure_ascii=False)
            
        logger.info(f"✅ Table mapping extracted successfully!")
        logger.info(f"Saved {len(mappings)} table definitions to '{output_file}'")
        
        # Display a summary of the mapped tables
        print("\nSummary of Extracted Mappings:")
        print(f"{'Power BI Table':<40} | {'BigQuery Dataset':<20} | {'BigQuery Table':<30}")
        print("-" * 96)
        for m in mappings:
            pbi_t = m["pbi_table"]
            bq_d = m["bq_dataset"] or "N/A"
            bq_t = m["bq_table"] or "N/A"
            print(f"{pbi_t:<40} | {bq_d:<20} | {bq_t:<30}")
        print("\n")
        
    except Exception as e:
        logger.error(f"❌ Failed to extract Power BI mappings: {e}")


def main():
    parser = argparse.ArgumentParser(description="Autonomous Trial Balance Validator Tool")
    parser.add_argument(
        "--dry-run", 
        action="store_true", 
        help="Runs validation and prints actions to console without making changes in ClickUp"
    )
    parser.add_argument(
        "--map-pbi", 
        action="store_true", 
        help="Connects to running Power BI Desktop and extracts table mappings to pbi_table_mapping.json"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true", 
        help="Enables verbose debugging logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        
    if args.map_pbi:
        map_powerbi_tables()
    else:
        run_balance_validation(dry_run=args.dry_run)

if __name__ == "__main__":
    main()
