from flask import Flask, render_template, request, redirect, url_for
from datetime import datetime
import mysql.connector
from flask import send_from_directory
app = Flask(__name__)

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
    
    # Fetch Daily Profit Analytics
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
    
    # Fetch Monthly Profit Analytics
    monthly_query = """
        SELECT 
            SUM(quantity_sold * (sales_price - cost_price_at_sale)) as net_profit,
            SUM(quantity_sold) as total_items_sold
        FROM Sales
        WHERE DATE_FORMAT(date_time, '%%Y-%%m') = %s
    """
    cursor.execute(monthly_query, (current_month,))
    monthly_data = cursor.fetchone()
    
    # Fetch Low Stock Alerts (including unique stock_id)
    stock_query = """
        SELECT i.stock_id, p.name, i.product_id, i.size, i.quantity 
        FROM Inventory i
        JOIN Products p ON i.product_id = p.product_id
        WHERE i.quantity < 5
    """
    cursor.execute(stock_query)
    low_stock_items = cursor.fetchall()

    # Fetch All Stock Items for Counter POS Display
    all_stock_query = """
        SELECT i.stock_id, p.name, p.selling_price, i.product_id, i.size, i.quantity 
        FROM Inventory i
        JOIN Products p ON i.product_id = p.product_id
        ORDER BY p.name ASC, i.size ASC
    """
    cursor.execute(all_stock_query)
    all_stock_items = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template(
        'dashboard.html', 
        daily=daily_data, 
        monthly=monthly_data, 
        low_stock=low_stock_items,
        stock_items=all_stock_items
    )

@app.route('/add-product-view')
def add_product_view():
    return render_template('add_product.html')

@app.route('/restock-view')
def restock_view():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT product_id, name FROM Products ORDER BY name ASC")
    unique_products_list = cursor.fetchall()
    cursor.close()
    conn.close()
    return render_template('restock.html', unique_products=unique_products_list)


# ==========================================
#      PURE PYTHON PURE FORM PROCESSING
# ==========================================

# Action: Log Counter Sale via POST Form
@app.route('/reduce-stock', methods=['POST'])
def reduce_stock():
    product_id = request.form.get('product_id')
    size = request.form.get('size')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    try:
        # Get standard prices from the Products table
        price_query = "SELECT cost_price, selling_price FROM Products WHERE product_id = %s"
        cursor.execute(price_query, (product_id,))
        product = cursor.fetchone()

        if product:
            # Decrement inventory by 1
            update_query = """
                UPDATE Inventory 
                SET quantity = quantity - 1 
                WHERE product_id = %s AND size = %s AND quantity > 0
            """
            cursor.execute(update_query, (product_id, size))
            
            # If stock was successfully updated, log the sale details
            if cursor.rowcount > 0:
                insert_sale_query = """
                    INSERT INTO Sales (product_id, size_sold, quantity_sold, sales_price, cost_price_at_sale, date_time)
                    VALUES (%s, %s, 1, %s, %s, NOW())
                """
                cursor.execute(insert_sale_query, (product_id, size, product['selling_price'], product['cost_price']))
                conn.commit()
                
    except Exception as e:
        print(f"Error reducing stock: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('dashboard'))

# Action: Add New Base Product via POST Form
@app.route('/add-product', methods=['POST'])
def add_product():
    product_id=request.form.get('product_id')
    name = request.form.get('name')
    cost_price = request.form.get('cost_price')
    selling_price = request.form.get('selling_price')
    image_path = request.form.get('image_path', '')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        query = """
            INSERT INTO Products (product_id,name, cost_price, selling_price, image_path)
            VALUES (%s,%s, %s, %s, %s)
        """
        cursor.execute(query, (product_id,name, cost_price, selling_price, image_path))
        conn.commit()
    except Exception as e:
        print(f"Error adding product: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
        
    return redirect(url_for('dashboard'))

# Action: Apply Size Restocking Intake via POST Form
@app.route('/restock-product', methods=['POST'])
def restock_product():
    stock_id = request.form.get('stock_id')
    product_id = request.form.get('product_id')
    size = request.form.get('size')
    quantity = request.form.get('quantity')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        query = """
            INSERT INTO Inventory (stock_id,product_id, size, quantity)
            VALUES (%s,%s, %s, %s)
            ON DUPLICATE KEY UPDATE quantity = quantity + VALUES(quantity)
        """
        cursor.execute(query, (stock_id,product_id, size, quantity))
        conn.commit()
    except Exception as e:
        print(f"Error restocking: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()
   
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)