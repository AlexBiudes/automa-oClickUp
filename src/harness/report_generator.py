import logging

logger = logging.getLogger("validation_tool")

def format_currency(val: float) -> str:
    is_neg = val < 0
    abs_val = abs(val)
    parts = f"{abs_val:.2f}".split('.')
    integer_part = parts[0]
    decimal_part = parts[1]
    
    reversed_int = integer_part[::-1]
    groups = [reversed_int[i:i+3] for i in range(0, len(reversed_int), 3)]
    integer_formatted = ".".join(groups)[::-1]
    
    if is_neg:
        return f"R$ -{integer_formatted},{decimal_part}"
    else:
        return f"R$ {integer_formatted},{decimal_part}"

class ReportGenerator:
    @staticmethod
    def generate_clickup_comment(
        uaid: str,
        cnpj: str,
        empresa: str,
        periodo: str,
        success: bool,
        depara_results: dict,
        rubricas_results: dict,
        balancete_totals: dict = None
    ) -> str:
        """
        Generates a premium markdown formatted report for ClickUp task comments.
        """
        lines = []
        
        if success:
            lines.append("🟢 **Validação Contábil Concluída com Sucesso!**\n")
            lines.append(f"O balancete da empresa **{empresa}** (CNPJ: `{cnpj}` | Período: `{periodo}`) passou em todos os testes do Harness de Validação.\n")
            
            lines.append("### 📈 Resumo da Validação:")
            if balancete_totals:
                lines.append(f"• **Contas Processadas:** `{balancete_totals.get('total_rows', 0)}` contas contábeis.")
                lines.append(f"• **Equação Contábil:** Débitos e Créditos batem perfeitamente! ({format_currency(balancete_totals.get('sum_debito', 0.0))})")
            
            lines.append("• **Plano De-Para:** 100% mapeado (zero contas analíticas pendentes).")
            lines.append("• **Rubricas de BI (Composição):** Todas as rubricas testadas batem perfeitamente com os saldos das views contábeis do BigQuery.\n")
            
            lines.append("Card movido automaticamente para a coluna **`validação coordenador`**.")
        else:
            lines.append("🔴 **Divergências Encontradas na Validação (Harness Fail):**\n")
            lines.append(f"O processamento do balancete para **{empresa}** (CNPJ: `{cnpj}` | Período: `{periodo}`) apresentou inconsistências que precisam de correção manual.\n")
            
            # 1. De-Para Errors
            if not depara_results.get("passed"):
                unmapped = depara_results.get("unmapped_accounts", [])
                lines.append("### 🔍 1. Mapeamento De-Para Pendente")
                lines.append("Foram encontradas contas contábeis analíticas no balancete que não possuem um mapeamento cadastrado na tabela `plano_dp`.\n")
                
                # Table format for unmapped accounts
                lines.append("| Conta Origem | Descrição da Conta |")
                lines.append("| :--- | :--- |")
                for acc in unmapped[:15]:
                    lines.append(f"| `{acc['conta']}` | {acc['descricao']} |")
                
                if len(unmapped) > 15:
                    lines.append(f"| *...* | *e mais {len(unmapped) - 15} contas.* |")
                
                lines.append("\n👉 **Como corrigir:** Acesse o cadastro de De-Para no sistema e associe as contas analíticas acima a uma conta contábil padrão (com 9 dígitos) no `plano_dp`.\n")
            
            # 2. Rubrica Composition Errors
            failed_rubricas = [r for r in rubricas_results.get("assertions", []) if not r.get("passed")]
            if failed_rubricas:
                lines.append("### ⚖️ 2. Divergências de Composição de Saldo (Rubricas)")
                lines.append("O saldo calculado para as rubricas abaixo na view de BI difere da soma física das contas correspondentes no balancete do cliente:\n")
                
                for r in failed_rubricas:
                    lines.append(f"#### ⚠️ Rubrica: `{r['rubrica']}` ({r['descricao']})")
                    if "error" in r:
                        lines.append(f"❌ *Erro na execução da validação:* `{r['error']}`")
                        continue
                        
                    lines.append(f"• **Saldo na View do BI:** `{format_currency(r['valor_bi'])}`")
                    lines.append(f"• **Soma das Contas do Balancete:** `{format_currency(r['valor_balancete'])}`")
                    lines.append(f"• **Divergência:** `{format_currency(r['diferenca'])}` (Tolerância permitida: {format_currency(r['tolerance'])})")
                    
                    # Show composition table
                    lines.append("\n**Contas do Cliente Amarradas a esta Rubrica no Balancete:**")
                    lines.append("| Conta Origem | Descrição da Conta | Conta Padrão | Saldo Atual |")
                    lines.append("| :--- | :--- | :--- | :--- |")
                    for c in r["composicao"]:
                        lines.append(f"| `{c['conta_origem']}` | {c['descricao_origem']} | `{c['conta_padrao']}` | {format_currency(c['saldo_atual'])} |")
                    if not r["composicao"]:
                        lines.append("| *Nenhuma* | *Nenhuma conta amarrada encontrada* | *N/A* | *R$ 0,00* |")
                    lines.append("")
                
                lines.append("👉 **Como corrigir:** Verifique se as contas contábeis do cliente foram mapeadas para as contas padrão corretas no De-Para. Se o mapeamento estiver correto, verifique a integridade e os saldos das contas no arquivo de balancete original.\n")
                
            lines.append("📂 *ID do Processamento (UAID):* `" + uaid + "`")
            lines.append("\nCard movido automaticamente para a coluna **`verificar dados`**.")
            
        return "\n".join(lines)
