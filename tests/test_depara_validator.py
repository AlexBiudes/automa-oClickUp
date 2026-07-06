import unittest
from unittest.mock import MagicMock
from src.validators.depara_validator import DeparaValidator

class TestDeparaValidator(unittest.TestCase):
    def setUp(self):
        self.bq_mock = MagicMock()

    def test_depara_all_mapped(self):
        """Tests that validator passes if there are no unmapped analytical accounts."""
        self.bq_mock.get_balancete_accounts.return_value = ["1", "1.1", "1.1.01", "1.1.01.001"]
        self.bq_mock.get_unmapped_balancete_accounts.return_value = []
        
        validator = DeparaValidator(self.bq_mock)
        res = validator.validate_depara("test-uaid")
        
        self.assertTrue(res["passed"])
        self.assertEqual(len(res["unmapped_accounts"]), 0)

    def test_depara_ignores_synthetic_unmapped(self):
        """Tests that unmapped synthetic group accounts (headers) are ignored."""
        self.bq_mock.get_balancete_accounts.return_value = ["1", "1.1", "1.1.01", "1.1.01.001"]
        # '1' is synthetic prefix of '1.1', which is prefix of '1.1.01' etc.
        # Suppose '1.1' is in the unmapped list from BQ
        self.bq_mock.get_unmapped_balancete_accounts.return_value = [
            {"conta": "1.1", "descricao": "ATIVO CIRCULANTE"}
        ]
        
        validator = DeparaValidator(self.bq_mock)
        res = validator.validate_depara("test-uaid")
        
        # It should ignore '1.1' because it is a prefix to '1.1.01.001' (synthetic)
        self.assertTrue(res["passed"])
        self.assertEqual(len(res["unmapped_accounts"]), 0)

    def test_depara_detects_analytical_unmapped(self):
        """Tests that unmapped analytical accounts (leaf nodes) are detected."""
        self.bq_mock.get_balancete_accounts.return_value = ["1", "1.1", "1.1.01", "1.1.01.001"]
        # '1.1.01.001' is leaf node (analytical) and it has no de-para
        self.bq_mock.get_unmapped_balancete_accounts.return_value = [
            {"conta": "1.1.01.001", "descricao": "CAIXA GERAL"}
        ]
        
        validator = DeparaValidator(self.bq_mock)
        res = validator.validate_depara("test-uaid")
        
        # It should detect it
        self.assertFalse(res["passed"])
        self.assertEqual(len(res["unmapped_accounts"]), 1)
        self.assertEqual(res["unmapped_accounts"][0]["conta"], "1.1.01.001")

if __name__ == '__main__':
    unittest.main()
