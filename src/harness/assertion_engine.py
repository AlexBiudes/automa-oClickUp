import logging
from src.connectors.bigquery_client import BigQueryClient
from src.harness.spec_interpreter import SpecInterpreter

logger = logging.getLogger("validation_tool")

class AssertionEngine:
    def __init__(self, bigquery_client: BigQueryClient, spec_interpreter: SpecInterpreter):
        self.bq_client = bigquery_client
        self.spec_interpreter = spec_interpreter

    def validate_rubricas(self, uaid: str, cnpj: str, data_base: str) -> dict:
        """
        Runs all rubrica assertions defined in the spec for the given UAID, CNPJ, and Period.
        Returns a dictionary containing the results of each assertion and a global success flag.
        """
        logger.info(f"Starting rubrica assertion engine for UAID: {uaid}")
        rubricas = self.spec_interpreter.get_rubricas()
        bi_view = self.spec_interpreter.get_bi_view()
        
        assertions = []
        global_success = True
        
        for rubrica in rubricas:
            name = rubrica["name"]
            desc = rubrica["description"]
            table_amarracao = rubrica["tabela_amarracao"]
            tolerance = rubrica["tolerance"]
            
            logger.info(f"Running assertion for rubrica: '{name}'")
            
            try:
                # 1. Get value calculated in the BI view
                bi_val = self.bq_client.get_rubrica_bi_value(cnpj, data_base, name, bi_view)
                
                # 2. Get composition of customer accounts in BALANCETE_ERP
                composition = self.bq_client.get_rubrica_composition_from_balancete(uaid, name, table_amarracao)
                
                # 3. Sum the balances of the mapped customer accounts, applying the multiplier
                balancete_val = sum(account["saldo_atual"] * account.get("multiplicador", 1) for account in composition)
                
                # 4. Compare
                diff = abs(bi_val - balancete_val)
                passed = diff <= tolerance
                
                if not passed:
                    global_success = False
                    logger.warning(
                        f"Assertion FAILED for '{name}': BI={bi_val:.2f}, Balancete={balancete_val:.2f}. "
                        f"Diff={diff:.2f} (tolerance={tolerance})"
                    )
                else:
                    logger.info(f"Assertion PASSED for '{name}' (diff: {diff:.2f})")
                
                assertions.append({
                    "rubrica": name,
                    "descricao": desc,
                    "passed": passed,
                    "valor_bi": bi_val,
                    "valor_balancete": balancete_val,
                    "diferenca": diff,
                    "tolerance": tolerance,
                    "composicao": composition
                })
                
            except Exception as e:
                logger.error(f"Error validating rubrica '{name}': {e}")
                global_success = False
                assertions.append({
                    "rubrica": name,
                    "descricao": desc,
                    "passed": False,
                    "error": str(e),
                    "valor_bi": 0.0,
                    "valor_balancete": 0.0,
                    "diferenca": 0.0,
                    "tolerance": tolerance,
                    "composicao": []
                })
                
        return {
            "success": global_success,
            "assertions": assertions
        }
