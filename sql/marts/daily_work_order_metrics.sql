CREATE OR REPLACE VIEW daily_work_order_metrics AS
SELECT CAST(created_at AS DATE) AS metric_date,
       COUNT(*) AS total_work_orders,
       COUNT(*) FILTER (WHERE status IN ('OPEN', 'IN_PROGRESS')) AS open_backlog,
       AVG(CASE WHEN resolved_at > created_at + sla_hours * INTERVAL '1 hour' THEN 1.0 ELSE 0.0 END) AS sla_breach_rate,
       dataset_version_id,
       dataset_version
FROM (
    SELECT w.dataset_version_id,
           dv.version AS dataset_version,
           CAST(w.payload ->> 'created_at' AS TIMESTAMP) AS created_at,
           CAST(NULLIF(w.payload ->> 'resolved_at', 'None') AS TIMESTAMP) AS resolved_at,
           CAST(w.payload ->> 'sla_hours' AS INTEGER) AS sla_hours,
           w.payload ->> 'status' AS status
    FROM work_order_snapshots AS w
    JOIN dataset_versions AS dv ON dv.dataset_version_id = w.dataset_version_id
) AS versioned_orders
GROUP BY dataset_version_id, dataset_version, CAST(created_at AS DATE);
