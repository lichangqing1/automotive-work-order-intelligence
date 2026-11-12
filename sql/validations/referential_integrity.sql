-- Any returned row is a referential-integrity failure.
SELECT w.work_order_id, w.payload ->> 'vehicle_id' AS vehicle_id
FROM work_order_snapshots AS w
LEFT JOIN vehicles AS v ON v.vehicle_id = w.payload ->> 'vehicle_id'
WHERE w.dataset_version_id = :dataset_version_id
  AND v.vehicle_id IS NULL;
