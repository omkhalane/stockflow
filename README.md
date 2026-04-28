# StockFlow Backend Engineering Case Study

This repository contains a cleaned-up, readable version of the StockFlow backend case study deliverables. It focuses on code quality, database design, and a production-minded API for low-stock alerts.

## Repository Layout

| File | Purpose |
| --- | --- |
| [summary.md](summary.md) | Executive submission summary and discussion guide |
| [part1.py](part1.py) | Code review and corrected product-creation endpoint |
| [part2.sql](part2.sql) | PostgreSQL schema design for inventory management |
| [part3.py](part3.py) | Low-stock alerts API implementation |
| [app.py](app.py) | Small demo Flask app showing the main endpoints |
| [requirements.txt](requirements.txt) | Python dependencies |

## What’s Included

### Part 1 — Code Review
- Identifies validation, transaction, security, and logging issues in the original endpoint.
- Reworks the flow around atomic database writes and clearer error handling.
- Documents the assumptions made where the original requirements were incomplete.

### Part 2 — Database Design
- Designs a multi-tenant PostgreSQL schema for products, warehouses, suppliers, inventory, and analytics.
- Uses constraints and indexes to enforce data integrity and improve query performance.
- Includes the product questions that still need clarification before a final build.

### Part 3 — Low Stock Alerts API
- Implements a `/api/companies/<company_id>/alerts/low-stock` endpoint.
- Calculates sales velocity, stockout timing, and supplier information.
- Supports pagination and filters for warehouse-specific views.

## Tech Stack

- Python 3.11+
- Flask 3.x
- SQLAlchemy 2.x
- PostgreSQL 14+

## Quick Start

1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the demo app:
   ```bash
   python app.py
   ```

The demo app exposes a simple home route and sample endpoints for the case study.

## Notes

- The Markdown files are written as submission documents, so they explain the reasoning behind the implementation rather than just the final result.
- File names in the repo now match the current workspace layout, so the documentation points to `part1.py`, `part2.sql`, `part3.py`, and `summary.md`.
- The SQL and Python examples are intentionally verbose so they are easy to review and discuss.

## Discussion Topics

- Transaction safety and rollback strategy
- Schema design for multi-tenant inventory systems
- Sales-velocity-based stockout prediction
- Supplier ranking and alert prioritization
- What additional requirements are needed before production
# stockflow
# stockflow
