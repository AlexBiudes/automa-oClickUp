# Issues Pendentes: Validações Contábeis & Modelagem de Dados

Este documento registra as inconsistências e limitações identificadas durante a homologação do Harness de Validação Contábil (ClickUp-BigQuery) em relação ao portal BI, que motivaram a transição destas validações para o modo informativo.

Este histórico serve como guia para a equipe de Engenharia de Dados & BI e Arquitetura quando a validação estrita for retomada.

---

## 📋 Lista de Issues Identificadas

### 1. Incompatibilidade de Escopo de Validação (Harness vs Portal)
* **Descrição**: O portal BI valida apenas consistência estrutural do Excel (Saldo Inicial zerado, Saldo Final zerado, Movimentação zerada e Continuidade com o mês anterior). Ele **não** faz batimento das rubricas nem validação conta a conta contra as views de BI no momento da ingestão.
* **Impacto**: Cards marcados como "Processado com sucesso" no portal falham na esteira do ClickUp porque os saldos nas views consolidadas não batem com o balancete bruto de forma síncrona.
* **Ação Futura**: Alinhar se o batimento do BI deve ser impeditivo no ClickUp ou se continuará apenas como alerta de governança.

### 2. Divergências de Sinal (Multiplicadores) na Validação de Contas
* **Descrição**: A view `VIZ_BALANCETE_AUTO_COMPLETA_NEW` aplica multiplicadores (`multiplicador` -1 ou 1) nos saldos para apresentação de relatórios (ex: inverter contas credoras de receita e passivo).
* **Impacto**: O batimento direto conta a conta falhava ao comparar o saldo local original (credor/devedor bruto) com o saldo processado pelo BI, necessitando de uma normalização por valor absoluto (`abs()`) ou mapeamento individualizado de sinal.
* **Ação Futura**: Desenvolver um mapeamento de sinais estruturado baseado na natureza de cada conta para evitar o uso de valor absoluto genérico.

### 3. Defasagem Temporal das Views do BigQuery
* **Descrição**: As views analíticas do BigQuery (`VIZ_BALANCETE_AUTO_BI_NEW`) e as tabelas de amarração possuem um delay de atualização ou dependem de recargas manuais/agendadas.
* **Impacto**: O validador executa imediatamente após o processamento da ingestão. Se as views de BI demorarem para refletir a nova carga do UAID, a validação de rubricas aponta divergências falsas.
* **Ação Futura**: Implementar um tempo de carência ou verificação de sincronismo de partição/sincronização do BigQuery antes de disparar o batimento das rubricas.

### 4. Definição do Plano Padrão (Filtro `grau = 9`)
* **Descrição**: O de-para e agrupamento da view `VIZ_BALANCETE_AUTO_COMPLETA_NEW` junta as contas do `plano_dp` com o `plano_pp` filtrando apenas pelo `grau = 9` (contas analíticas). Contas que não atendem a este grau são omitidas na view de BI, mas eram consideradas pelo Harness original.
* **Ação Futura**: Validar se o filtro `grau = 9` é a regra de negócio definitiva ou se contas de outros graus contábeis podem afetar a consolidação sob certas circunstâncias de ERPs diferentes.
