# Protótipo de prontidão de dados

Implementação local em Python e PostgreSQL para avaliar a estrutura, a atualidade e o volume de arquivos do Informe Diário da CVM. O protótipo registra a decisão lógica no banco; não aciona uma tarefa consumidora nem integra um orquestrador.

## Experimento documentado

A entrada é `data/raw/inf_diario_fi_202507.csv`. O gerador confere seu SHA-256 antes de processá-la. A base do experimento contém os 25.144 registros com competência `2025-07-31`; a validação usa a data de referência `2025-08-01`.

A bateria final registrada no TCC é:

- Conjunto: `202507_20261013_070842_616498_99181f`
- Lote: `batch_20261013_070936_216632_9c1f`
- Resultado: C1 `READY`; C2, C3 e C4 `BLOCKED`

Os arquivos de proveniência, matriz, manifesto e transcrição do PostgreSQL dessa bateria estão em `results/`. A transcrição registra as consultas feitas no banco; ela não é um dump. A execução de 12/10/2026 é incluída apenas para a comparação de hashes do contrato/cenários e da matriz descrita no capítulo de resultados; a bateria final citada é a de 13/10.

Uma nova execução gera outros identificadores e horários. Para comparar as execuções, confira os hashes dos arquivos e os valores de S, T, C e estado final, não os IDs.

## Reproduzir

Use o PowerShell no Windows. Os pré-requisitos, a preparação do ambiente, a configuração do PostgreSQL e a sequência de comandos estão em [`COMANDOS.md`](COMANDOS.md). As dependências Python estão fixadas em `requirements.txt`.

O arquivo `.env.example` mostra as variáveis necessárias. Copie-o para `.env` e preencha a senha local. Não distribua o `.env`.

## Arquivos principais

- `contracts/readiness.yaml`: contrato usado pelo validador.
- `src/create_scenarios.py`: seleciona a competência e gera C1–C4 e a proveniência.
- `src/validator.py`: calcula as dimensões estrutural, temporal e de completude.
- `src/repository.py`: registra os estados, as validações e o histórico no PostgreSQL.
- `src/run_scenarios.py`: executa a bateria e grava a matriz e o manifesto.
- `sql/schema.sql`: cria as tabelas do protótipo.
- `sql/audit_evidence.sql`: consulta os resultados de um lote.
