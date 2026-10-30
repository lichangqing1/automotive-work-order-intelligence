SELECT
    dv.row_count AS expected_clean_count,
    COUNT(wos.snapshot_id) AS actual_clean_count
FROM dataset_versions AS dv
LEFT JOIN work_order_snapshots AS wos ON wos.dataset_version_id = dv.dataset_version_id
WHERE dv.version = :dataset_version
GROUP BY dv.dataset_version_id, dv.row_count;
