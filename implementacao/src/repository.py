from contextlib import closing
import json
import os
from typing import Any, Dict, Optional
from dotenv import load_dotenv
import psycopg2

load_dotenv()

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "readiness_tcc"),
    "user": os.getenv("DB_USER", "tcc_user"),
    "password": os.getenv("DB_PASS", "sua_senha_local"),
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "5432")),
}

VALID_TRANSITIONS = {
    (None, "INGESTED"),
    ("INGESTED", "VALIDATING"),
    ("VALIDATING", "READY"),
    ("VALIDATING", "BLOCKED"),
}


class InvalidStateTransitionError(ValueError):
    """Lançada quando a transição viola a máquina de estados finitos."""
    pass


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def validate_transition_rule(previous_state: Optional[str], new_state: str) -> None:
    if (previous_state, new_state) not in VALID_TRANSITIONS:
        raise InvalidStateTransitionError(
            f"Transição teórica ilegal: {previous_state} -> {new_state}"
        )


def register_admission(
    asset_id: str,
    execution_id: str,
    batch_id: str,
    scenario_id: str,
    file_name: str,
    storage_path: str,
) -> None:
    validate_transition_rule(None, "INGESTED")

    query_asset = """
        INSERT INTO tb_ativos_ingestao 
        (asset_id, execution_id, batch_id, scenario_id, file_name, storage_path, current_state)
        VALUES (%s, %s, %s, %s, %s, %s, 'INGESTED');
    """
    query_history = """
        INSERT INTO tb_historico_estados 
        (execution_id, batch_id, previous_state, new_state, justification_message)
        VALUES (%s, %s, NULL, 'INGESTED', 'Ativo admitido fisicamente na Landing Zone.');
    """
    with closing(get_connection()) as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query_asset, (asset_id, execution_id, batch_id, scenario_id, file_name, storage_path))
                cur.execute(query_history, (execution_id, batch_id))


def register_transition_to_validating(execution_id: str, batch_id: str) -> None:
    validate_transition_rule("INGESTED", "VALIDATING")

    query_update = """
        UPDATE tb_ativos_ingestao
        SET current_state = 'VALIDATING'
        WHERE execution_id = %s
          AND batch_id = %s
          AND current_state = 'INGESTED';
    """
    query_history = """
        INSERT INTO tb_historico_estados 
        (execution_id, batch_id, previous_state, new_state, justification_message)
        VALUES (%s, %s, 'INGESTED', 'VALIDATING', 'Início da verificação contra o contrato YAML.');
    """
    with closing(get_connection()) as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query_update, (execution_id, batch_id))
                if cur.rowcount != 1:
                    raise InvalidStateTransitionError(
                        f"Transição rejeitada: ativo {execution_id} não estava em INGESTED no banco."
                    )
                cur.execute(query_history, (execution_id, batch_id))


def register_terminal_decision(
    execution_id: str,
    batch_id: str,
    final_state: str,
    justification: str,
    s_val: bool,
    t_val: bool,
    c_val: bool,
    cols_count: int,
    rows_count: int,
    details: Dict[str, Any],
) -> None:
    validate_transition_rule("VALIDATING", final_state)

    query_update = """
        UPDATE tb_ativos_ingestao 
        SET current_state = %s 
        WHERE execution_id = %s
          AND batch_id = %s
          AND current_state = 'VALIDATING';
    """
    query_validation = """
        INSERT INTO tb_validacoes_contrato 
        (execution_id, batch_id, dim_structure_s, dim_freshness_t, dim_completeness_c, 
         ready_result, observed_columns_count, observed_records_count, details_json)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s);
    """
    query_history = """
        INSERT INTO tb_historico_estados 
        (execution_id, batch_id, previous_state, new_state, justification_message)
        VALUES (%s, %s, 'VALIDATING', %s, %s);
    """

    with closing(get_connection()) as conn:
        with conn:
            with conn.cursor() as cur:
                cur.execute(query_update, (final_state, execution_id, batch_id))
                if cur.rowcount != 1:
                    raise InvalidStateTransitionError(
                        f"Transição terminal rejeitada: ativo {execution_id} não estava em VALIDATING."
                    )

                cur.execute(
                    query_validation,
                    (
                        execution_id,
                        batch_id,
                        s_val,
                        t_val,
                        c_val,
                        (final_state == "READY"),
                        cols_count,
                        rows_count,
                        json.dumps(details),
                    ),
                )
                cur.execute(query_history, (execution_id, batch_id, final_state, justification))
