import os
from google.cloud import bigquery

def main():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "gcp_key.json"
    client = bigquery.Client()
    
    # Check for unmapped accounts in the view
    query = """
    SELECT cnpj, data_base, COUNT(*) as total_accounts, 
           COUNTIF(NOT encontrada) as unmapped_accounts
    FROM `bi-performance.BI_PROD.VIZ_VALIDACAO_BALANCETE_DEPARA`
    GROUP BY cnpj, data_base
    ORDER BY unmapped_accounts DESC
    LIMIT 10
    """
    try:
        job = client.query(query)
        print("Unmapped accounts by CNPJ and month in VIZ_VALIDACAO_BALANCETE_DEPARA:")
        for row in job:
            print(f"CNPJ: {row[0]} | Month: {row[1]} | Total: {row[2]} | Unmapped: {row[3]}")
    except Exception as e:
        print(f"❌ Error querying view: {e}")

if __name__ == '__main__':
    main()
