-- sql/schema.sql
CREATE TABLE IF NOT EXISTS tb_ativos_ingestao (
    asset_id VARCHAR(64) PRIMARY KEY,
    execution_id VARCHAR(64) NOT NULL UNIQUE,
    batch_id VARCHAR(64) NOT NULL,
    scenario_id VARCHAR(10) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    storage_path VARCHAR(512) NOT NULL,
    ingestion_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    current_state VARCHAR(20) NOT NULL
        CHECK (current_state IN ('INGESTED', 'VALIDATING', 'READY', 'BLOCKED')),
    CONSTRAINT uq_ativos_execution_batch UNIQUE (execution_id, batch_id)
);

CREATE TABLE IF NOT EXISTS tb_validacoes_contrato (
    validation_id SERIAL PRIMARY KEY,
    execution_id VARCHAR(64) NOT NULL,
    batch_id VARCHAR(64) NOT NULL,
    dim_structure_s BOOLEAN NOT NULL,
    dim_freshness_t BOOLEAN NOT NULL,
    dim_completeness_c BOOLEAN NOT NULL,
    ready_result BOOLEAN NOT NULL,
    observed_columns_count INT NOT NULL,
    observed_records_count INT NOT NULL,
    details_json JSONB NOT NULL,
    validation_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_validacao_execucao UNIQUE (execution_id, batch_id),
    CONSTRAINT ck_ready_result CHECK (ready_result = (dim_structure_s AND dim_freshness_t AND dim_completeness_c)),
    CONSTRAINT fk_validacoes_ativo FOREIGN KEY (execution_id, batch_id)
        REFERENCES tb_ativos_ingestao (execution_id, batch_id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS tb_historico_estados (
    history_id SERIAL PRIMARY KEY,
    execution_id VARCHAR(64) NOT NULL,
    batch_id VARCHAR(64) NOT NULL,
    previous_state VARCHAR(20),
    new_state VARCHAR(20) NOT NULL
        CHECK (new_state IN ('INGESTED', 'VALIDATING', 'READY', 'BLOCKED')),
    transition_timestamp TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP,
    justification_message TEXT NOT NULL,
    CONSTRAINT fk_historico_ativo FOREIGN KEY (execution_id, batch_id)
        REFERENCES tb_ativos_ingestao (execution_id, batch_id) ON DELETE RESTRICT
);
