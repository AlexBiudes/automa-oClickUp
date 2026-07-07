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
        conta_a_conta_results: dict = None,
        balancete_totals: dict = None
    ) -> str:
        """
        Generates a premium markdown formatted report for ClickUp task comments.
        """
        lines = []
        
        # Check for informational warnings
        failed_rubricas = [r for r in rubricas_results.get("assertions", []) if not r.get("passed")]
        has_bi_warnings = len(failed_rubricas) > 0 or (conta_a_conta_results and not conta_a_conta_results.get("success"))

        if success:
            lines.append("🟢 **Validação Contábil Concluída com Sucesso!**\n")
            lines.append(f"O balancete da empresa **{empresa}** (CNPJ: `{cnpj}` | Período: `{periodo}`) passou nos testes de integridade fundamentais (De-Para e Equação Contábil).\n")
            
            lines.append("### 📈 Resumo da Validação:")
            if balancete_totals:
                lines.append(f"• **Contas Processadas:** `{balancete_totals.get('total_rows', 0)}` contas contábeis.")
                lines.append(f"• **Equação Contábil:** Débitos e Créditos batem perfeitamente! ({format_currency(balancete_totals.get('sum_debito', 0.0))})")
            
            lines.append("• **Plano De-Para:** 100% mapeado (zero contas analíticas pendentes).")
            
            if not has_bi_warnings:
                lines.append("• **Rubricas de BI (Composição):** Todas as rubricas testadas batem perfeitamente com os saldos das views contábeis do BigQuery.")
                lines.append("• **Saldos Conta a Conta:** Todos os saldos individuais de contas contábeis analíticas conferem com o BI!\n")
            else:
                lines.append("• **Divergências de BI:** Foram identificados alertas informativos de divergência nas views do BI contábil (ver seção de alertas abaixo).\n")
                
                lines.append("---")
                lines.append("### ⚠️ Alertas / Divergências de BI (Informativo - Não Bloqueante)")
                lines.append("Os apontamentos abaixo não impediram a aprovação do card, mas indicam defasagem ou desalinhamento na modelagem do BI:\n")
                
                if failed_rubricas:
                    lines.append("**Divergências de Composição por Rubrica:**")
                    for r in failed_rubricas:
                        lines.append(f"• **Rubrica `{r['rubrica']}` ({r['descricao']}):** View do BI = `{format_currency(r['valor_bi'])}` | Balancete = `{format_currency(r['valor_balancete'])}` | Dif = `{format_currency(r['diferenca'])}` (tolerância: {format_currency(r['tolerance'])})")
                    lines.append("")
                    
                if conta_a_conta_results and not conta_a_conta_results.get("success"):
                    divergences = conta_a_conta_results.get("divergences", [])
                    lines.append("**Divergências de Saldos Conta a Conta:**")
                    for d in divergences[:10]:
                        lines.append(f"• **Conta `{d['conta']}` ({d['descricao']}):** BI = `{format_currency(d['valor_bi'])}` | Balancete = `{format_currency(d['valor_local'])}` | Dif = `{format_currency(d['diferenca'])}`")
                    if len(divergences) > 10:
                        lines.append(f"• *... e mais {len(divergences) - 10} contas com divergências.*")
                    lines.append("")
            
            lines.append("📂 *ID do Processamento (UAID):* `" + uaid + "`")
            lines.append("\nCard movido automaticamente para a coluna **`validação coordenador`**.")
        else:
            lines.append("🔴 **Divergências Encontradas na Validação (Harness Fail):**\n")
            lines.append(f"O processamento do balancete para **{empresa}** (CNPJ: `{cnpj}` | Período: `{periodo}`) apresentou inconsistências críticas que impedem a aprovação automática.\n")
            
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
            
            # 2. Informational BI Warnings listed even on failure
            if has_bi_warnings:
                lines.append("---")
                lines.append("### ⚠️ Alertas / Divergências de BI (Informativo - Não Bloqueante)")
                lines.append("Além dos erros críticos acima, foram encontrados desalinhamentos no BI (não impedem aprovação por si só):\n")
                
                if failed_rubricas:
                    lines.append("**Divergências de Composição por Rubrica:**")
                    for r in failed_rubricas:
                        lines.append(f"• **Rubrica `{r['rubrica']}` ({r['descricao']}):** View do BI = `{format_currency(r['valor_bi'])}` | Balancete = `{format_currency(r['valor_balancete'])}` | Dif = `{format_currency(r['diferenca'])}`")
                    lines.append("")
                    
                if conta_a_conta_results and not conta_a_conta_results.get("success"):
                    divergences = conta_a_conta_results.get("divergences", [])
                    lines.append("**Divergências de Saldos Conta a Conta:**")
                    for d in divergences[:10]:
                        lines.append(f"• **Conta `{d['conta']}` ({d['descricao']}):** BI = `{format_currency(d['valor_bi'])}` | Balancete = `{format_currency(d['valor_local'])}` | Dif = `{format_currency(d['diferenca'])}`")
                    if len(divergences) > 10:
                        lines.append(f"• *... e mais {len(divergences) - 10} contas com divergências.*")
                    lines.append("")
                
            lines.append("📂 *ID do Processamento (UAID):* `" + uaid + "`")
            lines.append("\nCard movido automaticamente para a coluna **`conferir dados`**.")
            
        return "\n".join(lines)
