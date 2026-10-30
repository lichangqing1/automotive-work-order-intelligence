CREATE OR REPLACE VIEW team_resolution_performance AS
SELECT assigned_team,
       COUNT(*) FILTER (WHERE resolved_at IS NOT NULL) AS resolved_orders,
       AVG(EXTRACT(EPOCH FROM (resolved_at - created_at)) / 3600.0) AS avg_resolution_hours
FROM work_orders
WHERE assigned_team IS NOT NULL
GROUP BY assigned_team;
