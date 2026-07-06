import os
from google.cloud import bigquery

def main():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "gcp_key.json"
    client = bigquery.Client()
    
    print("--- Checking file types in BALANCETES_PROCESSADOS ---")
    # Let's see some file names from url_arquivo
    query = """
    SELECT url_arquivo, uaid, msg_erro
    FROM `bi-performance.BI_PROD.BALANCETES_PROCESSADOS`
    ORDER BY data_criacao DESC
    LIMIT 20
    """
    try:
        job = client.query(query)
        for row in job:
            url = row[0] or ""
            filename = url.split('/')[-1] if '/' in url else url
            print(f"UAID: {row[1]} | File: {filename:<60} | Error: {str(row[2])[:30]}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
