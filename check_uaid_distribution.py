import os
from google.cloud import bigquery

def main():
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "gcp_key.json"
    client = bigquery.Client()
    
    # Get latest UAIDs
    query_uaids = """
    SELECT uaid, url_arquivo, empresa
    FROM `bi-performance.BI_PROD.BALANCETES_PROCESSADOS`
    ORDER BY data_criacao DESC
    LIMIT 20
    """
    
    try:
        uaids_job = client.query(query_uaids)
        uaids = list(uaids_job.result())
        
        uaid_list = [row[0] for row in uaids if row[0]]
        if not uaid_list:
            print("No UAIDs found in BALANCETES_PROCESSADOS.")
            return
            
        uaid_placeholders = ", ".join([f"'{u}'" for u in uaid_list])
        
        tables = [
            "BALANCETE_ERP",
            "Aging_List_Adiantamentos_Clientes",
            "Aging_List_Adiantamentos_Fornecedores",
            "Aging_List_Contas_Pagar",
            "Aging_List_Contas_Receber",
            "Analise_Estoques",
            "Relatorio_Custos",
            "Relatorio_Receitas"
        ]
        
        # Build union query
        union_parts = []
        for t in tables:
            union_parts.append(f"""
            SELECT '{t}' as table_name, uaid, COUNT(*) as row_count 
            FROM `bi-performance.BI_PROD.{t}` 
            WHERE uaid IN ({uaid_placeholders}) 
            GROUP BY uaid
            """)
            
        union_query = "\nUNION ALL\n".join(union_parts)
        
        results_job = client.query(union_query)
        results = list(results_job.result())
        
        # Map uaid -> (table_name, row_count)
        uaid_map = {}
        for row in results:
            u = row.uaid
            t = row.table_name
            r = row.row_count
            if u not in uaid_map:
                uaid_map[u] = []
            uaid_map[u].append((t, r))
            
        print(f"{'UAID':<38} | {'File Name':<45} | {'Table where data resides':<40} | {'Row Count':<10}")
        print("-" * 140)
        
        for u_row in uaids:
            uaid = u_row[0]
            url = u_row[1] or ""
            filename = url.split('/')[-1] if '/' in url else url
            
            if uaid in uaid_map:
                for t, count in uaid_map[uaid]:
                    print(f"{uaid:<38} | {filename[:45]:<45} | {t:<40} | {count:<10}")
            else:
                print(f"{uaid:<38} | {filename[:45]:<45} | {'[NOT FOUND IN ANY DATA TABLE]':<40} | {0:<10}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
