# UCI Online Retail demo

Queris can build a local DuckDB database from the UCI Online Retail workbook:

```bash
python -m pip install -e '.[dev]'
queris-online-retail data/online_retail.duckdb
```

The command downloads the workbook to ignored `data/raw/`, installs/uses DuckDB's Excel
extension under that ignored directory, and creates four normalized tables: `orders`,
`order_items`, `products`, and `customers`. It refuses to replace an existing database.

The source dataset contains 541,909 transactions from 2010-12-01 through 2011-12-09. It has
unit price, quantity, invoice time, customer identifier, product description, and country. It
does not provide product categories or product cost, so the demo does not invent those fields.

## Ready-to-use questions

These are good first questions for the Streamlit demo:

1. What are the top 10 products by revenue, excluding cancelled invoices?
2. How has monthly revenue changed over time, excluding cancelled invoices?
3. Which countries generated the most revenue?
4. What is the average unit price by country?
5. Which customers placed the most orders?
6. What percentage of invoices were cancelled?
7. Which products had negative total quantity because of returns or cancellations?
8. What was the average order value by month?
9. Which products sold the most units in the United Kingdom?
10. What was the total revenue from products priced above £10?

Filter cancelled invoices explicitly for ordinary sales analysis:

```sql
WHERE NOT orders.is_cancelled
```

The source must be attributed to Daqing Chen, “Online Retail,” UCI Machine Learning Repository,
DOI `10.24432/C5BW33`, under CC BY 4.0.
