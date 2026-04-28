# StockFlow Backend Case Study — Submission Summary

## Executive Summary

This repository contains a polished set of backend case-study deliverables for StockFlow.
The work is organized around three themes:

- clean API implementation and error handling
- a scalable multi-tenant inventory schema
- practical documentation of assumptions, trade-offs, and open questions

## What Each File Covers

| File | Purpose |
| --- | --- |
| [part1.py](part1.py) | Reviews and corrects the product-creation endpoint |
| [part2.sql](part2.sql) | Defines the PostgreSQL schema for inventory, suppliers, and analytics |
| [part3.py](part3.py) | Implements low-stock alerts with supplier prioritization |
| [app.py](app.py) | Lightweight Flask demo showing the main routes |
| [README.md](README.md) | Short, practical project guide |

## Part 1 — Code Review

The product-creation flow was redesigned around these principles:

- validate required fields early
- normalize SKU and user input consistently
- perform product and inventory writes in one transaction
- log failures and roll back safely
- return clear HTTP errors instead of generic failures

The main problems addressed were validation gaps, weak transaction handling, and missing auditability.

## Part 2 — Database Design

The schema is built for a multi-tenant inventory platform.
It includes the core entities needed for day-to-day operations:

- companies and users for tenant isolation
- warehouses and inventory for stock tracking
- products, categories, and bundles for catalog management
- suppliers and product-supplier links for procurement
- sales orders and analytics for stockout calculations
- audit logs and system config for governance

Design choices worth calling out:

- company-scoped uniqueness for SKUs and warehouse codes
- soft-delete support for recoverability
- generated and indexed fields for read performance
- a materialized analytics view for stockout reporting

## Part 3 — Low Stock Alerts

The alert endpoint focuses on actionable inventory warnings.
It:

- filters to active products and warehouses
- calculates average daily sales over the last 30 days
- estimates days until stockout
- prefers marked suppliers when more than one exists
- supports warehouse filtering and pagination

This is a good example of balancing real-time accuracy with query cost.

## Assumptions

The implementation assumes:

- Flask and SQLAlchemy are the application stack
- PostgreSQL is the database
- authentication middleware supplies the current user context
- recent sales means the trailing 30 days
- stockout math can use a linear projection

## Open Questions for Product

There are still requirements that should be confirmed before a production build:

1. Should inventory be tracked by warehouse only, or by bin/location as well?
2. Do bundles reduce component stock automatically?
3. How should supplier selection work when no preferred supplier exists?
4. What notification channels should low-stock alerts use?
5. How strict should the alert threshold be across categories and warehouses?

## Testing and Scale Notes

- unit tests should cover validation, transaction rollback, and alert calculations
- integration tests should validate the end-to-end create-product and low-stock flows
- performance testing should check query time with large product catalogs
- caching or async analytics would be the next step for very high volume

## Time Allocation

- Part 1: about 25 minutes
- Part 2: about 35 minutes
- Part 3: about 30 minutes
- Total: about 90 minutes

## Final Takeaway

This solution is intentionally documented like a real handoff:

- it explains what was built
- it shows the reasoning behind the design
- it leaves a clear list of unanswered questions

That makes it easier to review, extend, and discuss in a live interview or team setting.
