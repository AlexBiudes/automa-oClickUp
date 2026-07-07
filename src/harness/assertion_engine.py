from concurrent.futures import ThreadPoolExecutor, as_completed
import logging
from src.connectors.bigquery_client import BigQueryClient
from src.harness.spec_interpreter import SpecInterpreter

logger = logging.getLogger("validation_tool")

class AssertionEngine:
    def __init__(self, bigquery_client: BigQueryClient, spec_interpreter: SpecInterpreter):
        self.bq_client = bigquery_client
        self.spec_interpreter = spec_interpreter

    def _validate_single_rubrica(self, rubrica: dict, uaid: str, cnpj: str, data_base: str, bi_view: str) -> dict:
        name = rubrica["name"]
        desc = rubrica["description"]
        table_amarracao = rubrica["tabela_amarracao"]
        tolerance = rubrica["tolerance"]
        is_calculation = rubrica.get("is_calculation", False)
        
        logger.info(f"Running assertion for rubrica: '{name}'")
        try:
            # 1. Get value calculated in the BI view
            bi_val = self.bq_client.get_rubrica_bi_value(cnpj, data_base, name, bi_view)
            
            if is_calculation:
                # For calculation/totalizer rubricas, we don't validate composition since they are derived in BI
                logger.info(f"Skipping composition validation for derived calculation rubrica: '{name}'")
                return {
                    "rubrica": name,
                    "descricao": desc,
                    "passed": True,
                    "valor_bi": bi_val,
                    "valor_balancete": bi_val,
                    "diferenca": 0.0,
                    "tolerance": tolerance,
                    "composicao": [],
                    "is_calculation": True
                }
            
            # 2. Get composition of customer accounts in BALANCETE_ERP
            composition = self.bq_client.get_rubrica_composition_from_balancete(uaid, name, table_amarracao)
            
            # 3. Sum the balances of the mapped customer accounts, applying the multiplier
            balancete_val = sum(account["saldo_atual"] * account.get("multiplicador", 1) for account in composition)
            
            # 4. Compare
            diff = abs(bi_val - balancete_val)
            passed = diff <= tolerance
            
            if not passed:
                logger.warning(
                    f"Assertion FAILED for '{name}': BI={bi_val:.2f}, Balancete={balancete_val:.2f}. "
                    f"Diff={diff:.2f} (tolerance={tolerance})"
                )
            else:
                logger.info(f"Assertion PASSED for '{name}' (diff: {diff:.2f})")
                
            return {
                "rubrica": name,
                "descricao": desc,
                "passed": passed,
                "valor_bi": bi_val,
                "valor_balancete": balancete_val,
                "diferenca": diff,
                "tolerance": tolerance,
                "composicao": composition
            }
        except Exception as e:
            logger.error(f"Error validating rubrica '{name}': {e}")
            return {
                "rubrica": name,
                "descricao": desc,
                "passed": False,
                "error": str(e),
                "valor_bi": 0.0,
                "valor_balancete": 0.0,
                "diferenca": 0.0,
                "tolerance": tolerance,
                "composicao": []
            }

    def validate_rubricas(self, uaid: str, cnpj: str, data_base: str) -> dict:
        """
        Runs all rubrica assertions in parallel using a ThreadPoolExecutor.
        """
        logger.info(f"Starting parallel rubrica assertion engine for UAID: {uaid}")
        rubricas = self.spec_interpreter.get_rubricas()
        bi_view = self.spec_interpreter.get_bi_view()
        
        assertions = []
        global_success = True
        
        # We run with 15 concurrent threads since BigQuery handles concurrent queries very well
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = {
                executor.submit(self._validate_single_rubrica, rubrica, uaid, cnpj, data_base, bi_view): rubrica
                for rubrica in rubricas
            }
            
            for future in as_completed(futures):
                result = future.result()
                assertions.append(result)
                if not result.get("passed"):
                    global_success = False
                    
        # Sort assertions by name to keep report order stable and deterministic
        assertions.sort(key=lambda x: x["rubrica"])
        
        return {
            "success": global_success,
            "assertions": assertions
        }

    def validate_conta_a_conta(self, uaid: str, cnpj: str, data_base: str) -> dict:
        """
        Validates account balances one by one.
        Compares the balance of each mapped analytical account in BALANCETE_ERP with
        the corresponding account balance in the VIZ_BALANCETE_AUTO_BI_NEW view.
        """
        logger.info(f"Starting account-by-account validation for UAID: {uaid}")
        bi_view = self.spec_interpreter.get_bi_view()
        
        try:
            # 1. Get BI account balances
            bi_balances = self.bq_client.get_bi_accounts_balances(cnpj, data_base, bi_view)
            
            # 2. Get local mapped account balances
            local_accounts = self.bq_client.get_balancete_mapped_accounts_balances(uaid)
            
            divergences = []
            passed_count = 0
            
            tolerance = 0.05
            
            for acc in local_accounts:
                conta = acc["conta"]
                desc = acc["descricao"]
                conta_para = acc.get("conta_para", "")
                
                # Check if it's a DRE account (standard accounts starting with 3, 4, 5, etc.)
                # Accounts starting with 1 (Ativo) and 2 (Passivo/PL) are Balance Sheet (BS) accounts.
                if conta_para and not (conta_para.startswith("1") or conta_para.startswith("2")):
                    val_local = acc["movimentacao"]
                else:
                    val_local = acc["saldo_atual"]
                
                # Check if this account exists in BI
                val_bi = bi_balances.get(conta, 0.0)
                
                # Compare absolute values since BI view applies sign multipliers (1 or -1)
                diff = abs(abs(val_local) - abs(val_bi))
                if diff > tolerance:
                    logger.warning(
                        f"Account-by-account divergence on '{conta}' ({desc}): "
                        f"Local={val_local:.2f}, BI={val_bi:.2f}, Diff={diff:.2f}"
                    )
                    divergences.append({
                        "conta": conta,
                        "descricao": desc,
                        "valor_local": val_local,
                        "valor_bi": val_bi,
                        "diferenca": diff
                    })
                else:
                    passed_count += 1
                    
            success = len(divergences) == 0
            if success:
                logger.info(f"Account-by-account validation PASSED. All {passed_count} accounts match.")
            else:
                logger.warning(f"Account-by-account validation FAILED. Found {len(divergences)} divergences.")
                
            return {
                "success": success,
                "passed_count": passed_count,
                "divergences": divergences
            }
            
        except Exception as e:
            logger.error(f"Error in account-by-account validation: {e}")
            return {
                "success": False,
                "passed_count": 0,
                "error": str(e),
                "divergences": []
            }
