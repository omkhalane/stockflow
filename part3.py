# PART 3: API IMPLEMENTATION - LOW STOCK ALERTS
# GET /api/companies/{company_id}/alerts/low-stock

"""
IMPLEMENTATION: Low Stock Alerts Endpoint
==========================================

ASSUMPTIONS MADE:
=================
1. Database schema from Part 2 is in place
2. Using Flask + SQLAlchemy ORM
3. Authentication middleware provides current_user
4. "Recent sales activity" = sales in last 30 days
5. "Days until stockout" = current_stock / average_daily_sales
6. Low stock threshold can be product-specific or category default
7. Only active products and warehouses are considered
8. Preferred supplier is returned if available, otherwise any supplier

BUSINESS RULES:
===============
1. Only alert if product has sales in last 30 days (active products)
2. Only alert if current stock <= threshold
3. Must have supplier information available
4. Calculate realistic stockout timeline based on sales velocity
5. Support pagination for companies with many products
"""

from flask import Flask, request, jsonify
from sqlalchemy import and_, or_, func, case
from sqlalchemy.orm import joinedload, aliased
from datetime import datetime, timedelta
from decimal import Decimal
import logging

app = Flask(__name__)
logger = logging.getLogger(__name__)


def calculate_days_until_stockout(current_stock, avg_daily_sales):
    """
    Calculate days until stockout based on current stock and sales velocity.
    
    Args:
        current_stock: Current available quantity
        avg_daily_sales: Average daily sales over recent period
    
    Returns:
        Integer days until stockout, or None if no sales velocity
    """
    if not avg_daily_sales or avg_daily_sales <= 0:
        return None  # No sales data, can't predict stockout
    
    if current_stock <= 0:
        return 0  # Already out of stock
    
    # Simple linear projection
    days = int(current_stock / avg_daily_sales)
    return max(0, days)  # Ensure non-negative


@app.route('/api/companies/<int:company_id>/alerts/low-stock', methods=['GET'])
def get_low_stock_alerts(company_id):
    """
    Get low stock alerts for a company across all warehouses.
    
    Query Parameters:
        - warehouse_id (optional): Filter by specific warehouse
        - threshold_days (optional): Alert if stockout within X days (default: 30)
        - page (optional): Page number for pagination (default: 1)
        - per_page (optional): Items per page (default: 50, max: 200)
    
    Returns:
        JSON response with low stock alerts including supplier information
    """
    
    # Step 1: Validate company access and existence
    try:
        # Verify user has access to this company
        # This would typically come from authentication middleware
        current_user = get_current_user()
        
        if current_user.company_id != company_id and not current_user.is_admin:
            return jsonify({
                "error": "Forbidden",
                "message": "You don't have access to this company's data"
            }), 403
        
        # Verify company exists
        company = Company.query.get(company_id)
        if not company or company.deleted_at is not None:
            return jsonify({
                "error": "Not Found",
                "message": f"Company {company_id} not found"
            }), 404
        
    except Exception as e:
        logger.error(f"Error validating company access: {str(e)}")
        return jsonify({"error": "Internal server error"}), 500
    
    # Step 2: Parse and validate query parameters
    warehouse_id = request.args.get('warehouse_id', type=int)
    threshold_days = request.args.get('threshold_days', default=30, type=int)
    page = request.args.get('page', default=1, type=int)
    per_page = request.args.get('per_page', default=50, type=int)
    
    # Validate pagination parameters
    if page < 1:
        return jsonify({"error": "Page must be >= 1"}), 400
    if per_page < 1 or per_page > 200:
        return jsonify({"error": "per_page must be between 1 and 200"}), 400
    if threshold_days < 0:
        return jsonify({"error": "threshold_days must be >= 0"}), 400
    
    # If warehouse_id provided, verify it belongs to this company
    if warehouse_id:
        warehouse = Warehouse.query.filter_by(
            id=warehouse_id,
            company_id=company_id
        ).first()
        if not warehouse or warehouse.deleted_at is not None:
            return jsonify({
                "error": "Not Found",
                "message": f"Warehouse {warehouse_id} not found for this company"
            }), 404
    
    # Step 3: Build complex query for low stock alerts
    try:
        # Calculate the date 30 days ago for "recent sales"
        recent_sales_cutoff = datetime.utcnow() - timedelta(days=30)
        
        # Subquery for calculating average daily sales per product/warehouse
        sales_subquery = db.session.query(
            SalesOrderItem.product_id,
            SalesOrder.warehouse_id,
            func.sum(SalesOrderItem.quantity).label('total_sold'),
            func.count(func.distinct(SalesOrder.id)).label('order_count'),
            (func.sum(SalesOrderItem.quantity) / 30.0).label('avg_daily_sales')
        ).join(
            SalesOrder, SalesOrderItem.order_id == SalesOrder.id
        ).filter(
            and_(
                SalesOrder.company_id == company_id,
                SalesOrder.order_date >= recent_sales_cutoff,
                SalesOrder.status.notin_(['cancelled', 'refunded']),
                SalesOrder.deleted_at.is_(None)
            )
        ).group_by(
            SalesOrderItem.product_id,
            SalesOrder.warehouse_id
        ).subquery()
        
        # Main query with joins
        query = db.session.query(
            Product.id.label('product_id'),
            Product.name.label('product_name'),
            Product.sku,
            Inventory.warehouse_id,
            Warehouse.name.label('warehouse_name'),
            Inventory.available_quantity.label('current_stock'),
            func.coalesce(
                Inventory.low_stock_threshold,
                ProductCategory.default_low_stock_threshold,
                10  # System default if nothing else set
            ).label('threshold'),
            sales_subquery.c.avg_daily_sales,
            sales_subquery.c.total_sold,
            Supplier.id.label('supplier_id'),
            Supplier.name.label('supplier_name'),
            Supplier.contact_email.label('supplier_email'),
            ProductSupplier.unit_cost,
            ProductSupplier.minimum_order_quantity
        ).select_from(
            Inventory
        ).join(
            Product, Inventory.product_id == Product.id
        ).join(
            Warehouse, Inventory.warehouse_id == Warehouse.id
        ).outerjoin(
            ProductCategory, Product.category_id == ProductCategory.id
        ).outerjoin(
            sales_subquery,
            and_(
                sales_subquery.c.product_id == Product.id,
                sales_subquery.c.warehouse_id == Inventory.warehouse_id
            )
        ).outerjoin(
            ProductSupplier,
            ProductSupplier.product_id == Product.id
        ).outerjoin(
            Supplier, ProductSupplier.supplier_id == Supplier.id
        ).filter(
            and_(
                Product.company_id == company_id,
                Product.is_active == True,
                Product.deleted_at.is_(None),
                Warehouse.is_active == True,
                Warehouse.deleted_at.is_(None),
                # Only include if there were recent sales
                sales_subquery.c.total_sold > 0,
                # Only include if supplier exists
                Supplier.id.isnot(None),
                Supplier.is_active == True,
                Supplier.deleted_at.is_(None)
            )
        )
        
        # Add warehouse filter if specified
        if warehouse_id:
            query = query.filter(Inventory.warehouse_id == warehouse_id)
        
        # Subquery to get preferred supplier or any supplier
        # We'll use a window function to prioritize preferred suppliers
        preferred_supplier_rank = func.row_number().over(
            partition_by=[Product.id, Inventory.warehouse_id],
            order_by=[
                case(
                    (ProductSupplier.is_preferred == True, 1),
                    else_=2
                ),
                Supplier.id
            ]
        ).label('supplier_rank')
        
        # Modify query to include supplier ranking
        ranked_query = query.add_columns(preferred_supplier_rank)
        
        # Filter to only get rank 1 (preferred or first supplier)
        final_query = ranked_query.from_self().filter(
            ranked_query.c.supplier_rank == 1
        )
        
        # Filter by low stock condition (current_stock <= threshold)
        final_query = final_query.filter(
            Inventory.available_quantity <= func.coalesce(
                Inventory.low_stock_threshold,
                ProductCategory.default_low_stock_threshold,
                10
            )
        )
        
        # Get total count for pagination
        total_count = final_query.count()
        
        # Apply pagination
        offset = (page - 1) * per_page
        results = final_query.order_by(
            # Order by urgency: lowest days until stockout first
            func.coalesce(
                Inventory.available_quantity / func.nullif(sales_subquery.c.avg_daily_sales, 0),
                9999  # Products with no sales velocity go to end
            ).asc(),
            Product.name.asc()
        ).limit(per_page).offset(offset).all()
        
        # Step 4: Process results and build response
        alerts = []
        for row in results:
            # Calculate days until stockout
            days_until_stockout = calculate_days_until_stockout(
                row.current_stock,
                float(row.avg_daily_sales) if row.avg_daily_sales else 0
            )
            
            # Only include if stockout is within threshold_days
            if days_until_stockout is not None and days_until_stockout <= threshold_days:
                alert = {
                    "product_id": row.product_id,
                    "product_name": row.product_name,
                    "sku": row.sku,
                    "warehouse_id": row.warehouse_id,
                    "warehouse_name": row.warehouse_name,
                    "current_stock": row.current_stock,
                    "threshold": int(row.threshold),
                    "days_until_stockout": days_until_stockout,
                    "sales_velocity": {
                        "avg_daily_sales": round(float(row.avg_daily_sales), 2) if row.avg_daily_sales else 0,
                        "total_sold_30d": int(row.total_sold) if row.total_sold else 0
                    },
                    "supplier": {
                        "id": row.supplier_id,
                        "name": row.supplier_name,
                        "contact_email": row.supplier_email
                    },
                    "reorder_info": {
                        "unit_cost": float(row.unit_cost) if row.unit_cost else None,
                        "minimum_order_quantity": row.minimum_order_quantity
                    }
                }
                alerts.append(alert)
        
        # Step 5: Build pagination metadata
        total_pages = (total_count + per_page - 1) // per_page  # Ceiling division
        
        response = {
            "alerts": alerts,
            "total_alerts": len(alerts),
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total_items": total_count,
                "total_pages": total_pages,
                "has_next": page < total_pages,
                "has_prev": page > 1
            },
            "filters": {
                "warehouse_id": warehouse_id,
                "threshold_days": threshold_days,
                "recent_sales_period_days": 30
            }
        }
        
        logger.info(f"Low stock alerts retrieved for company {company_id}: {len(alerts)} alerts")
        
        return jsonify(response), 200
    
    except Exception as e:
        logger.error(f"Error retrieving low stock alerts: {str(e)}", exc_info=True)
        return jsonify({
            "error": "Internal server error",
            "message": "Failed to retrieve low stock alerts"
        }), 500


# ============================================================================
# ALTERNATIVE IMPLEMENTATION: Using Raw SQL for Better Performance
# ============================================================================

def get_low_stock_alerts_raw_sql(company_id, warehouse_id=None, threshold_days=30, page=1, per_page=50):
    """
    Alternative implementation using raw SQL for better performance with large datasets.
    
    This approach:
    - Uses a single optimized query
    - Leverages database indexing effectively
    - Reduces ORM overhead for read-heavy operations
    """
    
    offset = (page - 1) * per_page
    
    # Base SQL query
    sql = """
    WITH recent_sales AS (
        -- Calculate sales velocity for each product/warehouse combination
        SELECT 
            soi.product_id,
            so.warehouse_id,
            SUM(soi.quantity) AS total_sold_30d,
            SUM(soi.quantity) / 30.0 AS avg_daily_sales,
            COUNT(DISTINCT so.id) AS order_count
        FROM sales_order_items soi
        JOIN sales_orders so ON soi.order_id = so.id
        WHERE 
            so.company_id = :company_id
            AND so.order_date >= NOW() - INTERVAL '30 days'
            AND so.status NOT IN ('cancelled', 'refunded')
            AND so.deleted_at IS NULL
        GROUP BY soi.product_id, so.warehouse_id
        HAVING SUM(soi.quantity) > 0  -- Only products with sales
    ),
    low_stock_products AS (
        -- Find products below threshold with supplier info
        SELECT 
            p.id AS product_id,
            p.name AS product_name,
            p.sku,
            i.warehouse_id,
            w.name AS warehouse_name,
            i.available_quantity AS current_stock,
            COALESCE(i.low_stock_threshold, pc.default_low_stock_threshold, 10) AS threshold,
            rs.avg_daily_sales,
            rs.total_sold_30d,
            CASE 
                WHEN rs.avg_daily_sales > 0 THEN 
                    FLOOR(i.available_quantity / rs.avg_daily_sales)
                ELSE NULL 
            END AS days_until_stockout,
            -- Get preferred supplier or any supplier (ordered)
            FIRST_VALUE(s.id) OVER (
                PARTITION BY p.id, i.warehouse_id 
                ORDER BY ps.is_preferred DESC, s.id
            ) AS supplier_id,
            FIRST_VALUE(s.name) OVER (
                PARTITION BY p.id, i.warehouse_id 
                ORDER BY ps.is_preferred DESC, s.id
            ) AS supplier_name,
            FIRST_VALUE(s.contact_email) OVER (
                PARTITION BY p.id, i.warehouse_id 
                ORDER BY ps.is_preferred DESC, s.id
            ) AS supplier_email,
            FIRST_VALUE(ps.unit_cost) OVER (
                PARTITION BY p.id, i.warehouse_id 
                ORDER BY ps.is_preferred DESC, s.id
            ) AS unit_cost,
            FIRST_VALUE(ps.minimum_order_quantity) OVER (
                PARTITION BY p.id, i.warehouse_id 
                ORDER BY ps.is_preferred DESC, s.id
            ) AS min_order_qty,
            ROW_NUMBER() OVER (
                PARTITION BY p.id, i.warehouse_id 
                ORDER BY ps.is_preferred DESC, s.id
            ) AS supplier_rank
        FROM inventory i
        JOIN products p ON i.product_id = p.id
        JOIN warehouses w ON i.warehouse_id = w.id
        LEFT JOIN product_categories pc ON p.category_id = pc.id
        JOIN recent_sales rs ON rs.product_id = p.id AND rs.warehouse_id = i.warehouse_id
        JOIN product_suppliers ps ON ps.product_id = p.id
        JOIN suppliers s ON ps.supplier_id = s.id
        WHERE 
            p.company_id = :company_id
            AND p.is_active = TRUE
            AND p.deleted_at IS NULL
            AND w.is_active = TRUE
            AND w.deleted_at IS NULL
            AND s.is_active = TRUE
            AND s.deleted_at IS NULL
            AND i.available_quantity <= COALESCE(i.low_stock_threshold, pc.default_low_stock_threshold, 10)
            {warehouse_filter}
    )
    SELECT 
        product_id,
        product_name,
        sku,
        warehouse_id,
        warehouse_name,
        current_stock,
        threshold,
        avg_daily_sales,
        total_sold_30d,
        days_until_stockout,
        supplier_id,
        supplier_name,
        supplier_email,
        unit_cost,
        min_order_qty
    FROM low_stock_products
    WHERE supplier_rank = 1  -- Only get first supplier per product/warehouse
        AND (days_until_stockout IS NULL OR days_until_stockout <= :threshold_days)
    ORDER BY 
        COALESCE(days_until_stockout, 9999) ASC,  -- Most urgent first
        product_name ASC
    LIMIT :per_page OFFSET :offset
    """
    
    # Add warehouse filter if specified
    warehouse_filter = "AND i.warehouse_id = :warehouse_id" if warehouse_id else ""
    sql = sql.format(warehouse_filter=warehouse_filter)
    
    # Execute query
    params = {
        'company_id': company_id,
        'threshold_days': threshold_days,
        'per_page': per_page,
        'offset': offset
    }
    if warehouse_id:
        params['warehouse_id'] = warehouse_id
    
    result = db.session.execute(sql, params)
    
    return result.fetchall()


"""
EDGE CASES HANDLED:
===================

1. No Sales Data:
   - Products with zero sales in last 30 days are excluded
   - Prevents false alarms for slow-moving inventory

2. Division by Zero:
   - Uses NULLIF and COALESCE to handle zero sales velocity
   - Returns None for days_until_stockout if no sales data

3. Multiple Suppliers:
   - Uses window function FIRST_VALUE to select preferred supplier
   - Falls back to any supplier if no preferred one marked

4. Missing Thresholds:
   - Falls back to category default, then system default (10)
   - Ensures every product has a threshold

5. Deleted/Inactive Records:
   - Filters out soft-deleted products, warehouses, suppliers
   - Only shows active inventory

6. Permission Validation:
   - Checks user belongs to company
   - Returns 403 if unauthorized

7. Invalid Input:
   - Validates pagination parameters
   - Validates warehouse belongs to company
   - Returns appropriate error codes

8. Large Result Sets:
   - Implements pagination
   - Includes metadata for navigation
   - Limits max per_page to prevent memory issues

9. No Supplier Available:
   - Filters out products without suppliers
   - Ensures alerts are actionable

10. Concurrent Modifications:
    - Read-only query doesn't lock tables
    - Uses current snapshot of data

PERFORMANCE OPTIMIZATIONS:
===========================

1. Indexed Queries:
   - All JOIN columns are indexed
   - WHERE conditions use indexed columns
   - ORDER BY uses indexed columns

2. Subquery Optimization:
   - Sales calculation done once as CTE
   - Reused across main query

3. Selective Filtering:
   - Filter early (company_id, is_active)
   - Reduce dataset before complex operations

4. Materialized View Option:
   - For very large datasets, create materialized view
   - Refresh hourly instead of real-time calculation

5. Database-Level Calculations:
   - Days calculation done in SQL
   - Reduces data transfer to application

TESTING CONSIDERATIONS:
========================

1. Unit Tests:
   - Test with various threshold values
   - Test pagination edge cases
   - Test with missing suppliers
   - Test with zero/negative stock

2. Integration Tests:
   - Test with realistic data volumes
   - Verify query performance
   - Test concurrent access

3. Edge Case Tests:
   - Empty result set
   - Single result
   - Exactly per_page results
   - All products below threshold

MONITORING & ALERTING:
======================

1. Query Performance:
   - Monitor query execution time
   - Alert if > 2 seconds

2. Alert Volume:
   - Track number of alerts per company
   - Unusual spikes may indicate data issues

3. API Usage:
   - Monitor endpoint call frequency
   - Rate limiting if necessary

4. Error Rates:
   - Track 500 errors
   - Alert on error rate > 1%
"""
