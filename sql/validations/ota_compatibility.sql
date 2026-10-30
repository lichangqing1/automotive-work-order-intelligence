SELECT w.work_order_id, w.ota_version, v.hardware_version
FROM work_orders AS w
JOIN vehicles AS v ON v.vehicle_id = w.vehicle_id
LEFT JOIN ota_releases AS o ON o.ota_version = w.ota_version
WHERE w.service_type = 'OTA'
  AND (w.ota_version IS NULL OR o.ota_version IS NULL);

