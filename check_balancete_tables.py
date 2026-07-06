import os
from google.cloud import bigquery

def main():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "gcp_key.json"
    client = bigquery.Client()
    
    for table_name in ['BALANCETES_PROCESSADOS', 'ESTATISTICAS_PROCESSAMENTO_BALANCETES']:
        print(f"\n======================================")
        print(f"Table: {table_name}")
        print(f"======================================")
        
        query_cols = f"""
        SELECT column_name, data_type 
        FROM `bi-performance.BI_PROD.INFORMATION_SCHEMA.COLUMNS` 
        WHERE table_name = '{table_name}'
        """
        try:
            cols_job = client.query(query_cols)
            for row in cols_job:
                print(f" - {row[0]}: {row[1]}")
                
            query_sample = f"""
            SELECT * 
            FROM `bi-performance.BI_PROD.{table_name}` 
            LIMIT 3
            """
            sample_job = client.query(query_sample)
            sample_rows = list(sample_job.result())
            print(f"\nFound {len(sample_rows)} sample rows:")
            for i, r in enumerate(sample_rows):
                print(f"Row {i}:")
                for key in r.keys():
                    print(f"  {key}: {r[key]}")
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == '__main__':
    main()
