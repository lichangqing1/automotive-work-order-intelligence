CREATE OR REPLACE VIEW ota_issue_summary AS
SELECT ota_version,
       COUNT(*) AS total_issues,
       COUNT(*) FILTER (WHERE status IN ('OPEN', 'IN_PROGRESS')) AS open_issues,
       AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600.0) AS avg_resolution_hours
FROM work_orders
WHERE ota_version IS NOT NULL
GROUP BY ota_version;

