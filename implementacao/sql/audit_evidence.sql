\set ON_ERROR_STOP on
SELECT 
    a.scenario_id,
    a.file_name,
    a.current_state,
    v.dim_structure_s AS s,
    v.dim_freshness_t AS t,
    v.dim_completeness_c AS c,
    v.observed_columns_count AS colunas,
    v.observed_records_count AS registros,
    h.justification_message
FROM tb_ativos_ingestao a
JOIN tb_validacoes_contrato v
  ON a.execution_id = v.execution_id AND a.batch_id = v.batch_id
JOIN tb_historico_estados h
  ON a.execution_id = h.execution_id
 AND a.batch_id = h.batch_id
 AND h.new_state = a.current_state
WHERE a.batch_id = :'batch_id'
ORDER BY a.scenario_id;
