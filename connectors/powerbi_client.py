import os
import glob
import logging
import requests
import re
import xml.etree.ElementTree as ET

logger = logging.getLogger("validation_tool")

class PowerBIClient:
    def __init__(self):
        self.local_appdata = os.environ.get("LOCALAPPDATA")
        self.workspaces_dir = os.path.join(
            self.local_appdata, "Microsoft", "Power BI Desktop", "AnalysisServicesWorkspaces"
        ) if self.local_appdata else None

    def find_local_instances(self) -> list:
        """
        Scans Power BI Desktop directories to find port numbers of running instances.
        Returns a list of dictionaries with port and workspace name.
        """
        if not self.workspaces_dir or not os.path.exists(self.workspaces_dir):
            logger.info("Power BI Desktop AnalysisServicesWorkspaces directory not found.")
            return []

        instances = []
        # Look for msmdsrv.port.txt files recursively
        port_files = glob.glob(os.path.join(self.workspaces_dir, "**", "msmdsrv.port.txt"), recursive=True)
        
        for port_file in port_files:
            try:
                # Get the workspace folder name (e.g. AnalysisServicesWorkspace_xxx)
                parts = port_file.split(os.sep)
                ws_name = "Unknown"
                for p in parts:
                    if "AnalysisServicesWorkspace" in p:
                        ws_name = p
                        break
                
                with open(port_file, "r", encoding="utf-16le") as f:
                    port_str = f.read().strip()
                
                # Verify port is a number
                if port_str.isdigit():
                    instances.append({
                        "port": int(port_str),
                        "workspace": ws_name,
                        "path": port_file
                    })
            except Exception as e:
                logger.error(f"Error reading port file {port_file}: {e}")

        logger.info(f"Found {len(instances)} running Power BI Desktop instances.")
        return instances

    def query_xmla(self, port: int, dax_or_dmv_query: str) -> str:
        """
        Sends an XMLA execute request to the local Power BI instance using raw SOAP HTTP.
        """
        url = f"http://localhost:{port}/xmla"
        headers = {
            "Content-Type": "text/xml",
            "SOAPAction": 'urn:schemas-microsoft-com:xml-analysis:Execute'
        }
        
        # XMLA SOAP envelope template
        soap_envelope = f"""<?xml version="1.0" encoding="utf-8"?>
<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
  <soap:Body>
    <Execute xmlns="urn:schemas-microsoft-com:xml-analysis">
      <Command>
        <Statement><![CDATA[{dax_or_dmv_query}]]></Statement>
      </Command>
      <Properties>
        <PropertyList>
          <Format>Tabular</Format>
        </PropertyList>
      </Properties>
    </Execute>
  </soap:Body>
</soap:Envelope>"""
        
        response = requests.post(url, data=soap_envelope.encode('utf-8'), headers=headers, timeout=15)
        response.raise_for_status()
        return response.text

    def parse_xmla_tabular_results(self, xml_response: str) -> list:
        """
        Parses the SOAP XML XMLA response into a list of row dictionaries.
        """
        # Register XML namespaces to parse properly
        namespaces = {
            'soap': 'http://schemas.xmlsoap.org/soap/envelope/',
            'xmla': 'urn:schemas-microsoft-com:xml-analysis',
            'row': 'urn:schemas-microsoft-com:xml-analysis:rowset'
        }
        
        try:
            root = ET.fromstring(xml_response)
            rows = root.findall('.//row:row', namespaces)
            
            parsed_rows = []
            for r in rows:
                row_dict = {}
                for child in r:
                    # Strip namespace tag
                    tag_name = child.tag.split('}')[-1]
                    row_dict[tag_name] = child.text
                parsed_rows.append(row_dict)
            return parsed_rows
        except Exception as e:
            logger.error(f"Error parsing XMLA response: {e}")
            return []

    def map_semantic_model_tables(self, port: int) -> list:
        """
        Queries DMVs to get tables and their partitions (M query definitions)
        to identify which BigQuery tables they are mapped to.
        """
        logger.info(f"Mapping semantic model tables from port {port}")
        
        # 1. Get all tables
        tables_query = "SELECT ID, Name, Description FROM $SYSTEM.TMSCHEMA_TABLES"
        xml_tables = self.query_xmla(port, tables_query)
        tables_rows = self.parse_xmla_tabular_results(xml_tables)
        
        # 2. Get partitions (M queries)
        partitions_query = "SELECT TableID, QueryDefinition FROM $SYSTEM.TMSCHEMA_PARTITIONS"
        xml_partitions = self.query_xmla(port, partitions_query)
        partitions_rows = self.parse_xmla_tabular_results(xml_partitions)
        
        # Create partitions map: TableID -> M Query
        partitions_map = {}
        for p in partitions_rows:
            table_id = p.get("TableID")
            query_def = p.get("QueryDefinition")
            if table_id and query_def:
                partitions_map[table_id] = query_def
                
        # Combine
        mappings = []
        for t in tables_rows:
            table_id = t.get("ID")
            name = t.get("Name")
            
            # Skip system/hidden tables if they start with DateTableTemplate or LocalDateTable
            if name.startswith("DateTableTemplate") or name.startswith("LocalDateTable"):
                continue
                
            m_query = partitions_map.get(table_id, "")
            
            # Extract BigQuery tables from M query definition if present
            # Look for patterns like: Schema="BI_PROD", Table="BALANCETE_ERP" or similar
            bq_dataset = None
            bq_table = None
            
            if m_query:
                # regex to search for BigQuery tables in M Query: e.g. [Schema="BI_PROD",Item="BALANCETE_ERP"]
                schema_match = re.search(r'Schema\s*=\s*"([^"]+)"', m_query)
                item_match = re.search(r'Item\s*=\s*"([^"]+)"', m_query)
                if schema_match:
                    bq_dataset = schema_match.group(1)
                if item_match:
                    bq_table = item_match.group(1)
                    
            mappings.append({
                "pbi_table": name,
                "bq_dataset": bq_dataset,
                "bq_table": bq_table,
                "m_query": m_query
            })
            
        return mappings
