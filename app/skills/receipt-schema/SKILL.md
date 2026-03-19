# Receipt Database Schema Reference

## Core Tables

### receipts
Primary receipt records. One row per shopping trip.
- `receipt_hash` (text PK) -- unique receipt identifier
- `store_id` (int FK->stores) -- which store
- `purchase_ts` (timestamptz) -- purchase date/time (Europe/Brussels)
- `currency` (text) -- always 'EUR'
- `total_cents` (int) -- receipt total in cents
- `xtra_savings_cents` (int) -- Colruyt Xtra loyalty discount in cents

### product_price_history
Individual line items from receipts. One row per product per receipt.
- `article_nr` (text) -- product article number (store-specific)
- `receipt_hash` (text FK->receipts) -- which receipt
- `purchase_ts` (timestamptz) -- purchase timestamp
- `product_name` (text) -- product label (usually Dutch)
- `unit_cents` (int) -- price per unit in cents
- `quantity_print` (text) -- quantity as printed on receipt (e.g., "2 ST", "0.534 KG")
- `line_total_cents` (int) -- total for this line item in cents
- `google_category` (text) -- taxonomy category path
- `google_category_id` (int FK->google_product_taxonomy) -- category ID

### stores
Store locations.
- `store_id` (int PK)
- `brand` (text) -- COLRUYT, OKAY, SPAR, BIO-PLANET, CRU, COLLECT&GO
- `name` (text) -- store name
- `city` (text) -- city

### google_product_taxonomy
Hierarchical product categories (Google Product Taxonomy).
- `category_id` (bigint PK)
- `category_path` (text) -- full path (e.g., "Food > Dairy > Cheese")
- `category_name` (text) -- leaf name
- `parent_id` (bigint FK->self) -- parent category
- `level` (int) -- depth in hierarchy

### google_category_translations
Localized category names (nl, fr, en).
- `category_id` (int FK->google_product_taxonomy)
- `locale` (varchar) -- 'nl', 'fr', or 'en'
- `display_name` (text) -- translated name

### smart_list_scores
ML-predicted shopping urgency per product category.
- `category_id` (int FK)
- `score` (float) -- overall urgency score (higher = more urgent)
- `p_need_by_trip` (float) -- probability of needing before next trip
- `urgency_level` (text) -- 'high', 'medium', 'low'
- `purchase_reason` (text) -- why this is suggested
- `predicted_trip_date` (date) -- when next trip is expected

## Product Hierarchy

### generic_products
- `generic_product_id` (int PK), `generic_product_name` (text), `google_category` (text), `name_nl` (text), `name_en` (text), `is_staple` (bool)

### base_products
- `base_product_id` (int PK), `base_product_name` (text), `generic_product_id` (int FK), `google_category` (text)

### retail_products
- `retail_product_id` (int PK), `product_name` (text), `base_product_id` (int FK), `generic_product_id` (int FK), `store_brand` (text)

## Useful Views
- `recent_purchases` -- last receipts with store, total, item count
- `top_products` -- most purchased products with spending totals
- `store_performance` -- per-store spending and visit stats
- `category_totals` -- lifetime spending by category
- `daily_spending` -- daily totals by category

## Key JOINs
```sql
-- Products with store info
product_price_history pph
JOIN receipts r ON r.receipt_hash = pph.receipt_hash
JOIN stores s ON s.store_id = r.store_id

-- Products with category names (Dutch)
product_price_history pph
JOIN google_product_taxonomy g ON g.category_id = pph.google_category_id
LEFT JOIN google_category_translations t ON t.category_id = g.category_id AND t.locale = 'nl'

-- Category spending with parent grouping
product_price_history pph
JOIN google_product_taxonomy leaf ON leaf.category_id = pph.google_category_id
JOIN google_product_taxonomy parent ON parent.category_id = leaf.parent_id
```
