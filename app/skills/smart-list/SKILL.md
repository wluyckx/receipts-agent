# Smart Shopping List Guide

## Understanding Scores
- `score`: Overall urgency (0-1). Higher = buy sooner.
- `p_need_by_trip`: Probability you'll need this before next shopping trip (0-1).
- `urgency_level`: 'high' (buy now), 'medium' (buy soon), 'low' (not urgent).
- `purchase_reason`: Why this is suggested (e.g., "regular purchase overdue").
- `predicted_trip_date`: When the model expects your next shopping trip.

## Query: urgent items to buy
```sql
SELECT sls.category_id, g.category_name, sls.score, sls.urgency_level,
       sls.purchase_reason, sls.predicted_trip_date
FROM smart_list_scores sls
JOIN google_product_taxonomy g ON g.category_id = sls.category_id
WHERE sls.urgency_level IN ('high', 'medium')
ORDER BY sls.score DESC LIMIT {limit}
```

## Query: purchase frequency for a product
```sql
SELECT pph.product_name, COUNT(*) AS purchase_count,
       MIN(pph.purchase_ts)::date AS first_purchase,
       MAX(pph.purchase_ts)::date AS last_purchase,
       ROUND(AVG(pph.unit_cents)) AS avg_price_cents
FROM product_price_history pph
WHERE pph.product_name ILIKE '%{product}%' AND pph.line_total_cents > 0
GROUP BY pph.product_name ORDER BY purchase_count DESC LIMIT 20
```

## Query: what was on the last receipt
```sql
SELECT pph.product_name, pph.unit_cents, pph.line_total_cents, pph.quantity_print
FROM product_price_history pph
WHERE pph.receipt_hash = (SELECT receipt_hash FROM receipts ORDER BY purchase_ts DESC LIMIT 1)
ORDER BY pph.line_sequence
```
