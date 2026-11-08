# Comandos de preparação e execução no Windows

Use o **PowerShell** a partir desta pasta (`implementacao`). Estes passos usam Python e PostgreSQL instalados no Windows; WSL2 não é necessário.

## Verificar pré-requisitos

```powershell
py -3.11 --version
psql --version
```

Se `psql` não for reconhecido, adicione a pasta `bin` da instalação do PostgreSQL ao `PATH` do Windows ou chame `psql.exe` pelo caminho completo. A instalação padrão costuma ficar sob `C:\Program Files\PostgreSQL\<versão>\bin`.

Confira o serviço do PostgreSQL:

```powershell
Get-Service -Name 'postgresql*'
```

Se estiver parado, abra o PowerShell como administrador e inicie o serviço listado:

```powershell
Start-Service -Name 'postgresql-x64-<versão>'
```

Substitua o nome pelo que `Get-Service` mostrar. Confirme que está escutando na porta configurada em `.env`, normalmente 5432:

```powershell
pg_isready -h localhost -p 5432
```

## Preparar o Python e as configurações

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
if (-not (Test-Path .env)) {
    Copy-Item .env.example .env
} else {
    Write-Host ".env já existe; mantendo as configurações atuais."
}
```

Se a ativação do ambiente virtual for bloqueada pela política do PowerShell, permita scripts apenas nesta sessão e tente novamente:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Configure as credenciais locais em `.env`; mantenha esse arquivo fora do repositório.

## Usar o banco existente

Os comandos abaixo pressupõem que o banco local `readiness_tcc` e o usuário `tcc_user` já existem no PostgreSQL. `sql/schema.sql` cria apenas as tabelas; não cria o banco nem o usuário. Se as tabelas ainda não existirem, aplique o esquema:

```powershell
psql -h localhost -p 5432 -U tcc_user -d readiness_tcc -W -f sql/schema.sql
```

O comando executa `CREATE TABLE IF NOT EXISTS` e não apaga dados existentes. Cada nova execução acrescenta um lote, sem substituir os artefatos já arquivados.

## Preparar e executar os cenários

O CSV bruto usado neste ensaio é `data\raw\inf_diario_fi_202507.csv`. A cópia local deve permanecer intacta. O gerador cria um conjunto identificado por execução em `data\base` e `data\scenarios`, além de um arquivo de proveniência exclusivo em `results`; ele não substitui artefatos anteriores.

```powershell
python -m src.create_scenarios
```

Copie o valor `DATASET_SET_ID` impresso pelo primeiro comando e use-o nas etapas seguintes:

```powershell
$datasetSet = "202507_<id_impresso>"
python -m src.validator --dataset-set $datasetSet
python -m src.run_scenarios --dataset-set $datasetSet
```

Registre o `batch_id` impresso pelo último comando e confira `results\matriz_<batch_id>.csv`, `results\manifest_<batch_id>.json` e `results\provenance_<datasetSet>.json`.

## Consultar evidências

Substitua `SEU_BATCH_ID` pelo identificador impresso na execução:

```powershell
psql -h localhost -p 5432 -U tcc_user -d readiness_tcc -W -v "batch_id=SEU_BATCH_ID" -f sql/audit_evidence.sql
```

A consulta mostra estados finais, valores S/T/C, contagens e justificativas terminais. Para documentar toda a sequência de estados, consulte também `tb_historico_estados` em ordem cronológica.
