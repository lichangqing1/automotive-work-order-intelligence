CREATE OR REPLACE VIEW ota_issue_summary AS
SELECT ota_version,
       COUNT(*) AS total_issues,
       COUNT(*) FILTER (WHERE status IN ('OPEN', 'IN_PROGRESS')) AS open_issues,
       AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600.0) AS avg_resolution_hours,
       dataset_version_id,
       dataset_version
FROM (
    SELECT w.dataset_version_id,
           dv.version AS dataset_version,
           w.payload ->> 'ota_version' AS ota_version,
           w.payload ->> 'status' AS status,
           CAST(w.payload ->> 'created_at' AS TIMESTAMP) AS created_at,
           CAST(NULLIF(w.payload ->> 'resolved_at', 'None') AS TIMESTAMP) AS resolved_at
    FROM work_order_snapshots AS w
    JOIN dataset_versions AS dv ON dv.dataset_version_id = w.dataset_version_id
) AS versioned_orders
WHERE ota_version IS NOT NULL
GROUP BY dataset_version_id, dataset_version, ota_version;
