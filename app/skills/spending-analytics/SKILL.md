# Spending Analytics SQL Patterns

Use these patterns with `query_readonly`. Replace placeholders with actual values.

## Monthly spending by parent category (Dutch names)
```sql
SELECT COALESCE(t.display_name, parent.category_name) AS category,
       SUM(pph.line_total_cents) AS total_cents, COUNT(*) AS items
FROM product_price_history pph
JOIN google_product_taxonomy leaf ON leaf.category_id = pph.google_category_id
JOIN google_product_taxonomy parent ON parent.category_id = leaf.parent_id
LEFT JOIN google_category_translations t
    ON t.category_id = parent.category_id AND t.locale = 'nl'
WHERE pph.purchase_ts >= now() - interval '{months} months'
  AND pph.line_total_cents > 0
GROUP BY parent.category_id, parent.category_name, t.display_name
ORDER BY total_cents DESC
```

## Monthly spending by store
```sql
SELECT s.brand AS store, COUNT(DISTINCT r.receipt_hash) AS trips,
       SUM(r.total_cents) AS total_cents, SUM(r.xtra_savings_cents) AS savings_cents
FROM receipts r JOIN stores s ON s.store_id = r.store_id
WHERE r.purchase_ts >= now() - interval '{months} months'
GROUP BY s.brand ORDER BY total_cents DESC
```

## Daily spending trend
```sql
SELECT r.purchase_ts::date AS date, SUM(r.total_cents) AS total_cents,
       COUNT(DISTINCT r.receipt_hash) AS trips
FROM receipts r
WHERE r.purchase_ts >= now() - interval '{days} days'
GROUP BY r.purchase_ts::date ORDER BY date
```

## Top products by spending in period
```sql
SELECT pph.product_name, SUM(pph.line_total_cents) AS total_cents,
       COUNT(*) AS purchase_count, ROUND(AVG(pph.unit_cents)) AS avg_price_cents
FROM product_price_history pph
WHERE pph.purchase_ts >= now() - interval '{months} months'
  AND pph.line_total_cents > 0
GROUP BY pph.product_name ORDER BY total_cents DESC LIMIT {limit}
```

## Receipt count and total for a period
```sql
SELECT COUNT(*) AS receipt_count, SUM(total_cents) AS total_cents
FROM receipts WHERE purchase_ts >= now() - interval '{months} months'
```
