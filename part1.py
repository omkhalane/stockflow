# PART 1: CODE REVIEW & DEBUGGING
# StockFlow - Product Creation API Endpoint

"""
IDENTIFIED ISSUES IN ORIGINAL CODE:
=====================================

1. NO INPUT VALIDATION
   - Missing validation for required fields
   - No type checking for data types
   - No validation for price (must be positive, decimal)
   - No SKU format validation

2. NO ERROR HANDLING
   - No try-except blocks for database operations
   - No handling for duplicate SKUs (uniqueness constraint)
   - Missing validation if warehouse exists
   - No rollback mechanism on failures

3. BUSINESS LOGIC ISSUES
   - SKU uniqueness not enforced at application level
   - No check if warehouse_id exists before creating product
   - Negative or zero quantities not prevented
   - Missing validation for decimal price values

4. DATABASE TRANSACTION ISSUES
   - Two separate commits create race condition
   - If second commit fails, product exists without inventory
   - No atomic transaction wrapping both operations
   - Partial data could remain in database on failure

5. SECURITY ISSUES
   - No authentication/authorization checks
   - No rate limiting consideration
   - Direct JSON access without sanitization
   - Potential SQL injection if raw queries used elsewhere

6. MISSING FEATURES
   - No audit trail (who created, when)
   - No soft delete capability
   - Missing created_at/updated_at timestamps
   - No logging for debugging

PRODUCTION IMPACT:
==================

1. Duplicate SKUs: Could create inventory conflicts, incorrect stock counts
2. Orphaned Products: Product without inventory if second commit fails
3. Invalid Data: Negative prices, invalid warehouse references
4. System Crashes: Unhandled exceptions bring down the API
5. Data Integrity: Inconsistent state between Product and Inventory tables
6. Security Risks: Unauthorized access, data manipulation

CORRECTED VERSION:
==================
"""

from flask import Flask, request, jsonify
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from decimal import Decimal, InvalidOperation
import logging
from datetime import datetime

app = Flask(__name__)
logger = logging.getLogger(__name__)

# Validation helper functions
def validate_sku(sku):
    """Validate SKU format and uniqueness"""
    if not sku or not isinstance(sku, str):
        return False, "SKU must be a non-empty string"
    
    if len(sku) < 3 or len(sku) > 50:
        return False, "SKU must be between 3 and 50 characters"
    
    # Check uniqueness
    existing = Product.query.filter_by(sku=sku).first()
    if existing:
        return False, f"SKU '{sku}' already exists"
    
    return True, None

def validate_price(price):
    """Validate price is a positive decimal"""
    try:
        price_decimal = Decimal(str(price))
        if price_decimal <= 0:
            return False, "Price must be greater than 0"
        if price_decimal.as_tuple().exponent < -2:
            return False, "Price can have maximum 2 decimal places"
        return True, price_decimal
    except (InvalidOperation, ValueError, TypeError):
        return False, "Invalid price format"

def validate_quantity(quantity):
    """Validate initial quantity"""
    try:
        qty = int(quantity)
        if qty < 0:
            return False, "Quantity cannot be negative"
        return True, qty
    except (ValueError, TypeError):
        return False, "Invalid quantity format"


@app.route('/api/products', methods=['POST'])
def create_product():
    """
    Create a new product with initial inventory.
    
    Expected JSON body:
    {
        "name": "Product Name",
        "sku": "PROD-001",
        "price": 99.99,
        "warehouse_id": 1,
        "initial_quantity": 100,
        "description": "Optional description"  # Optional
    }
    """
    
    # Step 1: Validate request format
    if not request.is_json:
        return jsonify({"error": "Content-Type must be application/json"}), 400
    
    data = request.json
    
    # Step 2: Validate required fields
    required_fields = ['name', 'sku', 'price', 'warehouse_id', 'initial_quantity']
    missing_fields = [field for field in required_fields if field not in data]
    
    if missing_fields:
        return jsonify({
            "error": "Missing required fields",
            "missing": missing_fields
        }), 400
    
    # Step 3: Validate each field
    errors = {}
    
    # Validate name
    if not data['name'] or not isinstance(data['name'], str):
        errors['name'] = "Name must be a non-empty string"
    elif len(data['name']) > 200:
        errors['name'] = "Name must be less than 200 characters"
    
    # Validate SKU
    is_valid, error_msg = validate_sku(data['sku'])
    if not is_valid:
        errors['sku'] = error_msg
    
    # Validate price
    is_valid, price_value = validate_price(data['price'])
    if not is_valid:
        errors['price'] = price_value
    
    # Validate quantity
    is_valid, quantity_value = validate_quantity(data['initial_quantity'])
    if not is_valid:
        errors['initial_quantity'] = quantity_value
    
    # Validate warehouse exists
    warehouse = Warehouse.query.get(data['warehouse_id'])
    if not warehouse:
        errors['warehouse_id'] = f"Warehouse {data['warehouse_id']} does not exist"
    
    # Return validation errors if any
    if errors:
        return jsonify({"error": "Validation failed", "details": errors}), 400
    
    # Step 4: Create product and inventory in a single transaction
    try:
        # Begin transaction (implicit with session)
        product = Product(
            name=data['name'].strip(),
            sku=data['sku'].strip().upper(),  # Normalize SKU to uppercase
            price=price_value,
            description=data.get('description', '').strip(),  # Optional field
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.session.add(product)
        db.session.flush()  # Get product.id without committing
        
        # Create inventory record
        inventory = Inventory(
            product_id=product.id,
            warehouse_id=data['warehouse_id'],
            quantity=quantity_value,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.session.add(inventory)
        
        # Log the creation for audit trail
        audit_log = AuditLog(
            action='CREATE_PRODUCT',
            entity_type='Product',
            entity_id=product.id,
            user_id=get_current_user_id(),  # From auth middleware
            details={
                'sku': product.sku,
                'warehouse_id': data['warehouse_id'],
                'initial_quantity': quantity_value
            },
            created_at=datetime.utcnow()
        )
        db.session.add(audit_log)
        
        # Commit all changes atomically
        db.session.commit()
        
        logger.info(f"Product created successfully: SKU={product.sku}, ID={product.id}")
        
        return jsonify({
            "message": "Product created successfully",
            "product": {
                "id": product.id,
                "name": product.name,
                "sku": product.sku,
                "price": float(product.price),
                "warehouse_id": data['warehouse_id'],
                "initial_quantity": quantity_value
            }
        }), 201
    
    except IntegrityError as e:
        db.session.rollback()
        logger.error(f"Integrity error creating product: {str(e)}")
        
        # Handle specific constraint violations
        if 'sku' in str(e.orig):
            return jsonify({
                "error": "SKU already exists",
                "details": "A product with this SKU already exists in the system"
            }), 409
        
        return jsonify({
            "error": "Database constraint violation",
            "details": "Unable to create product due to data integrity issue"
        }), 400
    
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.error(f"Database error creating product: {str(e)}")
        return jsonify({
            "error": "Database error",
            "details": "An error occurred while creating the product"
        }), 500
    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Unexpected error creating product: {str(e)}")
        return jsonify({
            "error": "Internal server error",
            "details": "An unexpected error occurred"
        }), 500


"""
KEY IMPROVEMENTS EXPLAINED:
===========================

1. ATOMIC TRANSACTIONS
   - Single db.session.commit() ensures both Product and Inventory are created together
   - If anything fails, entire transaction rolls back
   - Uses flush() to get product.id without committing

2. COMPREHENSIVE VALIDATION
   - Check all required fields exist
   - Validate data types and formats
   - Check business rules (positive price, valid warehouse)
   - Normalize data (trim whitespace, uppercase SKU)

3. PROPER ERROR HANDLING
   - Try-except blocks for all database operations
   - Specific handling for IntegrityError (duplicates)
   - Automatic rollback on any error
   - Detailed error messages for debugging

4. SECURITY IMPROVEMENTS
   - Input sanitization (strip, validation)
   - Type checking prevents injection
   - Authentication hook (get_current_user_id)
   - Proper HTTP status codes

5. AUDIT TRAIL
   - Log all product creations
   - Track who did what and when
   - Helpful for debugging and compliance

6. PRODUCTION READY
   - Proper logging for monitoring
   - Clear error messages for API consumers
   - HTTP status codes follow REST conventions
   - Detailed response with created resource

ASSUMPTIONS MADE:
=================
1. SQLAlchemy ORM is being used
2. Authentication middleware provides get_current_user_id()
3. AuditLog model exists for tracking changes
4. Database has unique constraint on Product.sku
5. Warehouse model exists and has proper relationships
"""
