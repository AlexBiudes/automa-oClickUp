import re
import logging
import json
from connectors.clickup_client import ClickUpClient
from connectors.bigquery_client import BigQueryClient

logger = logging.getLogger("validation_tool")

def format_currency(val: float) -> str:
    is_neg = val < 0
    abs_val = abs(val)
    parts = f"{abs_val:.2f}".split('.')
    integer_part = parts[0]
    decimal_part = parts[1]
    
    reversed_int = integer_part[::-1]
    groups = [reversed_int[i:i+3] for i in range(0, len(reversed_int), 3)]
    integer_formatted = ".".join(groups)[::-1]
    
    if is_neg:
        return f"R$ -{integer_formatted},{decimal_part}"
    else:
        return f"R$ {integer_formatted},{decimal_part}"

def parse_and_format_error(msg_erro: str) -> str:
    if not msg_erro or not msg_erro.strip():
        return "Erro desconhecido durante o processamento do balancete."

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
                
                # Montar o comentário final
                comment_lines = [
                    "❌ **Falha na Validação do Balancete (Ingestão):**\n"
                    "O processamento do arquivo de balancete falhou devido a inconsistências nos dados.\n",
                    "### 🔍 O que deu errado:",
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

class DataValidator:
    def __init__(self, clickup_client: ClickUpClient, bigquery_client: BigQueryClient):
        self.clickup_client = clickup_client
        self.bigquery_client = bigquery_client
        # Regex to extract UAID from task name
        self.uaid_regex = re.compile(r"UAID[:\-\s]*([a-fA-F0-9\-]{36})", re.IGNORECASE)

    def extract_uaid(self, task_name: str) -> str:
        """Extracts the UAID (UUID4 format) from the ClickUp task name."""
        match = self.uaid_regex.search(task_name)
        if match:
            return match.group(1).strip()
        
        # Fallback to general uuid regex if "UAID:" literal is missing but a UUID exists
        uuid_fallback = re.search(r"([a-fA-F0-9\-]{36})", task_name)
        if uuid_fallback:
            return uuid_fallback.group(1).strip()
            
        return None

    def clean_account(self, acc: str) -> str:
        """Removes periods, hyphens, and spaces from an account code for prefix matching."""
        return re.sub(r"[.\-\s]", "", str(acc))

    def validate_card(self, task: dict) -> dict:
        """
        Validates a single ClickUp task card based on whether it is a Balancete or an Auxiliary Report.
        """
        task_id = task.get("id")
        task_name = task.get("name")
        logger.info(f"Validating task '{task_name}' (ID: {task_id})")

        uaid = self.extract_uaid(task_name)
        if not uaid:
            comment = (
                "⚠️ **Erro de Identificação:**\n"
                "Não foi possível encontrar um UAID válido no título desta tarefa.\n\n"
                "**Como corrigir:**\n"
                "Renomeie o card inserindo o UAID no final. Exemplo: `Empresa | CNPJ | UAID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`."
            )
            return {
                "task_id": task_id,
                "task_name": task_name,
                "uaid": None,
                "success": False,
                "next_status": "conferir dados",
                "comment": comment
            }

        # 1. Check ingestion log in BALANCETES_PROCESSADOS
        try:
            log_data = self.bigquery_client.get_balancete_processado(uaid)
        except Exception as e:
            return {
                "task_id": task_id,
                "task_name": task_name,
                "uaid": uaid,
                "success": False,
                "next_status": "conferir dados",
                "comment": f"❌ **Erro de Sistema:** Falha ao conectar ao BigQuery: {e}"
            }

        if not log_data:
            comment = (
                f"⚠️ **Erro de Ingestão:**\n"
                f"O UAID `{uaid}` não foi encontrado na tabela de controle (`BALANCETES_PROCESSADOS`).\n\n"
                f"Isso significa que a planilha correspondente a este card ainda não foi processada pelo sistema de ingestão."
            )
            return {
                "task_id": task_id,
                "task_name": task_name,
                "uaid": uaid,
                "success": False,
                "next_status": "conferir dados",
                "comment": comment
            }

        ingestao_concluida = log_data.get("ingestao_concluida")
        msg_erro = log_data.get("msg_erro")
        cnpj = log_data.get("cnpj")
        empresa = log_data.get("empresa")
        periodos_analise = log_data.get("periodos_analise")

        # Ingestion status code: 2 is success, 3 is error, other values mean processing
        if ingestao_concluida == 3 or (msg_erro and msg_erro.strip()):
            comment = parse_and_format_error(msg_erro)
            return {
                "task_id": task_id,
                "task_name": task_name,
                "uaid": uaid,
                "success": False,
                "next_status": "conferir dados",
                "comment": comment
            }
        elif ingestao_concluida != 2:
            comment = (
                f"⏳ **Aguardando Ingestão:**\n"
                f"O arquivo com UAID `{uaid}` está na fila de processamento (Status: {ingestao_concluida}).\n"
                f"Por favor, execute o validador novamente após a ingestão ser concluída."
            )
            return {
                "task_id": task_id,
                "task_name": task_name,
                "uaid": uaid,
                "success": False,
                "next_status": "para começar",
                "comment": comment
            }

        # 2. Detect report type based on where the UAID rows reside in BigQuery
        try:
            report_info = self.bigquery_client.detect_report_type_and_rows(uaid)
        except Exception as e:
            return {
                "task_id": task_id,
                "task_name": task_name,
                "uaid": uaid,
                "success": False,
                "next_status": "conferir dados",
                "comment": f"❌ **Erro de Sistema:** Falha ao detectar tipo de relatório no BigQuery: {e}"
            }

        if not report_info:
            comment = (
                f"⚠️ **Divergência de Dados:**\n"
                f"O log de processamento para o UAID `{uaid}` foi marcado como concluído, "
                f"mas nenhum data correspondente foi encontrado em nenhuma das tabelas de balancete ou relatórios auxiliares."
            )
            return {
                "task_id": task_id,
                "task_name": task_name,
                "uaid": uaid,
                "success": False,
                "next_status": "conferir dados",
                "comment": comment
            }

        table_name = report_info["table_name"]
        report_type = report_info["report_type"]
        row_count = report_info["row_count"]

        logger.info(f"Detected report type: '{report_type}' (Table: {table_name}, Rows: {row_count})")

        # 3. Apply validation logic based on report type
        if table_name == "BALANCETE_ERP":
            # --- TRIAL BALANCE (BALANCETE) VALIDATION ---
            try:
                totals = self.bigquery_client.get_balancete_totals(uaid)
            except Exception as e:
                return {
                    "task_id": task_id,
                    "task_name": task_name,
                    "uaid": uaid,
                    "success": False,
                    "next_status": "conferir dados",
                    "comment": f"❌ **Erro de Sistema:** Falha ao ler dados do balancete no BigQuery: {e}"
                }

            if not totals:
                comment = (
                    f"⚠️ **Erro de Dados:**\n"
                    f"Nenhum registro de conta foi encontrado na tabela `BALANCETE_ERP` para o UAID `{uaid}`."
                )
                return {
                    "task_id": task_id,
                    "task_name": task_name,
                    "uaid": uaid,
                    "success": False,
                    "next_status": "conferir dados",
                    "comment": comment
                }

            errors = []
            warnings = []

            # Check debits vs credits (tolerance: 0.05)
            deb_cred_diff = abs(totals["sum_debito"] - totals["sum_credito"])
            if deb_cred_diff > 0.05:
                errors.append(
                    f"• **Balancete Desbalanceado:** A soma de Débitos (`R$ {totals['sum_debito']:,.2f}`) difere da soma de Créditos (`R$ {totals['sum_credito']:,.2f}`). Diferença: `R$ {deb_cred_diff:,.2f}`."
                )

            # Check formula: Saldo Atual = Saldo Anterior + Movimento
            if totals["mismatch_count"] > 0:
                warnings.append(
                    f"• **Inconsistência de Fórmula:** Foram detectadas `{totals['mismatch_count']}` contas onde o `SALDO_ATUAL` não bate com `SALDO_ANTERIOR + MOV_PERIODO`."
                )

            # Check for unmapped accounts in De-Para view
            try:
                unmapped_raw = self.bigquery_client.get_unmapped_accounts(cnpj, periodos_analise)
                all_accounts = self.bigquery_client.get_balancete_accounts(uaid)
            except Exception as e:
                return {
                    "task_id": task_id,
                    "task_name": task_name,
                    "uaid": uaid,
                    "success": False,
                    "next_status": "conferir dados",
                    "comment": f"❌ **Erro de Sistema:** Falha ao consultar contas no BigQuery: {e}"
                }

            # Filter out synthetic accounts from the unmapped accounts list using prefix-based check
            clean_all_codes = {self.clean_account(a) for a in all_accounts}
            analytical_unmapped = []
            
            for acc in unmapped_raw:
                c_code = self.clean_account(acc["conta"])
                # An account is synthetic if it serves as a prefix for any other longer account in the trial balance
                is_synthetic = False
                for other in clean_all_codes:
                    if other.startswith(c_code) and len(other) > len(c_code):
                        is_synthetic = True
                        break
                if not is_synthetic:
                    analytical_unmapped.append(acc)

            if analytical_unmapped:
                unmapped_list_str = "\n".join([f"  - `{acc['conta']}`: {acc['descricao']}" for acc in analytical_unmapped[:10]])
                if len(analytical_unmapped) > 10:
                    unmapped_list_str += f"\n  - *... e mais {len(analytical_unmapped) - 10} contas.*"
                errors.append(
                    f"• **Mapeamento De-Para Faltante:** Foram encontradas `{len(analytical_unmapped)}` contas analíticas no balancete sem De-Para configurado (contas sintéticas foram ignoradas):\n{unmapped_list_str}"
                )

            # Determine final status
            if errors:
                success = False
                next_status = "conferir dados"
                comment = (
                    f"❌ **Divergências Encontradas na Validação (Balancete):**\n"
                    f"O balancete com UAID `{uaid}` (Empresa CNPJ: `{cnpj}` | Período: `{periodos_analise}`) apresentou inconsistências:\n\n"
                    + "\n\n".join(errors)
                )
                if warnings:
                    comment += "\n\n" + "\n\n".join(warnings)
            else:
                success = True
                next_status = "validação coordenador"
                comment = (
                    f"✅ **Validação Concluída com Sucesso!**\n"
                    f"O **Balancete** com UAID `{uaid}` foi verificado com sucesso:\n"
                    f"• CNPJ/Empresa: `{cnpj}` ({empresa})\n"
                    f"• Período: `{periodos_analise}`\n"
                    f"• Total de Contas Processadas: `{totals['total_rows']}`\n"
                    f"• Total Débito/Crédito: `R$ {totals['sum_debito']:,.2f}` (Débitos e Créditos Batem!)\n"
                    f"• Contas Analíticas sem De-Para: `0` (Mapeamento Completo! Contas sintéticas ignoradas)\n\n"
                    f"Card movido automaticamente para a coluna **`validação coordenador`**."
                )
                if warnings:
                    comment += "\n\n⚠️ **Avisos:**\n" + "\n\n".join(warnings)

        else:
            # --- AUXILIARY REPORT VALIDATION ---
            # Auxiliary reports are considered valid if they processed successfully and have rows in the target table.
            success = True
            next_status = "validação coordenador"
            comment = (
                f"✅ **Validação Concluída com Sucesso!**\n"
                f"O relatório **{report_type}** com UAID `{uaid}` foi verificado com sucesso:\n"
                f"• CNPJ/Empresa: `{cnpj}` ({empresa})\n"
                f"• Período: `{periodos_analise}`\n"
                f"• Total de Registros Ingeridos: `{row_count}` na tabela `{table_name}`.\n\n"
                f"Card movido automaticamente para a coluna **`validação coordenador`**."
            )

        return {
            "task_id": task_id,
            "task_name": task_name,
            "uaid": uaid,
            "success": success,
            "next_status": next_status,
            "comment": comment
        }
