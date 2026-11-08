from datetime import datetime
import hashlib
import json
from pathlib import Path
import uuid
import pandas as pd
import yaml

RAW_FILE = Path("data/raw/inf_diario_fi_202507.csv")
BASE_ROOT = Path("data/base")
SCENARIO_ROOT = Path("data/scenarios")
RESULTS_DIR = Path("results")

REFERENCE_COMPETENCE = "2025-07-31"
EXPECTED_RAW_ROWS = 579610
EXPECTED_BASE_ROWS = 25144
EXPECTED_RAW_SHA256 = "dae4d7c2a7a7cd7d39a1a76c7bc27942cb999f34afd00066683823c4cf0e79e0"
REFERENCE_DATE = "2025-08-01"
SOURCE_URL = "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_202507.zip"
SOURCE_INDEX_LAST_MODIFIED = "2026-06-27 06:19"  # horário exibido no diretório oficial; fuso não informado
OBSOLETE_COMPETENCE = "2025-06-02"
REMOVED_COLUMN = "VL_PATRIM_LIQ"
TRUNCATED_ROWS = 500


def compute_sha256(file_path: Path) -> str:
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def save_csv(df: pd.DataFrame, target: Path) -> None:
    if target.exists():
        raise FileExistsError(f"Artefato já existe; não será sobrescrito: {target}")
    df.to_csv(target, sep=";", index=False, encoding="utf-8")
    print(f"Gerado: {target.name:<22} | Linhas: {len(df):<6} | Colunas: {len(df.columns)}")


def main() -> None:
    if not RAW_FILE.exists():
        raise FileNotFoundError(f"Arquivo bruto ausente: {RAW_FILE}")

    contract_path = Path("contracts/readiness.yaml")
    contract = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
    if contract["freshness_rules"]["reference_date"] != REFERENCE_DATE:
        raise ValueError("A data de referência do contrato diverge do protocolo 202507.")

    sha256_hash = compute_sha256(RAW_FILE)
    if sha256_hash != EXPECTED_RAW_SHA256:
        raise ValueError(
            f"SHA-256 divergente para o CSV bruto: {sha256_hash}; esperado {EXPECTED_RAW_SHA256}."
        )

    df_raw = pd.read_csv(RAW_FILE, sep=";", dtype=str, encoding="utf-8-sig")

    if len(df_raw) != EXPECTED_RAW_ROWS:
        raise ValueError(f"Contagem mensal divergente: {len(df_raw)} registros; esperados {EXPECTED_RAW_ROWS}.")

    if "DT_COMPTC" not in df_raw.columns:
        raise ValueError("Coluna obrigatória DT_COMPTC ausente no arquivo bruto.")

    base = df_raw.loc[df_raw["DT_COMPTC"].str.strip() == REFERENCE_COMPETENCE].copy()
    if len(base) != EXPECTED_BASE_ROWS:
        raise ValueError(
            f"Contagem divergente para {REFERENCE_COMPETENCE}: "
            f"{len(base)} registros obtidos, esperados {EXPECTED_BASE_ROWS}. "
            "Confira a versão do arquivo original e a data da coleta."
        )

    dataset_set_id = f"202507_{datetime.now().astimezone().strftime('%Y%m%d_%H%M%S_%f')}_{uuid.uuid4().hex[:6]}"
    base_dir = BASE_ROOT / dataset_set_id
    scenario_dir = SCENARIO_ROOT / dataset_set_id
    base_dir.mkdir(parents=True, exist_ok=False)
    scenario_dir.mkdir(parents=True, exist_ok=False)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    base_path = base_dir / "base_2025-07-31.csv"
    scenario_paths = {
        "C1": scenario_dir / "C1_conforme.csv",
        "C2": scenario_dir / "C2_estrutura.csv",
        "C3": scenario_dir / "C3_atualidade.csv",
        "C4": scenario_dir / "C4_completude.csv",
    }

    save_csv(base, base_path)

    # C1: Conformidade Plena
    save_csv(base.copy(), scenario_paths["C1"])

    # C2: Violação Estrutural
    c2 = base.drop(columns=[REMOVED_COLUMN])
    save_csv(c2, scenario_paths["C2"])

    # C3: Violação Temporal
    c3 = base.copy()
    c3["DT_COMPTC"] = OBSOLETE_COMPETENCE
    save_csv(c3, scenario_paths["C3"])

    # C4: Violação de Completude
    c4 = base.head(TRUNCATED_ROWS).copy()
    save_csv(c4, scenario_paths["C4"])

    local_mtime = datetime.fromtimestamp(RAW_FILE.stat().st_mtime).astimezone().isoformat()
    provenance_data = {
        "dataset_set_id": dataset_set_id,
        "raw_file_name": RAW_FILE.name,
        "source_url": SOURCE_URL,
        "source_index_last_modified": SOURCE_INDEX_LAST_MODIFIED,
        "source_index_timezone": None,
        "local_file_last_write_time": local_mtime,
        "acquisition_timestamp": None,
        "acquisition_timestamp_note": "Não há evidência disponível da data de obtenção da cópia local.",
        "sha256": sha256_hash,
        "processing_timestamp": datetime.now().astimezone().isoformat(),
        "total_raw_rows": len(df_raw),
        "total_raw_columns": len(df_raw.columns),
        "raw_columns": list(df_raw.columns),
        "reference_competence": REFERENCE_COMPETENCE,
        "base_rows_count": len(base),
        "base_file_name": base_path.name,
        "base_sha256": compute_sha256(base_path),
        "reference_date": REFERENCE_DATE,
        "contract_file": str(contract_path),
        "contract_sha256": compute_sha256(contract_path),
        "scenario_artifacts": {
            scenario_id: {
                "file_name": path.name,
                "rows": len(pd.read_csv(path, sep=";", dtype=str, encoding="utf-8-sig")),
                "sha256": compute_sha256(path),
                "transformation": {
                    "C1": "Sem alteração da base de 2025-07-31.",
                    "C2": f"Remoção da coluna {REMOVED_COLUMN}.",
                    "C3": f"Substituição de DT_COMPTC por {OBSOLETE_COMPETENCE}.",
                    "C4": f"Seleção das primeiras {TRUNCATED_ROWS} linhas, preservando cabeçalho, esquema e competência.",
                }[scenario_id],
            }
            for scenario_id, path in scenario_paths.items()
        },
    }

    provenance_path = RESULTS_DIR / f"provenance_{dataset_set_id}.json"
    with provenance_path.open("x", encoding="utf-8") as pf:
        json.dump(provenance_data, pf, indent=2)

    print(f"Proveniência registrada: SHA-256 = {sha256_hash}")
    print(f"DATASET_SET_ID={dataset_set_id}")
    print(f"Lote-base: {base_path}")
    print(f"Cenários: {scenario_dir}")
    print(f"Proveniência: {provenance_path}")


if __name__ == "__main__":
    main()
