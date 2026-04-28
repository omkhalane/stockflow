from flask import Flask, request, jsonify
from datetime import datetime
from decimal import Decimal
import logging

app = Flask(__name__)
logger = logging.getLogger(__name__)

# Mock in-memory database (simulating PostgreSQL schema)
companies = [{'id': 1, 'name': 'Demo Co', 'is_active': True}]
users = [{'id': 1, 'company_id': 1, 'role': 'admin'}]
warehouses = [{'id': 1, 'company_id': 1, 'name': 'Main Warehouse', 'is_active': True}]
products = []
inventory = []
audit_logs = []
sales_orders = []
sales_order_items = []

next_product_id = 1
next_inventory_id = 1

def get_current_user():
    return {'id': 1, 'company_id': 1, 'is_admin': True}

# Mock validation functions from part1
def validate_sku(sku):
    for p in products:
        if p['sku'] == sku:
            return False, f"SKU '{sku}' already exists"
    return True, None

def validate_price(price):
    try:
        p = Decimal(str(price))
        if p <= 0:
            return False, "Price must be greater than 0"
        return True, p
    except:
        return False, "Invalid price format"

def validate_quantity(qty):
    try:
        q = int(qty)
        if q < 0:
            return False, "Quantity cannot be negative"
        return True, q
    except:
        return False, "Invalid quantity format"

# Part 1: Create Product Endpoint
@app.route('/api/products', methods=['POST'])
def create_product():
    data = request.json or {}
    if not data:
        return jsonify({"error": "No JSON data"}), 400

    # Validation
    required = ['name', 'sku', 'price', 'warehouse_id', 'initial_quantity']
    missing = [f for f in required if f not in data]
    if missing:
        return jsonify({"error": "Missing fields", "missing": missing}), 400

    errors = {}
    if len(data['name']) > 200:
        errors['name'] = "Too long"

    is_valid, msg = validate_sku(data['sku'])
    if not is_valid:
        errors['sku'] = msg

    is_valid, price_val = validate_price(data['price'])
    if not is_valid:
        errors['price'] = price_val

    is_valid, qty_val = validate_quantity(data['initial_quantity'])
    if not is_valid:
        errors['initial_quantity'] = qty_val

    # Check warehouse
    wh = next((w for w in warehouses if w['id'] == data['warehouse_id'] and w['company_id'] == 1), None)
    if not wh:
        errors['warehouse_id'] = "Warehouse not found"

    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 400

    global next_product_id, next_inventory_id
    product_id = next_product_id
    next_product_id += 1

    product = {
        'id': product_id,
        'name': data['name'][:200],
        'sku': data['sku'].upper(),
        'price': price_val,
        'created_at': datetime.utcnow()
    }
    products.append(product)

    inv_id = next_inventory_id
    next_inventory_id += 1
    inventory.append({
        'id': inv_id,
        'product_id': product_id,
        'warehouse_id': data['warehouse_id'],
        'quantity': qty_val,
        'available_quantity': qty_val
    })

    audit_logs.append({
        'action': 'CREATE_PRODUCT',
        'entity_id': product_id,
        'created_at': datetime.utcnow()
    })

    return jsonify({
        "message": "Product created",
        "product": product
    }), 201

# Simplified Part 3: Low Stock Alerts (mock data)
@app.route('/api/companies/<int:company_id>/alerts/low-stock', methods=['GET'])
def get_low_stock_alerts(company_id):
    if company_id != 1:
        return jsonify({"error": "Company not found"}), 404

    # Mock alerts
    alerts = [
        {
            "product_id": 1,
            "product_name": "Widget A",
            "sku": "WID-001",
            "warehouse_id": 1,
            "warehouse_name": "Main Warehouse",
            "current_stock": 5,
            "threshold": 10,
            "days_until_stockout": 12,
            "supplier": {"name": "Supplier Corp"}
        }
    ]

    return jsonify({
        "alerts": alerts,
        "total_alerts": 1,
        "pagination": {"page": 1, "total_pages": 1}
    })

@app.route('/', methods=['GET'])
def home():
    return jsonify({
        "message": "StockFlow Backend Case Study Demo",
        "endpoints": {
            "POST /api/products": "Create product (Part 1)",
            "GET /api/companies/1/alerts/low-stock": "Low stock alerts (Part 3)"
        },
        "instructions": "Use curl or Postman to test endpoints"
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)

