# ClickUp-BQ Validation Harness (Spec-Driven Development)

Este projeto implementa um **Test Harness de Validação Contábil** integrado entre o ClickUp e o BigQuery, estruturado sob o conceito de **Spec-Driven Development (SDD)**. O validador assegura a qualidade dos dados do balancete importado e das rubricas de BI no BigQuery antes que os cards avancem no Kanban operacional.

---

## 🛠️ Nova Estrutura do Projeto

O projeto foi reestruturado de forma modular e escalável:
* **`specs/`**: Contém o arquivo `validation_spec.json` com a especificação declarativa de rubricas (fácil de expandir via Pull Request).
* **`src/`**: Módulos core em Python.
  * `config.py`: Gestão de configurações e credenciais.
  * `connectors/`: Clientes para BigQuery e ClickUp.
  * `harness/`: Interpretador de especificações, motor de asserções de rubricas e gerador de relatórios contábeis.
  * `validators/`: Check de De-Para analítico pendente (`plano_dp`).
* **`tests/`**: Testes unitários com mocks para validação em pipelines de CI.
* **`.github/workflows/`**: Integração contínua (CI) via GitHub Actions.
* **`.harness/`**: Definição do pipeline do Harness CI/CD para deploy no GCP Cloud Run.

---

## ⚙️ Como Funciona a Validação Contábil (Rubricas)

O validador não checa apenas os saldos individuais do balancete, mas a **composição das rubricas contábeis (ex: BL_ATCIR_Estoques, BL_PASSCIR_Fornecedores)** que alimentam os dashboards no Power BI:

1. **Obtenção do Saldo da View do BI:** O Harness consulta na view consolidada (`VIZ_BALANCETE_AUTO_BI_NEW`) o saldo calculado para a rubrica daquele cliente no período.
2. **Cálculo da Soma Contábil do Cliente:** O Harness busca todas as contas do cliente no balancete (`BALANCETE_ERP`) mapeadas no `plano_dp` para contas padrão que pertencem à rubrica contábil, aplicando o multiplicador de sinal correspondente de cada conta.
3. **Asserção de Diferença:** O motor de asserção compara os dois valores contra a tolerância definida (ex: R$ 0,05). Se a divergência for maior, a rubrica falha e o relatório detalha a divergência e cada conta associada.
4. **Validação de De-Para:** Verifica se existem contas analíticas ativas no balancete importado que não foram mapeadas na tabela `plano_dp`, listando as pendentes.

---

## 🚀 Como Usar e Executar

### Pré-requisitos
* **Python 3.11+**
* Instale as dependências:
  ```bash
  pip install -r requirements.txt
  ```

### Executar Testes Unitários (CI)
Para executar a suíte de testes unitários locais com mocks:
```bash
python -m unittest discover -s tests
```

### Executar a Validação Contábil (Modo CLI)
Para rodar a validação das tarefas pendentes no ClickUp em modo seguro (sem comentar ou alterar status no Kanban):
```bash
python -m src.main --dry-run
```

Para rodar de forma operacional gravando os resultados e atualizando os status dos cards:
```bash
python -m src.main
```

Para validar um card específico do ClickUp (útil para triggers instantâneos):
```bash
python -m src.main --task-id <id_do_card>
```

### Executar como Servidor HTTP (Webhook / Cloud Run)
O validador possui um servidor HTTP nativo integrado. Para iniciá-lo como um microserviço escutando webhooks do n8n/ClickUp:
```bash
python -m src.main --server --port 8080
```
Envie requisições POST para `/validate` com o payload:
```json
{
  "task_id": "id_do_card_aqui",
  "dry_run": false
}
```

---

## 🐳 Docker e Docker Compose

Para subir a infraestrutura completa do n8n integrada com o validador localmente:
```bash
docker-compose up --build
```
Isso iniciará o contêiner `clickup-bq-validator` na mesma rede interna do n8n, expondo a porta `8080` no host. O n8n poderá invocar a validação internamente via HTTP chamando `http://validator:8080/validate`.
