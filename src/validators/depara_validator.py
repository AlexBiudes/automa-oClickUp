import re
import logging
from src.connectors.bigquery_client import BigQueryClient

logger = logging.getLogger("validation_tool")

class DeparaValidator:
    def __init__(self, bigquery_client: BigQueryClient):
        self.bq_client = bigquery_client

    def clean_account(self, acc: str) -> str:
        """Removes periods, hyphens, and spaces from an account code for prefix matching."""
        return re.sub(r"[.\-\s]", "", str(acc))

    def validate_depara(self, uaid: str) -> dict:
        """
        Validates if all analytical accounts in BALANCETE_ERP have a corresponding
        mapping in plano_dp. Synthetic accounts (group headers) are ignored.
        """
        logger.info(f"Starting De-Para validation for UAID: {uaid}")
        
        try:
            # 1. Get all unique accounts in the trial balance to identify synthetic prefixes
            all_accounts = self.bq_client.get_balancete_accounts(uaid)
            clean_all_codes = {self.clean_account(a) for a in all_accounts}
            
            # 2. Get unmapped accounts from BigQuery (raw list)
            unmapped_raw = self.bq_client.get_unmapped_balancete_accounts(uaid)
            
            # 3. Filter out synthetic accounts
            analytical_unmapped = []
            for acc in unmapped_raw:
                code = acc["conta"]
                desc = acc["descricao"]
                c_code = self.clean_account(code)
                
                # Check if this account code is a prefix of any other account in the trial balance
                is_synthetic = False
                for other in clean_all_codes:
                    if other.startswith(c_code) and len(other) > len(c_code):
                        is_synthetic = True
                        break
                
                if not is_synthetic:
                    analytical_unmapped.append({
                        "conta": code,
                        "descricao": desc
                    })
            
            passed = len(analytical_unmapped) == 0
            if passed:
                logger.info("De-Para validation PASSED. All analytical accounts are mapped.")
            else:
                logger.warning(f"De-Para validation FAILED. Found {len(analytical_unmapped)} unmapped analytical accounts.")
                
            return {
                "passed": passed,
                "unmapped_accounts": analytical_unmapped
            }
            
        except Exception as e:
            logger.error(f"Error in De-Para validation: {e}")
            return {
                "passed": False,
                "error": str(e),
                "unmapped_accounts": []
            }
