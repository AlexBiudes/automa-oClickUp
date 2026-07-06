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
        if credentials_path and os.path.exists(credentials_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath(credentials_path)
            logger.info(f"Setting GOOGLE_APPLICATION_CREDENTIALS to {os.path.abspath(credentials_path)}")
        
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
        """
        logger.info(f"Detecting report type and row count for UAID {uaid}")
        
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

    def get_unmapped_balancete_accounts(self, uaid: str) -> list:
        """
        Queries BALANCETE_ERP and plano_dp directly to find accounts without De-Para.
        """
        logger.info(f"Querying unmapped accounts for UAID {uaid}")
        query = """
        SELECT DISTINCT b.CONTA as conta, b.DESCRICAO as descricao
        FROM `bi-performance.BI_PROD.BALANCETE_ERP` b
        LEFT JOIN (
            SELECT DISTINCT REPLACE(conta_de, ".0", "") as conta_de, cnpj
            FROM `bi-performance.BI_PROD.plano_dp`
            WHERE conta_de <> "" AND conta_de IS NOT NULL AND LENGTH(conta_para) = 9
        ) dp ON b.CONTA = dp.conta_de AND b.CNPJ = dp.cnpj
        WHERE b.uaid = @uaid AND dp.conta_de IS NULL
        ORDER BY b.CONTA
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("uaid", "STRING", uaid)
            ]
        )
        try:
            query_job = self.client.query(query, job_config=job_config)
            results = list(query_job.result())
            return [{"conta": r.conta, "descricao": r.descricao} for r in results]
        except Exception as e:
            logger.error(f"Error querying unmapped accounts in BigQuery: {e}")
            raise

    def get_rubrica_bi_value(self, cnpj: str, data_base: str, rubrica_name: str, bi_view: str) -> float:
        """
        Queries the consolidator view in BigQuery for the final value of the rubrica.
        """
        logger.info(f"Querying BI value for rubrica '{rubrica_name}' (CNPJ: {cnpj}, Data: {data_base})")
        # Safety check: avoid SQL injection by validating view format
        if not bi_view or not all(c.isalnum() or c in '._-' for c in bi_view):
            raise ValueError(f"Invalid bi_view name: {bi_view}")

        query = f"""
        SELECT SUM(vlr) as val
        FROM `{bi_view}`
        WHERE cnpj = @cnpj AND data = @data_base AND descricao = @rubrica_name
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("cnpj", "STRING", cnpj),
                bigquery.ScalarQueryParameter("data_base", "STRING", data_base),
                bigquery.ScalarQueryParameter("rubrica_name", "STRING", rubrica_name)
            ]
        )
        try:
            query_job = self.client.query(query, job_config=job_config)
            results = list(query_job.result())
            if not results or results[0].val is None:
                return 0.0
            return float(results[0].val)
        except Exception as e:
            logger.error(f"Error querying rubrica BI value: {e}")
            raise

    def get_rubrica_composition_from_balancete(self, uaid: str, rubrica_name: str, tabela_amarracao: str) -> list:
        """
        Queries BALANCETE_ERP, plano_dp, and the specified mapping table to obtain the composition
        of accounts and balances that should go to the rubrica.
        """
        logger.info(f"Querying rubrica composition for '{rubrica_name}' using mapping table '{tabela_amarracao}'")
        # Safety check on table name
        if not tabela_amarracao or not all(c.isalnum() or c in '._-' for c in tabela_amarracao):
            raise ValueError(f"Invalid mapping table name: {tabela_amarracao}")

        query = f"""
        SELECT 
            b.CONTA as conta_origem, 
            b.DESCRICAO as descricao_origem, 
            dp.conta_para as conta_padrao,
            b.SALDO_ATUAL as saldo_atual,
            am.multiplicador as multiplicador
        FROM `bi-performance.BI_PROD.BALANCETE_ERP` b
        JOIN (
            SELECT 
                DISTINCT 
                REPLACE(conta_de, ".0", "") as conta_de, 
                REPLACE(conta_para, ".0", "") as conta_para, 
                cnpj
            FROM `bi-performance.BI_PROD.plano_dp`
            WHERE conta_de <> "" AND conta_de IS NOT NULL AND LENGTH(conta_para) = 9
        ) dp ON b.CONTA = dp.conta_de AND b.CNPJ = dp.cnpj
        JOIN `bi-performance.BI_PROD.{tabela_amarracao}` am 
          ON dp.conta_para LIKE CONCAT(am.amarracao, '%') AND b.CNPJ = am.cnpj
        WHERE b.uaid = @uaid AND am.descricao_banco = @rubrica_name
        ORDER BY b.CONTA
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("uaid", "STRING", uaid),
                bigquery.ScalarQueryParameter("rubrica_name", "STRING", rubrica_name)
            ]
        )
        try:
            query_job = self.client.query(query, job_config=job_config)
            results = list(query_job.result())
            return [
                {
                    "conta_origem": r.conta_origem,
                    "descricao_origem": r.descricao_origem,
                    "conta_padrao": r.conta_padrao,
                    "saldo_atual": float(r.saldo_atual) if r.saldo_atual is not None else 0.0,
                    "multiplicador": int(r.multiplicador) if r.multiplicador is not None else 1
                }
                for r in results
            ]
        except Exception as e:
            logger.error(f"Error querying rubrica composition from balancete: {e}")
            raise
