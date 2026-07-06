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
