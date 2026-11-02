-- Useful queries for the presentation (Section 8)

-- 1) Each driver's earnings per month (business information from Section 3)
SELECT d.driver_id,
       d.full_name,
       strftime('%Y-%m', p.paid_at) AS month,
       COUNT(DISTINCT r.ride_id)    AS rides,
       SUM(p.amount)                AS earnings_kzt
FROM payments p
JOIN rides   r ON r.ride_id   = p.ride_id
JOIN drivers d ON d.driver_id = r.driver_id
WHERE p.payment_status = 'paid'
GROUP BY d.driver_id, month
ORDER BY month DESC, earnings_kzt DESC;

-- 2) All rides of one passenger with car and driver
SELECT r.ride_id, r.start_time, r.pickup_address, r.dropoff_address, r.status, r.price,
       d.full_name AS driver, c.model, c.plate_number
FROM rides r
JOIN drivers d ON d.driver_id = r.driver_id
JOIN cars    c ON c.car_id    = r.car_id
WHERE r.passenger_id = 1
ORDER BY r.start_time DESC;

-- 3) Completed rides with no successful payment (a business problem)
SELECT r.ride_id, r.price
FROM rides r
WHERE r.status = 'completed'
  AND NOT EXISTS (SELECT 1 FROM payments p
                  WHERE p.ride_id = r.ride_id AND p.payment_status = 'paid');

-- 4) Most popular pickup points
SELECT pickup_address, COUNT(*) AS rides
FROM rides GROUP BY pickup_address ORDER BY rides DESC LIMIT 5;
