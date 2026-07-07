import unittest
from unittest.mock import MagicMock
from src.harness.assertion_engine import AssertionEngine
from src.harness.spec_interpreter import SpecInterpreter

class TestAssertionEngine(unittest.TestCase):
    def setUp(self):
        # Mock BigQueryClient
        self.bq_mock = MagicMock()
        
        # Mock SpecInterpreter
        self.spec_mock = MagicMock()
        self.spec_mock.get_bi_view.return_value = "bi-performance.BI_QA.VIZ_TEST"
        self.spec_mock.get_rubricas.return_value = [
            {
                "name": "BL_ATCIR_Estoques",
                "description": "Test rubrica",
                "tabela_amarracao": "plano_amarracao_bp_ativo",
                "tolerance": 0.05
            }
        ]

    def test_assertion_pass(self):
        """Tests that a rubrica validation passes if difference is within tolerance."""
        # Query results
        self.bq_mock.get_rubrica_bi_value.return_value = 100.00
        self.bq_mock.get_rubrica_composition_from_balancete.return_value = [
            {"conta_origem": "110401", "descricao_origem": "Estoque", "conta_padrao": "114010001", "saldo_atual": 100.00}
        ]
        
        engine = AssertionEngine(self.bq_mock, self.spec_mock)
        res = engine.validate_rubricas("test-uaid", "test-cnpj", "2026-02")
        
        self.assertTrue(res["success"])
        self.assertEqual(len(res["assertions"]), 1)
        self.assertTrue(res["assertions"][0]["passed"])
        self.assertEqual(res["assertions"][0]["valor_bi"], 100.00)
        self.assertEqual(res["assertions"][0]["valor_balancete"], 100.00)
        self.assertEqual(res["assertions"][0]["diferenca"], 0.0)

    def test_assertion_fail(self):
        """Tests that a rubrica validation fails if difference exceeds tolerance."""
        # Query results: BI is 120, but Balancete is 100 (diff is 20 > tolerance 0.05)
        self.bq_mock.get_rubrica_bi_value.return_value = 120.00
        self.bq_mock.get_rubrica_composition_from_balancete.return_value = [
            {"conta_origem": "110401", "descricao_origem": "Estoque", "conta_padrao": "114010001", "saldo_atual": 100.00}
        ]
        
        engine = AssertionEngine(self.bq_mock, self.spec_mock)
        res = engine.validate_rubricas("test-uaid", "test-cnpj", "2026-02")
        
        self.assertFalse(res["success"])
        self.assertEqual(len(res["assertions"]), 1)
        self.assertFalse(res["assertions"][0]["passed"])
        self.assertEqual(res["assertions"][0]["valor_bi"], 120.00)
        self.assertEqual(res["assertions"][0]["valor_balancete"], 100.00)
        self.assertEqual(res["assertions"][0]["diferenca"], 20.0)

    def test_validate_conta_a_conta(self):
        """Tests that account-by-account validation correctly handles DRE (movimentacao) and signs."""
        # BI account balances (with sign multipliers)
        self.bq_mock.get_bi_accounts_balances.return_value = {
            "110401": 100.00,  # BS: matches local saldo_atual
            "310101": -50.00,  # DRE: matches local absolute movimentacao
        }
        
        # Local mapped account balances (raw from BALANCETE_ERP)
        self.bq_mock.get_balancete_mapped_accounts_balances.return_value = [
            {
                "conta": "110401",
                "descricao": "Estoque",
                "saldo_atual": 100.00,
                "movimentacao": 0.00,
                "conta_para": "114010001"
            },
            {
                "conta": "310101",
                "descricao": "Receita de Vendas",
                "saldo_atual": 0.00,
                "movimentacao": 50.00,
                "conta_para": "311010001"
            }
        ]
        
        engine = AssertionEngine(self.bq_mock, self.spec_mock)
        res = engine.validate_conta_a_conta("test-uaid", "test-cnpj", "2026-02")
        
        self.assertTrue(res["success"])
        self.assertEqual(res["passed_count"], 2)
        self.assertEqual(len(res["divergences"]), 0)

if __name__ == '__main__':
    unittest.main()
