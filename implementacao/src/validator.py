import fnmatch
from pathlib import Path
from typing import Any, Dict, Tuple
import pandas as pd
import yaml


def load_contract(contract_path: Path) -> dict:
    with contract_path.open("r", encoding="utf-8") as f:
        contract = yaml.safe_load(f)
    if not isinstance(contract, dict):
        raise ValueError("O contrato YAML deve ser um dicionário estruturado.")
    return contract


def check_landing_specs(file_path: Path, contract: dict) -> Tuple[bool, Dict[str, Any]]:
    pattern = contract.get("landing_zone", {}).get("file_pattern", "*")
    if not fnmatch.fnmatchcase(file_path.name, pattern):
        return False, {
            "error": f"Nomenclatura '{file_path.name}' diverge do padrão contratual '{pattern}'."
        }
    return True, {"status": "Padrão físico compatível", "pattern": pattern}


def check_structure(df: pd.DataFrame, file_path: Path, contract: dict) -> Tuple[bool, Dict[str, Any]]:
    name_ok, name_details = check_landing_specs(file_path, contract)
    if not name_ok:
        return False, name_details

    schema_rules = contract["schema_validation"]
    expected_cols = [c["name"] for c in schema_rules["columns"]]
    observed_cols = list(df.columns)

    if schema_rules.get("strict_columns_order", False):
        if observed_cols != expected_cols:
            return False, {
                "error": "Incompatibilidade estrutural ou ordenação incorreta de colunas",
                "expected": expected_cols,
                "observed": observed_cols,
            }
    else:
        if not set(expected_cols).issubset(set(observed_cols)):
            return False, {
                "error": "Colunas obrigatórias ausentes",
                "missing": [c for c in expected_cols if c not in observed_cols],
            }

    for col_def in schema_rules["columns"]:
        col = col_def["name"]
        expected_type = col_def.get("type", "string")
        nullable = col_def.get("nullable", False)

        series = df[col].astype("string")
        null_mask = series.isna() | (series.str.strip() == "")
        null_count = int(null_mask.sum())

        if not nullable and null_count > 0:
            return False, {
                "error": f"Valores nulos não permitidos na coluna {col}",
                "null_count": null_count,
            }

        non_null_series = series[~null_mask].str.strip()
        if non_null_series.empty:
            continue

        if expected_type == "date":
            date_format = col_def.get("format", "YYYY-MM-DD")
            py_format = "%Y-%m-%d" if date_format == "YYYY-MM-DD" else date_format
            parsed_dates = pd.to_datetime(non_null_series, format=py_format, errors="coerce")
            if parsed_dates.isna().any():
                return False, {
                    "error": f"Violação de tipagem date na coluna {col}",
                    "invalid_count": int(parsed_dates.isna().sum()),
                }

        elif expected_type == "decimal":
            cleaned_num = non_null_series.str.replace(",", ".", regex=False)
            parsed_num = pd.to_numeric(cleaned_num, errors="coerce")
            if parsed_num.isna().any():
                return False, {
                    "error": f"Violação de tipagem decimal na coluna {col}",
                    "invalid_count": int(parsed_num.isna().sum()),
                }

        elif expected_type == "integer":
            cleaned_int = non_null_series.str.replace(",", ".", regex=False)
            parsed_num = pd.to_numeric(cleaned_int, errors="coerce")
            invalid_mask = parsed_num.isna() | (parsed_num % 1 != 0)
            invalid_count = int(invalid_mask.sum())
            if invalid_count > 0:
                return False, {
                    "error": f"Violação de tipagem integer na coluna {col}",
                    "invalid_count": invalid_count,
                }

    return True, {"status": "Estrutura e tipagem validadas", "columns_count": len(observed_cols)}


def check_freshness(df: pd.DataFrame, contract: dict) -> Tuple[bool, Dict[str, Any]]:
    if df.empty:
        return False, {"error": "Lote sem registros para avaliação temporal"}

    fresh_rules = contract["freshness_rules"]
    temporal_col = fresh_rules["temporal_field"]
    ref_date_str = fresh_rules["reference_date"]
    max_days = fresh_rules["max_age_days"]
    reject_future = fresh_rules.get("reject_future_dates", True)

    if temporal_col not in df.columns:
        return False, {"error": f"Coluna temporal {temporal_col} inexistente"}

    series = df[temporal_col].astype("string").str.strip()
    if series.isna().any() or (series == "").any():
        return False, {"error": "Registros com carimbo temporal ausente"}

    parsed_dates = pd.to_datetime(series, format="%Y-%m-%d", errors="coerce")
    if parsed_dates.isna().any():
        return False, {"error": "Registros com formato temporal inválido"}

    ref_date = pd.to_datetime(ref_date_str, format="%Y-%m-%d")
    diff_days = (ref_date - parsed_dates).dt.days

    if reject_future and (diff_days < 0).any():
        return False, {
            "error": "Datas futuras rejeitadas contratualmente",
            "min_age_observed": int(diff_days.min()),
        }

    if (diff_days > max_days).any():
        return False, {
            "error": "Defasagem temporal detectada em registros do lote",
            "max_age_observed": int(diff_days.max()),
            "max_allowed": max_days,
        }

    return True, {"status": "Tempestividade plena", "max_age_observed": int(diff_days.max())}


def check_completeness(df: pd.DataFrame, contract: dict) -> Tuple[bool, Dict[str, Any]]:
    comp_rules = contract["completeness_rules"]
    min_threshold = comp_rules["min_records_threshold"]
    observed_rows = len(df)

    if not comp_rules.get("allow_empty_file", False) and observed_rows == 0:
        return False, {"error": "Arquivo vazio rejeitado", "rows": 0}

    if observed_rows < min_threshold:
        return False, {
            "error": "Volume de registros abaixo do limiar contratual",
            "rows": observed_rows,
            "threshold": min_threshold,
        }

    return True, {"status": "Completude atendida", "rows": observed_rows}


def evaluate_asset(file_path: Path, contract_path: Path) -> Dict[str, Any]:
    contract = load_contract(contract_path)
    landing_cfg = contract["landing_zone"]

    try:
        df = pd.read_csv(
            file_path,
            sep=landing_cfg.get("delimiter", ";"),
            encoding=landing_cfg.get("encoding", "utf-8"),
            dtype=str,
        )
    except pd.errors.EmptyDataError:
        return {
            "S": False,
            "T": False,
            "C": False,
            "READY": False,
            "final_state": "BLOCKED",
            "columns_count": 0,
            "records_count": 0,
            "details": {
                "structure": {"error": "Arquivo fisicamente vazio (0 bytes)"},
                "freshness": {"error": "Sem registros temporais para avaliação"},
                "completeness": {"error": "Arquivo vazio rejeitado pelo contrato", "rows": 0},
            },
        }
    except (pd.errors.ParserError, UnicodeDecodeError) as exc:
        error_message = f"CSV ilegível ou malformado: {type(exc).__name__}: {exc}"
        return {
            "S": False,
            "T": False,
            "C": False,
            "READY": False,
            "final_state": "BLOCKED",
            "columns_count": 0,
            "records_count": 0,
            "details": {
                "structure": {"error": error_message},
                "freshness": {"error": "Não foi possível avaliar a dimensão temporal"},
                "completeness": {"error": "Não foi possível avaliar a quantidade de registros"},
            },
        }

    s_ok, s_details = check_structure(df, file_path, contract)
    t_ok, t_details = check_freshness(df, contract)
    c_ok, c_details = check_completeness(df, contract)

    ready = bool(s_ok and t_ok and c_ok)

    return {
        "S": s_ok,
        "T": t_ok,
        "C": c_ok,
        "READY": ready,
        "final_state": "READY" if ready else "BLOCKED",
        "columns_count": len(df.columns),
        "records_count": len(df),
        "details": {
            "structure": s_details,
            "freshness": t_details,
            "completeness": c_details,
        },
    }


if __name__ == "__main__":
    import argparse
    import shutil
    import tempfile

    parser = argparse.ArgumentParser(description="Pré-valida os cenários de um conjunto experimental.")
    parser.add_argument("--dataset-set", required=True, help="ID impresso por src.create_scenarios")
    args = parser.parse_args()
    contract_file = Path("contracts/readiness.yaml")
    scenarios_dir = Path("data/scenarios") / args.dataset_set

    test_cases = [
        ("C1", "C1_conforme.csv", (True, True, True, "READY")),
        ("C2", "C2_estrutura.csv", (False, True, True, "BLOCKED")),
        ("C3", "C3_atualidade.csv", (True, False, True, "BLOCKED")),
        ("C4", "C4_completude.csv", (True, True, False, "BLOCKED")),
    ]

    print("=== Executando Pré-Validação Offline (Sem Acesso ao Banco) ===")
    with tempfile.TemporaryDirectory() as tmp_dir:
        for scenario_id, filename, expected in test_cases:
            temp_path = Path(tmp_dir) / f"inf_diario_fi_preflight_{scenario_id}.csv"
            shutil.copy(scenarios_dir / filename, temp_path)

            res = evaluate_asset(temp_path, contract_file)
            vector = (res["S"], res["T"], res["C"], res["final_state"])
            assert vector == expected, f"Falha em {scenario_id} ({filename}): obtido {vector}, esperado {expected}"
            print(f"[OK] {scenario_id:<3} ({temp_path.name}) -> S={int(res['S'])} T={int(res['T'])} C={int(res['C'])} => {res['final_state']}")

    print("=== Pré-Validação Concluída: Lógica Aprovada ===")
