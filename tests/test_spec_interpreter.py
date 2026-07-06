import os
import unittest
import tempfile
import json
from src.harness.spec_interpreter import SpecInterpreter

class TestSpecInterpreter(unittest.TestCase):
    def setUp(self):
        # Create a temporary valid specification file
        self.valid_spec_data = {
            "project_name": "Test Validation",
            "version": "1.0.0",
            "bi_view": "bi-performance.BI_QA.VIZ_TEST_VIEW",
            "rubricas_key": [
                {
                    "name": "TEST_RUBRICA",
                    "description": "A test rubrica description",
                    "tabela_amarracao": "test_amarracao",
                    "tolerance": 0.05
                }
            ],
            "validacoes_gerais": [
                {
                    "name": "DEPARA_CHECK",
                    "description": "Check de-para",
                    "type": "depara_check"
                }
            ]
        }
        
        self.temp_spec_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode='w', encoding='utf-8')
        json.dump(self.valid_spec_data, self.temp_spec_file, ensure_ascii=False)
        self.temp_spec_file.close()

    def tearDown(self):
        # Cleanup temp file
        if os.path.exists(self.temp_spec_file.name):
            os.remove(self.temp_spec_file.name)

    def test_load_valid_spec(self):
        """Tests that a valid spec file loads correctly."""
        interpreter = SpecInterpreter(self.temp_spec_file.name)
        self.assertEqual(interpreter.get_bi_view(), "bi-performance.BI_QA.VIZ_TEST_VIEW")
        self.assertEqual(len(interpreter.get_rubricas()), 1)
        self.assertEqual(interpreter.get_rubricas()[0]["name"], "TEST_RUBRICA")

    def test_load_missing_keys(self):
        """Tests that loading a spec with missing required keys raises a ValueError."""
        invalid_spec = {"project_name": "Incomplete"}
        temp_invalid = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode='w')
        json.dump(invalid_spec, temp_invalid)
        temp_invalid.close()
        
        try:
            with self.assertRaises(ValueError):
                SpecInterpreter(temp_invalid.name)
        finally:
            if os.path.exists(temp_invalid.name):
                os.remove(temp_invalid.name)

    def test_invalid_json(self):
        """Tests that providing invalid JSON format raises ValueError."""
        temp_invalid = tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode='w')
        temp_invalid.write("{ invalid json }")
        temp_invalid.close()
        
        try:
            with self.assertRaises(ValueError):
                SpecInterpreter(temp_invalid.name)
        finally:
            if os.path.exists(temp_invalid.name):
                os.remove(temp_invalid.name)

if __name__ == '__main__':
    unittest.main()
