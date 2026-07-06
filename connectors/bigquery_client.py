import os
import logging
from google.cloud import bigquery

logger = logging.getLogger("validation_tool")

class BigQueryClient:
    TABLE_TO_REPORT_TYPE = {
        "BALANCETE_ERP": "Balancete",
        "Relatorio_Custos": "Relatório de custos",
        "Relatorio_Receitas": "Relatório de receitas",
        "Analise_Estoques": "Relatório de estoque",
        "Aging_List_Contas_Receber": "[Aging List] Contas Receber",
        "Aging_List_Contas_Pagar": "[Aging List] Contas Pagar",
        "Aging_List_Adiantamentos_Fornecedores": "[Aging List] Adiantamentos Fornecedores",
        "Aging_List_Adiantamentos_Clientes": "[Aging List] Adiantamentos Clientes"
    }

    def __init__(self, credentials_path: str = None):
        if credentials_path:
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(credentials_path)
        
        self.client = bigquery.Client()
        logger.info(f"BigQuery Client initialized for project: {self.client.project}")

    def get_balancete_processado(self, uaid: str) -> dict:
        """
        Retrieves the processing log for a given UAID.
        Returns None if not found, otherwise a dictionary with metadata.
        """
        logger.info(f"Querying BALANCETES_PROCESSADOS for UAID {uaid}")
        query = """
        SELECT grupo_empresarial, empresa, cnpj, periodos_analise, ingestao_concluida, msg_erro, url_arquivo
        FROM `bi-performance.BI_PROD.BALANCETES_PROCESSADOS`
        WHERE uaid = @uaid
        LIMIT 1
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("uaid", "STRING", uaid)
            ]
        )
        try:
            query_job = self.client.query(query, job_config=job_config)
            results = list(query_job.result())
            if not results:
                return None
            
            row = results[0]
            return {
                "grupo_empresarial": row.grupo_empresarial,
                "empresa": row.empresa,
                "cnpj": row.cnpj,
                "periodos_analise": row.periodos_analise,
                "ingestao_concluida": row.ingestao_concluida,
                "msg_erro": row.msg_erro,
                "url_arquivo": row.url_arquivo
            }
        except Exception as e:
            logger.error(f"Error querying BALANCETES_PROCESSADOS: {e}")
            raise

    def get_balancete_totals(self, uaid: str) -> dict:
        """
        Calculates sums and checks for formula mismatch for a given UAID in BALANCETE_ERP.
        """
        logger.info(f"Querying BALANCETE_ERP totals for UAID {uaid}")
        query = """
        SELECT 
            COUNT(*) as total_rows,
            SUM(SALDO_ANTERIOR) as sum_saldo_anterior,
            SUM(DEBITO) as sum_debito,
            SUM(CREDITO) as sum_credito,
            SUM(MOV_PERIODO) as sum_mov_periodo,
            SUM(SALDO_ATUAL) as sum_saldo_atual,
            COUNTIF(ABS(SALDO_ATUAL - (SALDO_ANTERIOR + MOV_PERIODO)) > 0.01) as mismatch_count
        FROM `bi-performance.BI_PROD.BALANCETE_ERP`
        WHERE uaid = @uaid
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("uaid", "STRING", uaid)
            ]
        )
        try:
            query_job = self.client.query(query, job_config=job_config)
            results = list(query_job.result())
            if not results or results[0].total_rows == 0:
                return None
            
            row = results[0]
            return {
                "total_rows": row.total_rows,
                "sum_saldo_anterior": row.sum_saldo_anterior or 0.0,
                "sum_debito": row.sum_debito or 0.0,
                "sum_credito": row.sum_credito or 0.0,
                "sum_mov_periodo": row.sum_mov_periodo or 0.0,
                "sum_saldo_atual": row.sum_saldo_atual or 0.0,
                "mismatch_count": row.mismatch_count or 0
            }
        except Exception as e:
            logger.error(f"Error querying BALANCETE_ERP: {e}")
            raise

    def get_unmapped_accounts(self, cnpj: str, data_base: str) -> list:
        """
        Queries VIZ_VALIDACAO_BALANCETE_DEPARA view for unmapped accounts.
        """
        logger.info(f"Querying unmapped accounts in VIZ_VALIDACAO_BALANCETE_DEPARA for CNPJ {cnpj} and Month {data_base}")
        query = """
        SELECT conta, descricao
        FROM `bi-performance.BI_PROD.VIZ_VALIDACAO_BALANCETE_DEPARA`
        WHERE cnpj = @cnpj AND data_base = @data_base AND encontrada = FALSE
        ORDER BY conta
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("cnpj", "STRING", cnpj),
                bigquery.ScalarQueryParameter("data_base", "STRING", data_base)
            ]
        )
        try:
            query_job = self.client.query(query, job_config=job_config)
            results = list(query_job.result())
            unmapped = []
            for row in results:
                unmapped.append({
                    "conta": row.conta,
                    "descricao": row.descricao
                })
            return unmapped
        except Exception as e:
            logger.error(f"Error querying VIZ_VALIDACAO_BALANCETE_DEPARA: {e}")
            raise

    def get_balancete_accounts(self, uaid: str) -> list:
        """
        Retrieves all unique account codes present in BALANCETE_ERP for a given UAID.
        """
        logger.info(f"Retrieving all account codes for UAID {uaid}")
        query = """
        SELECT DISTINCT CONTA 
        FROM `bi-performance.BI_PROD.BALANCETE_ERP` 
        WHERE uaid = @uaid
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("uaid", "STRING", uaid)
            ]
        )
        try:
            query_job = self.client.query(query, job_config=job_config)
            results = list(query_job.result())
            return [row.CONTA for row in results if row.CONTA]
        except Exception as e:
            logger.error(f"Error querying distinct accounts in BALANCETE_ERP: {e}")
            raise

    def detect_report_type_and_rows(self, uaid: str) -> dict:
        """
        Queries all tables using UNION ALL to find where the UAID records reside.
        Returns a dict: {"table_name": str, "report_type": str, "row_count": int}
        or None if not found in any table.
        """
        logger.info(f"Detecting report type and row count for UAID {uaid}")
        
        # Build union query to scan all possible tables in one query job
        union_parts = []
        for t in self.TABLE_TO_REPORT_TYPE.keys():
            union_parts.append(f"""
            SELECT '{t}' as table_name, COUNT(*) as row_count 
            FROM `bi-performance.BI_PROD.{t}` 
            WHERE uaid = @uaid
            """)
            
        union_query = "\nUNION ALL\n".join(union_parts)
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("uaid", "STRING", uaid)
            ]
        )
        
        try:
            query_job = self.client.query(union_query, job_config=job_config)
            results = list(query_job.result())
            
            for row in results:
                t_name = row.table_name
                count = row.row_count or 0
                if count > 0:
                    report_type = self.TABLE_TO_REPORT_TYPE.get(t_name, "Desconhecido")
                    return {
                        "table_name": t_name,
                        "report_type": report_type,
                        "row_count": count
                    }
            return None
        except Exception as e:
            logger.error(f"Error in detect_report_type_and_rows: {e}")
            raise
