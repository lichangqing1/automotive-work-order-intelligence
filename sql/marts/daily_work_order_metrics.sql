CREATE OR REPLACE VIEW daily_work_order_metrics AS
SELECT CAST(created_at AS DATE) AS metric_date,
       COUNT(*) AS total_work_orders,
       COUNT(*) FILTER (WHERE status IN ('OPEN', 'IN_PROGRESS')) AS open_backlog,
       AVG(CASE WHEN resolved_at > created_at + sla_hours * INTERVAL '1 hour' THEN 1.0 ELSE 0.0 END) AS sla_breach_rate
FROM work_orders
GROUP BY CAST(created_at AS DATE);

