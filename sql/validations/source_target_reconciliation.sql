SELECT
    dv.row_count - ir.rejected_rows AS expected_clean_count,
    (SELECT COUNT(*) FROM work_orders) AS actual_clean_count
FROM dataset_versions AS dv
JOIN ingestion_runs AS ir ON ir.dataset_version_id = dv.dataset_version_id
WHERE dv.version = :dataset_version
ORDER BY ir.started_at DESC
LIMIT 1;

