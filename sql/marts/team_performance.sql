CREATE OR REPLACE VIEW team_resolution_performance AS
SELECT assigned_team,
       COUNT(*) FILTER (WHERE resolved_at IS NOT NULL) AS resolved_orders,
       AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600.0) AS avg_resolution_hours,
       dataset_version_id,
       dataset_version
FROM (
    SELECT w.dataset_version_id,
           dv.version AS dataset_version,
           w.payload ->> 'assigned_team' AS assigned_team,
           CAST(w.payload ->> 'created_at' AS TIMESTAMP) AS created_at,
           CAST(NULLIF(w.payload ->> 'resolved_at', 'None') AS TIMESTAMP) AS resolved_at
    FROM work_order_snapshots AS w
    JOIN dataset_versions AS dv ON dv.dataset_version_id = w.dataset_version_id
) AS versioned_orders
WHERE assigned_team IS NOT NULL
GROUP BY dataset_version_id, dataset_version, assigned_team;
