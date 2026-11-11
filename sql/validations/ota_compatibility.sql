SELECT
    w.work_order_id,
    w.payload ->> 'ota_version' AS ota_version,
    v.hardware_version
FROM work_order_snapshots AS w
JOIN vehicles AS v ON v.vehicle_id = w.payload ->> 'vehicle_id'
LEFT JOIN ota_releases AS o ON o.ota_version = w.payload ->> 'ota_version'
WHERE w.dataset_version_id = :dataset_version_id
  AND w.payload ->> 'service_type' = 'OTA'
  AND (w.payload ->> 'ota_version' IS NULL OR o.ota_version IS NULL);
