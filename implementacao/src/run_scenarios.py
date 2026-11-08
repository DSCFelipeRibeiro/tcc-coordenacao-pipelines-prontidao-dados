from datetime import datetime
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import uuid
import pandas as pd
from src.repository import (
    register_admission,
    register_terminal_decision,
    register_transition_to_validating,
)
from src.validator import evaluate_asset

CONTRACT_FILE = Path("contracts/readiness.yaml")
LANDING_BASE_DIR = Path("data/landing")
RESULTS_DIR = Path("results")

SCENARIOS = [
    ("C1", "C1_conforme.csv", "Conforme Pleno"),
    ("C2", "C2_estrutura.csv", "Violação Estrutural"),
    ("C3", "C3_atualidade.csv", "Violação Temporal"),
    ("C4", "C4_completude.csv", "Violação de Completude"),
]


def run_preflight_checks(scenarios_dir: Path) -> None:
    expected_matrix = {
        "C1": (True, True, True, "READY"),
        "C2": (False, True, True, "BLOCKED"),
        "C3": (True, False, True, "BLOCKED"),
        "C4": (True, True, False, "BLOCKED"),
    }
    with tempfile.TemporaryDirectory(prefix="readiness_preflight_") as temp_dir:
        for scenario_id, filename, _ in SCENARIOS:
            temp_name = Path(temp_dir) / f"inf_diario_fi_preflight_{scenario_id}.csv"
            shutil.copy(scenarios_dir / filename, temp_name)
            res = evaluate_asset(temp_name, CONTRACT_FILE)
            observed = (res["S"], res["T"], res["C"], res["final_state"])
            if observed != expected_matrix[scenario_id]:
                raise RuntimeError(
                    f"Pré-checagem falhou em {scenario_id}. Esperado: {expected_matrix[scenario_id]}, Observado: {observed}"
                )


def execute_experimental_batch(dataset_set_id: str) -> None:
    scenarios_dir = Path("data/scenarios") / dataset_set_id
    if not scenarios_dir.is_dir():
        raise FileNotFoundError(f"Conjunto de cenários não encontrado: {scenarios_dir}")

    print("Executando pré-checagem lógica...")
    run_preflight_checks(scenarios_dir)
    print("Pré-checagem aprovada.\n")

    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    batch_id = f"batch_{timestamp_str}_{uuid.uuid4().hex[:4]}"

    batch_landing_dir = LANDING_BASE_DIR / batch_id
    batch_landing_dir.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    summary = []
    print(f"--- Bateria Experimental Iniciada: {batch_id} ---")

    for scenario_id, source_filename, condition in SCENARIOS:
        target_filename = f"inf_diario_fi_{scenario_id}.csv"
        src_path = scenarios_dir / source_filename
        dest_path = batch_landing_dir / target_filename

        shutil.copy(src_path, dest_path)

        exec_id = f"exec_{scenario_id}_{uuid.uuid4().hex[:6]}"
        asset_id = f"asset_{uuid.uuid4().hex[:6]}"

        # 1. Admissão: None -> INGESTED
        register_admission(
            asset_id=asset_id,
            execution_id=exec_id,
            batch_id=batch_id,
            scenario_id=scenario_id,
            file_name=target_filename,
            storage_path=str(dest_path),
        )

        # 2. Transição: INGESTED -> VALIDATING
        register_transition_to_validating(execution_id=exec_id, batch_id=batch_id)

        # 3. Confrontação conjuntiva contra o contrato
        eval_res = evaluate_asset(dest_path, CONTRACT_FILE)
        final_state = eval_res["final_state"]
        downstream = "DOWNSTREAM_AUTHORIZED" if final_state == "READY" else "DOWNSTREAM_BLOCKED"

        justification = (
            "Todas as dimensões contratuais atendidas."
            if final_state == "READY"
            else f"Reprovação em dimensão obrigatória: S={int(eval_res['S'])}, T={int(eval_res['T'])}, C={int(eval_res['C'])}."
        )

        # 4. Transição terminal atômica: VALIDATING -> READY ou BLOCKED
        register_terminal_decision(
            execution_id=exec_id,
            batch_id=batch_id,
            final_state=final_state,
            justification=justification,
            s_val=eval_res["S"],
            t_val=eval_res["T"],
            c_val=eval_res["C"],
            cols_count=eval_res["columns_count"],
            rows_count=eval_res["records_count"],
            details=eval_res["details"],
        )

        summary.append(
            {
                "batch_id": batch_id,
                "execution_id": exec_id,
                "cenario": scenario_id,
                "condicao": condition,
                "S": int(eval_res["S"]),
                "T": int(eval_res["T"]),
                "C": int(eval_res["C"]),
                "READY": int(eval_res["READY"]),
                "estado_obtido": final_state,
                "acao_downstream": downstream,
            }
        )

        print(f"[{scenario_id}] S={int(eval_res['S'])} T={int(eval_res['T'])} C={int(eval_res['C'])} -> {final_state} ({downstream})")

    df_out = pd.DataFrame(summary)
    df_out.to_csv(RESULTS_DIR / f"matriz_{batch_id}.csv", index=False)
    manifest = {
        "batch_id": batch_id,
        "dataset_set_id": dataset_set_id,
        "processing_timestamp": datetime.now().astimezone().isoformat(),
        "contract_file": str(CONTRACT_FILE),
        "contract_sha256": hashlib.sha256(CONTRACT_FILE.read_bytes()).hexdigest(),
        "scenario_files": {
            scenario_id: {
                "file_name": filename,
                "sha256": hashlib.sha256((scenarios_dir / filename).read_bytes()).hexdigest(),
            }
            for scenario_id, filename, _ in SCENARIOS
        },
        "results": summary,
    }
    with (RESULTS_DIR / f"manifest_{batch_id}.json").open("x", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print("\n--- Evidências Empíricas Coletadas ---")
    print(df_out[["cenario", "S", "T", "C", "READY", "estado_obtido", "acao_downstream"]].to_string(index=False))
    print(f"\nID da Bateria registrado no PostgreSQL: {batch_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Executa C1-C4 do conjunto experimental indicado.")
    parser.add_argument("--dataset-set", required=True, help="ID impresso por src.create_scenarios")
    args = parser.parse_args()
    execute_experimental_batch(args.dataset_set)
