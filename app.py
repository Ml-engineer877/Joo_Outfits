from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash
from datetime import datetime
import mysql.connector
import json
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
# REQUIRED: Establishes context signed session tracking for floating flash notifications
app.secret_key = "joo_outfit_secret_key_studio_prod"

# Configure image upload target directly inside your local static directory
UPLOAD_FOLDER = os.path.join(app.root_path, 'static')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def get_db_connection():
    return mysql.connector.connect(
        host="u6ag18.h.filess.io",
        user="Joo_outfits_timebroken",
        password="7f6baeeb5cba5711545586aaf4808a5faf120afc",
        database="Joo_outfits_timebroken",
        port=3307
    )

# ==========================================
#          VIEW ROUTING CONTROLLERS
# ==========================================
@app.route('/static/sw.js')
def serve_sw():
    return send_from_directory('static', 'sw.js', mimetype='application/javascript')


@app.route('/')
def dashboard():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    current_date = datetime.now().strftime('%Y-%m-%d')
    current_month = datetime.now().strftime('%Y-%m')
    
    # 1. Fetch Daily Profit Analytics
    daily_query = """
        SELECT 
            SUM(quantity_sold * sales_price) as total_revenue,
            SUM(quantity_sold * cost_price_at_sale) as total_cost,
            SUM(quantity_sold * (sales_price - cost_price_at_sale)) as net_profit,
            SUM(quantity_sold) as total_items_sold
        FROM Sales
        WHERE DATE(date_time) = %s
    """
    cursor.execute(daily_query, (current_date,))
    daily_data = cursor.fetchone()
    
    # 2. Fetch Monthly Profit Analytics
    monthly_query = """
        SELECT 
            SUM(quantity_sold * (sales_price - cost_price_at_sale)) as net_profit,
            SUM(quantity_sold) as total_items_sold
        FROM Sales
        WHERE date_time LIKE %s
    """
    cursor.execute(monthly_query, (f"{current_month}%",))
    monthly_data = cursor.fetchone()
    
    # 3. Fetch Low Stock Alerts (including unique stock_id)
    stock_query = """
        SELECT i.stock_id, p.name, i.product_id, i.size, i.quantity 
        FROM Inventory i
        JOIN Products p ON i.product_id = p.product_id
        WHERE i.quantity < 5
    """
    cursor.execute(stock_query)
    low_stock_items = cursor.fetchall()

    # 4. Fetch Grouped Catalog Models with Safe JSON Size Aggregation Array Mapping
    grouped_catalog_query = """
        SELECT 
            p.product_id,
            p.name,
            p.selling_price,
            p.image_path,
            COALESCE(SUM(i.quantity), 0) as total_stock,
            COALESCE(
                (
                    SELECT JSON_ARRAYAGG(
                        JSON_OBJECT(
                            'stock_id', inv.stock_id,
                            'size', inv.size,
                            'quantity', inv.quantity
                        )
                    )
                    FROM Inventory inv
                    WHERE inv.product_id = p.product_id
                ),
                JSON_ARRAY()
            ) as variants_json_raw
        FROM Products p
        LEFT JOIN Inventory i ON p.product_id = i.product_id
        GROUP BY p.product_id, p.name, p.selling_price, p.image_path
        ORDER BY p.name ASC
    """
    cursor.execute(grouped_catalog_query)
    grouped_products = cursor.fetchall()
    
    # Clean string-serialize JSON columns so frontend JS can read them perfectly
    for row in grouped_products:
        if row['variants_json_raw']:
            if isinstance(row['variants_json_raw'], (list, dict)):
                row['variants_json'] = json.dumps(row['variants_json_raw'])
            else:
                row['variants_json'] = str(row['variants_json_raw'])
        else:
            row['variants_json'] = "[]"

    # 5. Fetch Detailed Checkout Statements Log 
    all_sales_query = """
        SELECT 
            s.quantity_sold, 
            s.sales_price, 
            s.cost_price_at_sale, 
            s.size_sold, 
            s.date_time, 
            p.name,
            COALESCE(i.stock_id, 'N/A') as stock_id
        FROM Sales s
        JOIN Products p ON s.product_id = p.product_id
        LEFT JOIN Inventory i ON s.product_id = i.product_id AND s.size_sold = i.size
        ORDER BY s.date_time DESC
    """
    cursor.execute(all_sales_query)
    today_sales_data = cursor.fetchall()
    
    for sale in today_sales_data:
        if isinstance(sale['date_time'], datetime):
            sale['date_time'] = sale['date_time'].strftime('%Y-%m-%d %H:%M:%S')
    
    cursor.close()
    conn.close()
    
    return render_template(
        'dashboard.html', 
        daily=daily_data, 
        monthly=monthly_data, 
        low_stock=low_stock_items,
        products_grouped=grouped_products,
        today_sales_items=today_sales_data
    )

@app.route('/add-product-view')
def add_product_view():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    stock_query = """
        SELECT i.stock_id, p.name, i.product_id, i.size, i.quantity 
        FROM Inventory i
        JOIN Products p ON i.product_id = p.product_id
        WHERE i.quantity < 5
    """
    cursor.execute(stock_query)
    low_stock_items = cursor.fetchall()
    
    cursor.close()
    conn.close()
    return render_template('add_product.html', low_stock=low_stock_items)

@app.route('/restock-view')
def restock_view():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("SELECT product_id, name FROM Products ORDER BY name ASC")
    unique_products_list = cursor.fetchall()
    
    stock_query = """
        SELECT i.stock_id, p.name, i.product_id, i.size, i.quantity 
        FROM Inventory i
        JOIN Products p ON i.product_id = p.product_id
        WHERE i.quantity < 5
    """
    cursor.execute(stock_query)
    low_stock_items = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'restock.html', 
        unique_products=unique_products_list, 
        low_stock=low_stock_items
    )


# ==========================================
#       PURE PYTHON PURE FORM PROCESSING
# ==========================================

@app.route('/reduce-stock', methods=['POST'])
def reduce_stock():
    product_id = request.form.get('product_id')
    size = request.form.get('size')
    qty_to_deduct = int(request.form.get('quantity', 1))
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        price_query = "SELECT name, cost_price, selling_price FROM Products WHERE product_id = %s"
        cursor.execute(price_query, (product_id,))
        product = cursor.fetchone()

        if product:
            update_query = """
                UPDATE Inventory 
                SET quantity = quantity - %s 
                WHERE product_id = %s AND size = %s AND quantity >= %s
            """
            cursor.execute(update_query, (qty_to_deduct, product_id, size, qty_to_deduct))
            
            if cursor.rowcount > 0:
                insert_sale_query = """
                    INSERT INTO Sales (product_id, size_sold, quantity_sold, sales_price, cost_price_at_sale, date_time)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """
                cursor.execute(insert_sale_query, (product_id, size, qty_to_deduct, product['selling_price'], product['cost_price']))
                conn.commit()
                flash(f"Successfully checked out {qty_to_deduct}x '{product['name']}' (Size {size})!", "success")
            else:
                flash("Insufficient stock remaining to fulfill this checkout item order quantity.", "error")
        else:
            flash("Target clothing model product profile could not be verified.", "error")
                
    except Exception as e:
        print(f"Error reducing stock: {e}")
        conn.rollback()
        flash("System transaction processing failure. Checkout logged offline.", "error")
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('dashboard'))

@app.route('/add-product', methods=['POST'])
def add_product():
    name = request.form.get('name')
    cost_price = request.form.get('cost_price')
    selling_price = request.form.get('selling_price')
    
    image_file = request.files.get('image_file')
    db_image_path = "" 

    print(f"DEBUG: Received file object: {image_file}")

    if image_file and image_file.filename != '':
        try:
            filename = secure_filename(image_file.filename)
            if not os.path.exists(app.config['UPLOAD_FOLDER']):
                os.makedirs(app.config['UPLOAD_FOLDER'])
                
            file_save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            image_file.save(file_save_path)
            db_image_path = filename
            print(f"DEBUG: File saved successfully as: {db_image_path}")
        except Exception as file_err:
            print(f"DEBUG: File saving system failed: {file_err}")

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        query = """
            INSERT INTO Products (name, cost_price, selling_price, image_path)
            VALUES (%s, %s, %s, %s)
        """
        cursor.execute(query, (name, cost_price, selling_price, db_image_path))
        conn.commit()
        flash(f"Successfully registered model: '{name}'!", "success")
    except Exception as db_e:
        print(f"DEBUG: Database execution crashed: {db_e}")
        conn.rollback()
        flash("Failed to register entry. Please verify database integrity settings.", "error")
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('add_product_view'))

@app.route('/restock-product', methods=['POST'])
def restock_product():
    stock_id = request.form.get('stock_id')
    product_id = request.form.get('product_id')
    size = request.form.get('size')
    quantity = int(request.form.get('quantity', 0))

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        check_query = """
            SELECT stock_id FROM Inventory 
            WHERE product_id = %s AND size = %s 
            LIMIT 1
        """
        cursor.execute(check_query, (product_id, size))
        existing_row = cursor.fetchone()

        if existing_row:
            query = """
                UPDATE Inventory 
                SET quantity = quantity + %s 
                WHERE product_id = %s AND size = %s
            """
            cursor.execute(query, (quantity, product_id, size))
        else:
            query = """
                INSERT INTO Inventory (stock_id, product_id, size, quantity)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(query, (stock_id, product_id, size, quantity))
            
        conn.commit()
        flash(f"Successfully added {quantity} items to Size {size} variant!", "success")
    except Exception as e:
        print(f"Error restocking: {e}")
        conn.rollback()
        flash("Failed to increment inventory numbers. Please review structural parameter keys.", "error")
    finally:
        cursor.close()
        conn.close()
   
    return redirect(url_for('restock_view'))

# Action: Delete An Inventory Variant Line and clean residual Model Context maps
@app.route('/delete-product', methods=['POST'])
def delete_product():
    target_name = request.form.get('delete_name').strip()
    target_stock_id = request.form.get('delete_stock_id').strip()

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    try:
        # Step 1: Look up the product profile by its text name to fetch its product_id
        find_product_query = "SELECT product_id FROM Products WHERE name = %s LIMIT 1"
        cursor.execute(find_product_query, (target_name,))
        product_record = cursor.fetchone()

        if not product_record:
            flash(f"Error: Product profile named '{target_name}' could not be found.", "error")
            return redirect(url_for('add_product_view'))

        pid = product_record['product_id']

        # Step 2: Delete the matching row item from the Inventory table
        delete_inventory_query = "DELETE FROM Inventory WHERE product_id = %s AND stock_id = %s"
        cursor.execute(delete_inventory_query, (pid, target_stock_id))
        rows_dropped = cursor.rowcount

        if rows_dropped > 0:
            # Step 3: Check if there are any remaining variations left for this product profile
            check_remaining_query = "SELECT COUNT(*) as active_lines FROM Inventory WHERE product_id = %s"
            cursor.execute(check_remaining_query, (pid,))
            remaining_data = cursor.fetchone()

            if remaining_data['active_lines'] == 0:
                # If it was the final variation line, drop the parent catalog profile completely
                delete_parent_query = "DELETE FROM Products WHERE product_id = %s"
                cursor.execute(delete_parent_query, (pid,))
                flash(f"Success: Dropped variant '{target_stock_id}' and cleared full master catalog entry for '{target_name}'!", "success")
            else:
                flash(f"Success: Dropped stock line variation '{target_stock_id}' from the database catalog.", "success")
            
            conn.commit()
        else:
            flash(f"Error: Stock ID reference key '{target_stock_id}' doesn't match a variation line recorded under '{target_name}'.", "error")

    except Exception as err:
        print(f"Database tracking engine failed a destructive sweep: {err}")
        conn.rollback()
        flash("Destructive query rejected. Verify that transaction histories don't lock this line element.", "error")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('add_product_view'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)