import os
from google.cloud import bigquery

def main():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "gcp_key.json"
    client = bigquery.Client()
    
    query = """
    SELECT view_definition 
    FROM `bi-performance.BI_PROD.INFORMATION_SCHEMA.VIEWS` 
    WHERE table_name = 'VIZ_VALIDACAO_BALANCETE_DEPARA'
    """
    try:
        job = client.query(query)
        result = list(job.result())
        if result:
            print("SQL definition of VIZ_VALIDACAO_BALANCETE_DEPARA:")
            print(result[0].view_definition)
        else:
            print("View VIZ_VALIDACAO_BALANCETE_DEPARA not found in INFORMATION_SCHEMA.VIEWS.")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
