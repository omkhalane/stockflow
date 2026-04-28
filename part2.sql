# PART 2: DATABASE DESIGN
# StockFlow - Inventory Management System Schema

"""
DATABASE SCHEMA DESIGN
======================

QUESTIONS FOR PRODUCT TEAM (Missing Requirements):
===================================================

1. USER & AUTHENTICATION:
   - How do users authenticate? (SSO, OAuth, local accounts?)
   - What are the user roles? (Admin, Manager, Warehouse Staff, Viewer?)
   - Is there multi-tenancy? (Each company isolated?)

2. INVENTORY TRACKING:
   - Do we need to track inventory movements? (transfers between warehouses?)
   - What about inventory adjustments? (damaged goods, theft, corrections?)
   - Should we track batch/lot numbers for products?
   - Do we need expiration date tracking?

3. PRODUCT BUNDLES:
   - Can bundles contain other bundles (nested)?
   - When a bundle is sold, do we auto-decrement component stock?
   - Can bundle composition change over time?

4. SUPPLIERS:
   - Can multiple suppliers provide the same product?
   - Do we need supplier pricing history?
   - What about purchase orders and supplier lead times?
   - Minimum order quantities per supplier?

5. SALES & STOCKOUT CALCULATION:
   - How are "recent sales" defined? (last 30 days? 90 days?)
   - How do we calculate "days until stockout"?
   - Do we need sales order tracking or just analytics?

6. LOW STOCK THRESHOLDS:
   - Who sets the threshold per product? (per warehouse or global?)
   - Can thresholds change seasonally?
   - Different thresholds for different product categories?

7. WAREHOUSE MANAGEMENT:
   - Do warehouses have locations/zones within them?
   - Active/inactive warehouse status?
   - Do we need warehouse capacity limits?

8. DATA RETENTION:
   - How long to keep historical inventory changes?
   - Soft delete vs hard delete for products/warehouses?
   - Archive old data?

9. PERFORMANCE:
   - Expected number of products? (thousands? millions?)
   - Expected number of companies? (scale?)
   - Concurrent users per company?

10. REPORTING:
    - Real-time inventory or eventual consistency acceptable?
    - Do we need inventory snapshots (end of day/month)?
"""

# ============================================================================
# SQL DDL - DATABASE SCHEMA
# ============================================================================

-- Database: PostgreSQL (recommended for JSON support and scalability)

-- Enable UUID extension for better distributed ID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- CORE ENTITIES
-- ============================================================================

-- Companies (Tenants)
CREATE TABLE companies (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE, -- URL-friendly identifier
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    address TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    subscription_tier VARCHAR(50) DEFAULT 'free', -- free, basic, premium
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL -- Soft delete
);

CREATE INDEX idx_companies_active ON companies(is_active) WHERE deleted_at IS NULL;
CREATE INDEX idx_companies_slug ON companies(slug);


-- Users (for authentication and audit)
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    email VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(200),
    role VARCHAR(50) NOT NULL, -- admin, manager, warehouse_staff, viewer
    is_active BOOLEAN DEFAULT TRUE,
    last_login_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, email) -- Email unique per company
);

CREATE INDEX idx_users_company ON users(company_id);
CREATE INDEX idx_users_email ON users(email);


-- Warehouses
CREATE TABLE warehouses (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    code VARCHAR(50), -- Warehouse code (e.g., WH-NYC-01)
    address TEXT,
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100),
    postal_code VARCHAR(20),
    is_active BOOLEAN DEFAULT TRUE,
    capacity_limit INTEGER, -- Optional: max units
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL,
    UNIQUE(company_id, code) -- Code unique per company
);

CREATE INDEX idx_warehouses_company ON warehouses(company_id);
CREATE INDEX idx_warehouses_active ON warehouses(company_id, is_active) WHERE deleted_at IS NULL;


-- Product Categories (for grouping and threshold management)
CREATE TABLE product_categories (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    parent_category_id BIGINT REFERENCES product_categories(id) ON DELETE SET NULL,
    default_low_stock_threshold INTEGER DEFAULT 10,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, name)
);

CREATE INDEX idx_categories_company ON product_categories(company_id);
CREATE INDEX idx_categories_parent ON product_categories(parent_category_id);


-- Products
CREATE TABLE products (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    category_id BIGINT REFERENCES product_categories(id) ON DELETE SET NULL,
    name VARCHAR(200) NOT NULL,
    sku VARCHAR(100) NOT NULL, -- Stock Keeping Unit
    description TEXT,
    price DECIMAL(12, 2) NOT NULL CHECK (price >= 0),
    cost DECIMAL(12, 2) CHECK (cost >= 0), -- Cost of goods
    weight DECIMAL(10, 2), -- For shipping calculations
    weight_unit VARCHAR(10) DEFAULT 'kg', -- kg, lb, oz
    is_bundle BOOLEAN DEFAULT FALSE, -- Is this a product bundle?
    is_active BOOLEAN DEFAULT TRUE,
    barcode VARCHAR(100), -- UPC/EAN barcode
    image_url VARCHAR(500),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL,
    UNIQUE(company_id, sku) -- SKU unique per company
);

CREATE INDEX idx_products_company ON products(company_id);
CREATE INDEX idx_products_sku ON products(company_id, sku);
CREATE INDEX idx_products_category ON products(category_id);
CREATE INDEX idx_products_active ON products(company_id, is_active) WHERE deleted_at IS NULL;
CREATE INDEX idx_products_bundle ON products(is_bundle) WHERE is_bundle = TRUE;


-- Product Bundles (many-to-many relationship for bundle components)
CREATE TABLE product_bundle_items (
    id BIGSERIAL PRIMARY KEY,
    bundle_product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    component_product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL CHECK (quantity > 0), -- Quantity of component in bundle
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bundle_product_id, component_product_id),
    CHECK (bundle_product_id != component_product_id) -- Prevent self-reference
);

CREATE INDEX idx_bundle_items_bundle ON product_bundle_items(bundle_product_id);
CREATE INDEX idx_bundle_items_component ON product_bundle_items(component_product_id);


-- Suppliers
CREATE TABLE suppliers (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name VARCHAR(200) NOT NULL,
    contact_email VARCHAR(255),
    contact_phone VARCHAR(50),
    address TEXT,
    website VARCHAR(255),
    payment_terms VARCHAR(100), -- e.g., "Net 30", "COD"
    lead_time_days INTEGER, -- Average lead time in days
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    deleted_at TIMESTAMP NULL
);

CREATE INDEX idx_suppliers_company ON suppliers(company_id);
CREATE INDEX idx_suppliers_active ON suppliers(company_id, is_active) WHERE deleted_at IS NULL;


-- Product-Supplier Relationship (many-to-many with additional attributes)
CREATE TABLE product_suppliers (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    supplier_id BIGINT NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
    supplier_sku VARCHAR(100), -- Supplier's SKU for this product
    unit_cost DECIMAL(12, 2), -- Cost per unit from this supplier
    minimum_order_quantity INTEGER DEFAULT 1,
    is_preferred BOOLEAN DEFAULT FALSE, -- Preferred supplier for this product
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(product_id, supplier_id)
);

CREATE INDEX idx_product_suppliers_product ON product_suppliers(product_id);
CREATE INDEX idx_product_suppliers_supplier ON product_suppliers(supplier_id);
CREATE INDEX idx_product_suppliers_preferred ON product_suppliers(product_id, is_preferred) WHERE is_preferred = TRUE;


-- ============================================================================
-- INVENTORY MANAGEMENT
-- ============================================================================

-- Current Inventory Levels (snapshot of current stock)
CREATE TABLE inventory (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    warehouse_id BIGINT NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0),
    reserved_quantity INTEGER NOT NULL DEFAULT 0 CHECK (reserved_quantity >= 0), -- Reserved for orders
    available_quantity INTEGER GENERATED ALWAYS AS (quantity - reserved_quantity) STORED,
    low_stock_threshold INTEGER, -- Override category default if needed
    reorder_point INTEGER, -- Trigger reorder when stock hits this level
    reorder_quantity INTEGER, -- How much to reorder
    last_counted_at TIMESTAMP, -- Last physical inventory count
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(product_id, warehouse_id), -- One inventory record per product per warehouse
    CHECK (reserved_quantity <= quantity) -- Can't reserve more than available
);

CREATE INDEX idx_inventory_product ON inventory(product_id);
CREATE INDEX idx_inventory_warehouse ON inventory(warehouse_id);
CREATE INDEX idx_inventory_low_stock ON inventory(warehouse_id, product_id) 
    WHERE quantity <= COALESCE(low_stock_threshold, 10);
CREATE INDEX idx_inventory_available ON inventory(product_id, available_quantity);


-- Inventory Movements (audit trail of all stock changes)
CREATE TABLE inventory_movements (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    warehouse_id BIGINT NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    movement_type VARCHAR(50) NOT NULL, 
        -- PURCHASE, SALE, ADJUSTMENT, TRANSFER_IN, TRANSFER_OUT, RETURN, DAMAGE, THEFT
    quantity INTEGER NOT NULL, -- Positive for increase, negative for decrease
    previous_quantity INTEGER NOT NULL,
    new_quantity INTEGER NOT NULL,
    reference_type VARCHAR(50), -- order, transfer, adjustment
    reference_id BIGINT, -- ID of related entity
    notes TEXT,
    performed_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_movements_product ON inventory_movements(product_id);
CREATE INDEX idx_movements_warehouse ON inventory_movements(warehouse_id);
CREATE INDEX idx_movements_type ON inventory_movements(movement_type);
CREATE INDEX idx_movements_created ON inventory_movements(created_at DESC);
CREATE INDEX idx_movements_reference ON inventory_movements(reference_type, reference_id);


-- Warehouse Transfers
CREATE TABLE warehouse_transfers (
    id BIGSERIAL PRIMARY KEY,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    from_warehouse_id BIGINT NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    to_warehouse_id BIGINT NOT NULL REFERENCES warehouses(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    status VARCHAR(50) NOT NULL DEFAULT 'pending', -- pending, in_transit, completed, cancelled
    initiated_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    completed_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    CHECK (from_warehouse_id != to_warehouse_id)
);

CREATE INDEX idx_transfers_from ON warehouse_transfers(from_warehouse_id);
CREATE INDEX idx_transfers_to ON warehouse_transfers(to_warehouse_id);
CREATE INDEX idx_transfers_product ON warehouse_transfers(product_id);
CREATE INDEX idx_transfers_status ON warehouse_transfers(status);


-- ============================================================================
-- SALES & ANALYTICS
-- ============================================================================

-- Sales Orders (simplified for stockout calculation)
CREATE TABLE sales_orders (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    order_number VARCHAR(100) NOT NULL,
    warehouse_id BIGINT REFERENCES warehouses(id) ON DELETE SET NULL,
    customer_name VARCHAR(200),
    status VARCHAR(50) NOT NULL DEFAULT 'pending', -- pending, confirmed, shipped, delivered, cancelled
    total_amount DECIMAL(12, 2),
    order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    shipped_date TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, order_number)
);

CREATE INDEX idx_sales_orders_company ON sales_orders(company_id);
CREATE INDEX idx_sales_orders_warehouse ON sales_orders(warehouse_id);
CREATE INDEX idx_sales_orders_date ON sales_orders(order_date DESC);
CREATE INDEX idx_sales_orders_status ON sales_orders(status);


-- Sales Order Items
CREATE TABLE sales_order_items (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL REFERENCES sales_orders(id) ON DELETE CASCADE,
    product_id BIGINT NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL CHECK (quantity > 0),
    unit_price DECIMAL(12, 2) NOT NULL,
    subtotal DECIMAL(12, 2) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_order_items_order ON sales_order_items(order_id);
CREATE INDEX idx_order_items_product ON sales_order_items(product_id);


-- Product Sales Analytics (materialized view for performance)
-- This aggregates sales data for stockout calculations
CREATE MATERIALIZED VIEW product_sales_analytics AS
SELECT 
    soi.product_id,
    so.warehouse_id,
    COUNT(DISTINCT so.id) AS order_count_30d,
    SUM(soi.quantity) AS total_quantity_30d,
    AVG(soi.quantity) AS avg_quantity_per_order,
    SUM(soi.quantity) / 30.0 AS avg_daily_sales, -- Sales per day
    MAX(so.order_date) AS last_sale_date
FROM sales_order_items soi
JOIN sales_orders so ON soi.order_id = so.id
WHERE so.order_date >= CURRENT_TIMESTAMP - INTERVAL '30 days'
    AND so.status NOT IN ('cancelled')
GROUP BY soi.product_id, so.warehouse_id;

CREATE UNIQUE INDEX idx_sales_analytics_product_warehouse 
    ON product_sales_analytics(product_id, warehouse_id);

-- Refresh command: REFRESH MATERIALIZED VIEW CONCURRENTLY product_sales_analytics;


-- ============================================================================
-- AUDIT & SYSTEM TABLES
-- ============================================================================

-- Audit Log (track all important actions)
CREATE TABLE audit_logs (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT REFERENCES companies(id) ON DELETE SET NULL,
    user_id BIGINT REFERENCES users(id) ON DELETE SET NULL,
    action VARCHAR(100) NOT NULL, -- CREATE_PRODUCT, UPDATE_INVENTORY, etc.
    entity_type VARCHAR(100), -- Product, Inventory, Order, etc.
    entity_id BIGINT,
    old_values JSONB, -- Store old values as JSON
    new_values JSONB, -- Store new values as JSON
    ip_address VARCHAR(45), -- IPv4 or IPv6
    user_agent TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_company ON audit_logs(company_id);
CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_entity ON audit_logs(entity_type, entity_id);
CREATE INDEX idx_audit_created ON audit_logs(created_at DESC);
CREATE INDEX idx_audit_action ON audit_logs(action);


-- System Configuration (for app-level settings)
CREATE TABLE system_config (
    id BIGSERIAL PRIMARY KEY,
    company_id BIGINT REFERENCES companies(id) ON DELETE CASCADE,
    config_key VARCHAR(100) NOT NULL,
    config_value JSONB NOT NULL,
    description TEXT,
    updated_by BIGINT REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(company_id, config_key)
);

CREATE INDEX idx_config_company ON system_config(company_id);


-- ============================================================================
-- DESIGN DECISIONS & RATIONALE
-- ============================================================================

"""
KEY DESIGN DECISIONS:
=====================

1. MULTI-TENANCY (Company Isolation):
   - Every major table has company_id for data isolation
   - Row-level security can be added for additional safety
   - Allows SaaS model with shared infrastructure

2. SOFT DELETES:
   - deleted_at column allows "undo" functionality
   - Historical reporting remains accurate
   - Indexes use WHERE deleted_at IS NULL for performance

3. INVENTORY TABLE DESIGN:
   - Single source of truth for current stock levels
   - Generated column for available_quantity (automatic calculation)
   - Reserved quantity for orders not yet fulfilled
   - Per-warehouse thresholds override category defaults

4. INVENTORY MOVEMENTS (Audit Trail):
   - Complete history of all stock changes
   - Enables debugging and compliance
   - Partition by created_at for better query performance (scalability)

5. PRODUCT BUNDLES:
   - Separate junction table allows flexible bundle composition
   - Can query "what bundles contain product X?"
   - Prevents circular dependencies with CHECK constraint

6. SUPPLIER RELATIONSHIPS:
   - Many-to-many allows multiple suppliers per product
   - is_preferred flag for primary supplier selection
   - Stores supplier-specific SKU and pricing

7. SALES ANALYTICS:
   - Materialized view pre-calculates aggregate metrics
   - Refreshed periodically (e.g., hourly) to reduce query load
   - Enables fast stockout calculations without scanning all orders

8. INDEXING STRATEGY:
   - Foreign keys always indexed
   - Compound indexes for common query patterns
   - Partial indexes for filtered queries (is_active, deleted_at)
   - GIN indexes for JSONB columns (audit_logs)

9. DATA TYPES:
   - BIGSERIAL for future scalability (8 billion+ records)
   - DECIMAL for money (avoids floating-point errors)
   - TIMESTAMP for timezone awareness
   - JSONB for flexible metadata storage

10. CONSTRAINTS:
    - CHECK constraints enforce business rules at DB level
    - UNIQUE constraints prevent duplicate SKUs per company
    - Foreign keys with ON DELETE CASCADE for cleanup
    - Generated columns reduce redundant data

SCALABILITY CONSIDERATIONS:
============================

1. Partitioning:
   - inventory_movements should be partitioned by created_at (monthly)
   - audit_logs partitioned by created_at
   - Improves query performance for time-range queries

2. Archival Strategy:
   - Move old inventory_movements to archive tables
   - Retain last 12 months in hot storage
   - Historical data in cold storage

3. Caching:
   - Inventory levels cached in Redis for read-heavy operations
   - Invalidate on write (inventory_movements)

4. Read Replicas:
   - Analytics queries on read replica
   - Transactional operations on primary

5. Materialized Views:
   - Refresh during off-peak hours
   - Use CONCURRENTLY to avoid locking

NORMALIZATION vs DENORMALIZATION:
==================================

- Tables are mostly 3NF (normalized)
- Strategic denormalization:
  - available_quantity (generated column)
  - product_sales_analytics (materialized view)
- Trade-off: Write complexity for read performance

MISSING CONSIDERATIONS (Would Ask About):
==========================================

1. Do we need batch/lot tracking for products?
2. Should we track product locations within warehouses (bins/aisles)?
3. Is there a need for purchase order management?
4. Do we support multi-currency pricing?
5. Should we track product variants (size, color)?
6. Do we need barcode generation or just storage?
7. What's the expected data retention policy?
8. Do we need real-time vs eventual consistency?
9. Should we implement optimistic locking for concurrent updates?
10. Do we need support for consignment inventory?

"""
