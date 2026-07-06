import os
import json
import logging

logger = logging.getLogger("validation_tool")

class SpecInterpreter:
    def __init__(self, spec_path: str):
        self.spec_path = os.path.abspath(spec_path)
        self.spec_data = {}
        self.load_spec()

    def load_spec(self):
        """Loads and parses the specification JSON file."""
        if not os.path.exists(self.spec_path):
            raise FileNotFoundError(f"Specification file not found at '{self.spec_path}'")
        
        try:
            with open(self.spec_path, 'r', encoding='utf-8') as f:
                self.spec_data = json.load(f)
            logger.info(f"Loaded validation spec version {self.spec_data.get('version', 'unknown')}")
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse specification JSON: {e}")
            raise ValueError(f"Invalid JSON format in specification file: {e}")
        
        self.validate_spec_structure()

    def validate_spec_structure(self):
        """Performs a basic structural validation of the spec data."""
        required_keys = ["project_name", "version", "bi_view", "rubricas_key", "validacoes_gerais"]
        for key in required_keys:
            if key not in self.spec_data:
                raise ValueError(f"Missing required key '{key}' in validation specification.")
        
        # Validate rubricas_key list
        rubricas = self.spec_data.get("rubricas_key", [])
        if not isinstance(rubricas, list):
            raise ValueError("Key 'rubricas_key' must be a list.")
        
        for idx, rubrica in enumerate(rubricas):
            r_keys = ["name", "description", "tabela_amarracao", "tolerance"]
            for r_key in r_keys:
                if r_key not in rubrica:
                    raise ValueError(f"Rubrica at index {idx} is missing required field '{r_key}'.")
            
            # Tolerance should be float or int
            if not isinstance(rubrica["tolerance"], (int, float)):
                raise ValueError(f"Tolerance for rubrica '{rubrica.get('name')}' must be a number.")

    def get_rubricas(self) -> list:
        """Returns the list of rubricas defined in the spec."""
        return self.spec_data.get("rubricas_key", [])

    def get_bi_view(self) -> str:
        """Returns the bi view name defined in the spec."""
        return self.spec_data.get("bi_view", "bi-performance.BI_QA.VIZ_BALANCETE_AUTO_BI_NEW")

    def get_validacoes_gerais(self) -> list:
        """Returns general validation rules."""
        return self.spec_data.get("validacoes_gerais", [])
