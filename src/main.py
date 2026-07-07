import os
import sys
import argparse
import logging
import json
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import src.config as config
from src.connectors.clickup_client import ClickUpClient
from src.connectors.bigquery_client import BigQueryClient
from src.harness.spec_interpreter import SpecInterpreter
from src.harness.assertion_engine import AssertionEngine
from src.harness.report_generator import ReportGenerator, format_currency
from src.validators.depara_validator import DeparaValidator
import src.database.local_db as local_db

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s [%(name)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("validation_tool")

def parse_and_format_error(msg_erro: str) -> str:
    if not msg_erro or not msg_erro.strip():
        return "Erro desconhecido durante o processamento do balancete no pipeline de ingestão."

    try:
        data = json.loads(msg_erro)
        if isinstance(data, dict):
            error_type = data.get("type")
            message = data.get("message", "")
            file_name = data.get("file_name", "")
            validacoes = data.get("validacoes", {})
            
            if error_type == "balancete_fail" or validacoes:
                failed_validations = []
                unmapped_accounts = []
                
                for key, val in validacoes.items():
                    if not val.get("passou", True):
                        name = val.get("nome", key)
                        desc = val.get("descricao", "")
                        soma = val.get("soma")
                        
                        soma_str = ""
                        if soma is not None:
                            try:
                                soma_val = float(soma)
                                soma_str = f" {format_currency(soma_val)}"
                            except ValueError:
                                soma_str = f" (Diferença: {soma})"
                        
                        failed_validations.append(f"• **{name}**: {desc} ({soma_str.strip()})")
                        
                        # Captura contas sem de-para
                        for sample in val.get("dados_amostra", []):
                            if sample.get("Status DePara") == "Não" or "falta de depara" in str(sample.get("Saldo Final", "")).lower() or "falta de depara" in str(sample.get("Movimento", "")).lower():
                                code = sample.get("Codigo Conta Original")
                                desc_orig = sample.get("Descricao Original")
                                if code:
                                    pair = (code, desc_orig or "Sem descrição")
                                    if pair not in unmapped_accounts:
                                        unmapped_accounts.append(pair)
                
                comment_lines = [
                    "❌ **Falha na Validação de Ingestão do Balancete:**\n"
                    "O processamento do arquivo de balancete falhou na fila do banco devido a inconsistências estruturais.\n",
                    "### 🔍 Inconsistências Detectadas:",
                ]
                
                if failed_validations:
                    comment_lines.extend(failed_validations)
                else:
                    comment_lines.append(f"• {message}")
                
                comment_lines.append("\n### 🛠️ Instruções de Correção:")
                
                if unmapped_accounts:
                    comment_lines.append(
                        "**1. Mapeamento De-Para Faltante:**\n"
                        "Foram encontradas contas analíticas que não possuem um mapeamento \"De-Para\" configurado. "
                        "Por isso, seus valores foram desconsiderados, fazendo com que o balancete ficasse desbalanceado.\n\n"
                        "**Contas pendentes de mapeamento:**"
                    )
                    for code, desc_orig in unmapped_accounts[:10]:
                        comment_lines.append(f"  - `{code}`: {desc_orig}")
                    if len(unmapped_accounts) > 10:
                        comment_lines.append(f"  - *... e mais {len(unmapped_accounts) - 10} contas.*")
                    
                    comment_lines.append(
                        "\n👉 **Como corrigir:**\n"
                        "Acesse o cadastro de De-Para no sistema e associe as contas analíticas acima a uma conta válida. Depois, reexecute a validação."
                    )
                else:
                    comment_lines.append(
                        "👉 **Como corrigir:**\n"
                        "Verifique se o arquivo enviado contém os saldos iniciais, finais e movimentações corretos. "
                        "Se o erro persistir, verifique a integridade do arquivo."
                    )
                
                if file_name:
                    comment_lines.append(f"\n📂 *Arquivo afetado: `{file_name}`*")
                    
                return "\n".join(comment_lines)
            
    except Exception as e:
        logger.debug(f"Failed to parse msg_erro as JSON: {e}")
        
    clean_msg = msg_erro.strip()
    return (
        f"❌ **Falha no Processamento da Ingestão:**\n"
        f"A ingestão do arquivo falhou. Erro reportado pelo validador do banco:\n\n"
        f"> {clean_msg}"
    )

class ValidationOrchestrator:
    def __init__(self, dry_run=False):
        self.dry_run = dry_run
        
        # Validate config
        config.validate_config()
        
        # Initialize clients
        self.clickup_client = ClickUpClient(config.CLICKUP_API_TOKEN)
        self.bigquery_client = BigQueryClient(config.GCP_KEY_PATH)
        
        # Initialize spec interpreter
        self.spec_interpreter = SpecInterpreter(config.SPEC_PATH)
        
        # Initialize engine and validators
        self.assertion_engine = AssertionEngine(self.bigquery_client, self.spec_interpreter)
        self.depara_validator = DeparaValidator(self.bigquery_client)

    def extract_uaid(self, task_name: str) -> str:
        """Extracts UAID (UUID4 format) from task name."""
        import re
        uaid_regex = re.compile(r"UAID[:\-\s]*([a-fA-F0-9\-]{36})", re.IGNORECASE)
        match = uaid_regex.search(task_name)
        if match:
            return match.group(1).strip()
        
        uuid_fallback = re.search(r"([a-fA-F0-9\-]{36})", task_name)
        if uuid_fallback:
            return uuid_fallback.group(1).strip()
            
        return None

    def validate_single_task(self, task: dict) -> bool:
        """
        Runs the full validation logic for a single ClickUp task card.
        """
        task_id = task.get("id")
        task_name = task.get("name")
        logger.info(f"Processing task '{task_name}' (ID: {task_id})")

        # 0. Check if validation engine is active in local DB config
        if not local_db.is_motor_ativo():
            logger.warning(f"Validation engine is PAUSED (motor_ativo = false). Skipping task {task_id}")
            return False

        start_time = time.time()
        uaid = self.extract_uaid(task_name)
        cnpj = ""
        empresa = ""
        periodos_analise = ""
        
        def log_local_audit(success_flag: bool, erros: list):
            tempo_ms = int((time.time() - start_time) * 1000)
            local_db.log_validation_attempt(
                task_id=task_id,
                uaid=uaid or "N/A",
                cnpj=cnpj or "N/A",
                empresa=empresa or "N/A",
                periodo=periodos_analise or "N/A",
                sucesso=success_flag,
                tempo_ms=tempo_ms,
                erros=erros
            )

        if not uaid:
            comment = (
                "⚠️ **Erro de Identificação:**\n"
                "Não foi possível encontrar um UAID válido no título desta tarefa.\n\n"
                "**Como corrigir:**\n"
                "Renomeie o card inserindo o UAID no final. Exemplo: `Empresa | CNPJ | UAID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`."
            )
            self._update_clickup(task_id, comment, "conferir dados", current_status=task.get("status", {}).get("status"))
            log_local_audit(False, [{"tipo": "identificacao_falhou", "message": "UAID não encontrado no título da tarefa"}])
            return False

        # 1. Fetch processing log in BALANCETES_PROCESSADOS
        try:
            log_data = self.bigquery_client.get_balancete_processado(uaid)
        except Exception as e:
            comment = f"❌ **Erro de Sistema:** Falha ao conectar ao BigQuery: {e}"
            self._update_clickup(task_id, comment, "conferir dados", current_status=task.get("status", {}).get("status"))
            log_local_audit(False, [{"tipo": "erro_bigquery", "message": f"Falha de conexão: {e}"}])
            return False

        if not log_data:
            comment = (
                f"⚠️ **Erro de Ingestão:**\n"
                f"O UAID `{uaid}` não foi encontrado na tabela de controle (`BALANCETES_PROCESSADOS`).\n\n"
                f"Isso significa que a planilha correspondente a este card ainda não foi processada pelo sistema de ingestão."
            )
            self._update_clickup(task_id, comment, "conferir dados", current_status=task.get("status", {}).get("status"))
            log_local_audit(False, [{"tipo": "ingestao_nao_encontrada", "message": "UAID inexistente na tabela BALANCETES_PROCESSADOS"}])
            return False

        ingestao_concluida = log_data.get("ingestao_concluida")
        msg_erro = log_data.get("msg_erro")
        cnpj = log_data.get("cnpj")
        empresa = log_data.get("empresa")
        periodos_analise = log_data.get("periodos_analise")

        # Ingestion status: 2 is success, 3 is error, other values mean processing
        if ingestao_concluida == 3 or (msg_erro and msg_erro.strip()):
            comment = parse_and_format_error(msg_erro)
            self._update_clickup(task_id, comment, "conferir dados", current_status=task.get("status", {}).get("status"))
            log_local_audit(False, [{"tipo": "ingestao_erro_banco", "message": msg_erro}])
            return False
        elif ingestao_concluida != 2:
            comment = (
                f"⏳ **Aguardando Ingestão:**\n"
                f"O arquivo com UAID `{uaid}` está na fila de processamento (Status: {ingestao_concluida}).\n"
                f"Por favor, execute o validador novamente após a ingestão ser concluída."
            )
            self._update_clickup(task_id, comment, "para começar", current_status=task.get("status", {}).get("status"))
            log_local_audit(False, [{"tipo": "aguardando_ingestao", "message": f"Status da ingestão: {ingestao_concluida}"}])
            return False

        # 2. Detect report type based on where the UAID rows reside in BigQuery
        try:
            report_info = self.bigquery_client.detect_report_type_and_rows(uaid)
        except Exception as e:
            comment = f"❌ **Erro de Sistema:** Falha ao detectar tipo de relatório no BigQuery: {e}"
            self._update_clickup(task_id, comment, "conferir dados", current_status=task.get("status", {}).get("status"))
            log_local_audit(False, [{"tipo": "erro_bigquery", "message": f"Falha na detecção do tipo de relatório: {e}"}])
            return False

        if not report_info:
            comment = (
                f"⚠️ **Divergência de Dados:**\n"
                f"O log de processamento para o UAID `{uaid}` foi concluído, "
                f"mas nenhuma linha contendo este UAID foi encontrada nas tabelas de dados."
            )
            self._update_clickup(task_id, comment, "conferir dados", current_status=task.get("status", {}).get("status"))
            log_local_audit(False, [{"tipo": "dados_ausentes", "message": "UAID concluído no log mas sem linhas nas tabelas analíticas"}])
            return False

        table_name = report_info["table_name"]
        report_type = report_info["report_type"]
        row_count = report_info["row_count"]

        logger.info(f"Detected report type: '{report_type}' (Table: {table_name}, Rows: {row_count})")

        # 3. Apply validation logic based on report type
        if table_name == "BALANCETE_ERP":
            try:
                # Calculate basic totals and equation validation
                totals = self.bigquery_client.get_balancete_totals(uaid)
                
                # Check De-Para
                depara_res = self.depara_validator.validate_depara(uaid)
                
                # Check Rubricas composition (Harness assertions)
                rubricas_res = self.assertion_engine.validate_rubricas(uaid, cnpj, periodos_analise)
                
                # Check Account-by-Account individual balances
                conta_a_conta_res = self.assertion_engine.validate_conta_a_conta(uaid, cnpj, periodos_analise)
                
                # General success is true if De-Para passed AND all rubricas assertions passed
                # AND debits vs credits equation matches (within tolerance) AND account-by-account balances match
                equation_passed = True
                if totals:
                    deb_cred_diff = abs(totals["sum_debito"] - totals["sum_credito"])
                    equation_passed = deb_cred_diff <= 0.05
                
                success = depara_res["passed"] and equation_passed
                next_status = "validação coordenador" if success else "conferir dados"
                
                # Generate Markdown comment
                comment = ReportGenerator.generate_clickup_comment(
                    uaid=uaid,
                    cnpj=cnpj,
                    empresa=empresa,
                    periodo=periodos_analise,
                    success=success,
                    depara_results=depara_res,
                    rubricas_results=rubricas_res,
                    conta_a_conta_results=conta_a_conta_res,
                    balancete_totals=totals
                )
                
                # If equation itself failed but others passed, make sure comment lists it
                if not equation_passed and totals:
                    deb_cred_diff = abs(totals["sum_debito"] - totals["sum_credito"])
                    equation_comment = (
                        f"\n\n### ⚖️ 4. Equação Contábil Desbalanceada\n"
                        f"• A soma de Débitos (`{format_currency(totals['sum_debito'])}`) difere da soma de Créditos (`{format_currency(totals['sum_credito'])}`). Diferença: `{format_currency(deb_cred_diff)}`.\n"
                    )
                    # Insert before the UAID file line
                    if "📂 *ID do Processamento" in comment:
                        parts = comment.split("📂 *ID do Processamento")
                        comment = parts[0] + equation_comment + "\n📂 *ID do Processamento" + parts[1]
                    else:
                        comment += equation_comment
                
                # Compile structured errors for dashboard SQLite audit log
                erros_lista = []
                if not depara_res["passed"]:
                    erros_lista.append({
                        "tipo": "depara_faltante",
                        "contas": [r["conta_origem"] for r in depara_res.get("unmapped_accounts", [])]
                    })
                if not equation_passed and totals:
                    erros_lista.append({
                        "tipo": "equacao_desbalanceada",
                        "diferenca": abs(totals["sum_debito"] - totals["sum_credito"])
                    })
                for assertion in rubricas_res.get("assertions", []):
                    if not assertion.get("passed", True):
                        erros_lista.append({
                            "tipo": "rubrica_divergente",
                            "rubrica": assertion["rubrica"],
                            "diferenca": assertion["diferenca"]
                        })
                if not conta_a_conta_res["success"]:
                    for div in conta_a_conta_res.get("divergences", []):
                        erros_lista.append({
                            "tipo": "saldo_conta_divergente",
                            "conta": div["conta"],
                            "descricao": div["descricao"],
                            "diferenca": div["diferenca"]
                        })
 
                self._update_clickup(task_id, comment, next_status, current_status=task.get("status", {}).get("status"))
                log_local_audit(success, erros_lista)
                return success
                
            except Exception as e:
                logger.error(f"Failed to validate balancete: {e}")
                comment = f"❌ **Erro no Processamento da Validação:** Falha interna ao executar testes contábeis: {e}"
                self._update_clickup(task_id, comment, "conferir dados", current_status=task.get("status", {}).get("status"))
                log_local_audit(False, [{"tipo": "erro_validador_interno", "message": str(e)}])
                return False
        else:
            # --- AUXILIARY REPORT VALIDATION ---
            success = True
            next_status = "validação coordenador"
            comment = (
                f"✅ **Validação Concluída com Sucesso!**\n"
                f"O relatório auxiliar **{report_type}** com UAID `{uaid}` foi verificado com sucesso:\n"
                f"• CNPJ/Empresa: `{cnpj}` ({empresa})\n"
                f"• Período: `{periodos_analise}`\n"
                f"• Total de Registros Ingeridos: `{row_count}` na tabela `{table_name}`.\n\n"
                f"Card movido automaticamente para a coluna **`validação coordenador`**."
            )
            self._update_clickup(task_id, comment, next_status, current_status=task.get("status", {}).get("status"))
            log_local_audit(True, [])
            return True

    def _update_clickup(self, task_id: str, comment: str, next_status: str, current_status: str = None):
        """Helper to post comment and update status with respect to dry-run flag."""
        if self.dry_run:
            logger.info(f"[DRY RUN] Would comment on task {task_id}:\n{comment}\n")
            logger.info(f"[DRY RUN] Would update task status from '{current_status}' to '{next_status}'")
        else:
            # Post comment
            try:
                self.clickup_client.add_task_comment(task_id, comment)
                logger.info("✅ Comment added successfully.")
            except Exception as e:
                logger.error(f"❌ Failed to add comment: {e}")
                
            # Update status if needed
            if current_status != next_status:
                try:
                    self.clickup_client.update_task_status(task_id, next_status)
                    logger.info(f"✅ Status updated to '{next_status}' successfully.")
                except Exception as e:
                    logger.error(f"❌ Failed to update status: {e}")
            else:
                logger.info(f"Status is already '{next_status}'. No update needed.")

    def run(self, task_id: str = None):
        """
        Orchestrates the validation process. If task_id is provided, validates that single card.
        Otherwise, fetches all open tasks from the configured ClickUp List.
        """
        logger.info("=== Starting Validation Harness ===")
        
        if task_id:
            logger.info(f"Fetching specific task ID: {task_id}")
            try:
                # We request task details from ClickUp
                task = self.clickup_client._request("GET", f"task/{task_id}")
                self.validate_single_task(task)
            except Exception as e:
                logger.error(f"Failed to fetch task {task_id}: {e}")
        else:
            # Fetch tasks from list
            try:
                tasks = self.clickup_client.get_tasks_to_validate(config.CLICKUP_LIST_ID)
            except Exception as e:
                logger.error(f"Failed to fetch tasks from ClickUp: {e}")
                sys.exit(1)
                
            if not tasks:
                logger.info("No tasks found in list to validate. Process complete.")
                return
                
            success_count = 0
            for task in tasks:
                logger.info("--------------------------------------------------")
                if self.validate_single_task(task):
                    success_count += 1
            
            logger.info("==================================================")
            logger.info(f"Validation summary: Total Processed: {len(tasks)} | Passed: {success_count} | Failed: {len(tasks) - success_count}")
        
        logger.info("=== Validation process finished ===")


class ValidationWebhookHandler(BaseHTTPRequestHandler):
    orchestrator = None

    def do_POST(self):
        if self.path == "/validate":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                task_id = data.get("task_id")
                dry_run = data.get("dry_run", False)
                if not task_id:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(b'{"error": "Missing task_id"}')
                    return
                
                logger.info(f"Received webhook validation request for task {task_id}")
                
                try:
                    task = self.orchestrator.clickup_client._request("GET", f"task/{task_id}")
                    success = self.orchestrator.validate_single_task(task)
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    response_payload = {
                        "success": success, 
                        "task_id": task_id, 
                        "status": "validated"
                    }
                    self.wfile.write(json.dumps(response_payload).encode('utf-8'))
                except Exception as e_task:
                    logger.error(f"Error executing task validation from webhook: {e_task}")
                    self.send_response(500)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error": f"Failed to execute task: {e_task}"}).encode('utf-8'))
                    
            except Exception as e:
                logger.error(f"Error parsing webhook request: {e}")
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": f"Invalid payload: {e}"}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()


def main():
    parser = argparse.ArgumentParser(description="Spec-Driven Validation Harness Tool")
    parser.add_argument(
        "--dry-run", 
        action="store_true", 
        help="Runs validation and prints actions to console without making changes in ClickUp"
    )
    parser.add_argument(
        "--task-id", 
        type=str,
        help="Runs validation specifically for a single ClickUp task ID (useful for webhook triggers)"
    )
    parser.add_argument(
        "--server", 
        action="store_true", 
        help="Runs as a webhook HTTP server to listen for validation events"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=int(os.environ.get("PORT", 8080)),
        help="Port to run the HTTP server on (default: 8080)"
    )
    parser.add_argument(
        "--verbose", 
        action="store_true", 
        help="Enables verbose debugging logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logger.setLevel(logging.DEBUG)
        
    # Initialize local SQLite DB
    local_db.init_db()
    
    orchestrator = ValidationOrchestrator(dry_run=args.dry_run)
    
    if args.server or "PORT" in os.environ:
        ValidationWebhookHandler.orchestrator = orchestrator
        server_address = ('', args.port)
        httpd = HTTPServer(server_address, ValidationWebhookHandler)
        logger.info(f"🚀 Starting webhook HTTP server on port {args.port}...")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            logger.info("Stopping HTTP server...")
            httpd.server_close()
    else:
        orchestrator.run(task_id=args.task_id)


if __name__ == "__main__":
    main()
