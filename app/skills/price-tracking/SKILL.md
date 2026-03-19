# Price Tracking SQL Patterns

## Average price per store for a product
```sql
SELECT s.brand AS store, ROUND(AVG(pph.unit_cents)) AS avg_price_cents,
       COUNT(*) AS purchase_count, MAX(pph.purchase_ts)::date AS last_bought
FROM product_price_history pph
JOIN receipts r ON r.receipt_hash = pph.receipt_hash
JOIN stores s ON s.store_id = r.store_id
WHERE pph.product_name ILIKE '%{product}%'
  AND pph.purchase_ts >= now() - interval '{months} months'
  AND pph.line_total_cents > 0
GROUP BY s.brand ORDER BY avg_price_cents ASC
```

## Price history for a product over time
```sql
SELECT pph.product_name, pph.unit_cents, pph.purchase_ts::date AS date,
       s.brand AS store
FROM product_price_history pph
JOIN receipts r ON r.receipt_hash = pph.receipt_hash
JOIN stores s ON s.store_id = r.store_id
WHERE pph.product_name ILIKE '%{product}%'
  AND pph.purchase_ts >= now() - interval '{months} months'
  AND pph.line_total_cents > 0
ORDER BY pph.purchase_ts DESC LIMIT 50
```

## Which stores sell a product
```sql
SELECT DISTINCT s.brand AS store, COUNT(*) AS times_bought,
       MAX(pph.purchase_ts)::date AS last_bought
FROM product_price_history pph
JOIN receipts r ON r.receipt_hash = pph.receipt_hash
JOIN stores s ON s.store_id = r.store_id
WHERE pph.product_name ILIKE '%{product}%'
  AND pph.line_total_cents > 0
GROUP BY s.brand ORDER BY times_bought DESC
```

## Cheapest store for a product (last 3 months)
```sql
SELECT s.brand AS store, ROUND(AVG(pph.unit_cents)) AS avg_cents,
       MIN(pph.unit_cents) AS min_cents, MAX(pph.unit_cents) AS max_cents,
       COUNT(*) AS purchases
FROM product_price_history pph
JOIN receipts r ON r.receipt_hash = pph.receipt_hash
JOIN stores s ON s.store_id = r.store_id
WHERE pph.product_name ILIKE '%{product}%'
  AND pph.purchase_ts >= now() - interval '3 months'
  AND pph.line_total_cents > 0
GROUP BY s.brand ORDER BY avg_cents ASC
```

## Notes
- All prices in cents (EUR). Divide by 100 for display: X.XX EUR
- Use ILIKE for case-insensitive product name matching
- Product names are typically in Dutch (e.g., "MOZZARELLA 125G")
- Filter `line_total_cents > 0` to exclude deposits/returns
