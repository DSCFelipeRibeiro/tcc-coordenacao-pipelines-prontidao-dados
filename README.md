# Materiais do TCC

Este repositório reúne as figuras, o código e os arquivos do experimento. O projeto LaTeX e o PDF completo do TCC não estão incluídos.

## Pastas

- `figuras_figma/`: contém os arquivos SVG editáveis dos seis diagramas externos usados no TCC. Os PDFs correspondentes ficam apenas na cópia local. A Figura 4.1 foi feita em TikZ no LaTeX e não tem um arquivo separado nesta pasta.
- `implementacao/`: contém o código Python, o contrato YAML, os arquivos SQL, os dados e os resultados do experimento.

## Dados e experimento

O experimento usa o arquivo mensal `inf_diario_fi_202507.csv`, da CVM, incluído em `implementacao/data/raw/`. O gerador confere a integridade do arquivo antes de processá-lo. Os passos para preparar o ambiente e executar os scripts estão em [`implementacao/COMANDOS.md`](implementacao/COMANDOS.md).

A bateria final apresentada no TCC foi executada em 13/10/2026. Seus arquivos de resultado estão em `implementacao/results/`: C1 foi classificado como `READY`, e C2, C3 e C4 como `BLOCKED`. Os artefatos da execução de 12/10 também foram mantidos porque aparecem na comparação de hashes descrita no trabalho.

O arquivo de snapshot do PostgreSQL contém resultados de consultas; não é uma cópia completa do banco.

## Sobre o protótipo

O programa lê arquivos locais, aplica as regras do contrato YAML e registra validações e estados no PostgreSQL. `READY` e `BLOCKED` representam decisões lógicas: o protótipo não aciona tarefas consumidoras nem se integra a um orquestrador.

O `.gitignore` exclui arquivos locais de configuração e caches. Os dados e resultados descritos acima estão versionados; credenciais locais não foram incluídas.
