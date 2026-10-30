-- Any returned row is a referential-integrity failure.
SELECT w.work_order_id, w.vehicle_id
FROM work_orders AS w
LEFT JOIN vehicles AS v ON v.vehicle_id = w.vehicle_id
WHERE v.vehicle_id IS NULL;

