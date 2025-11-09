# app.py
from flask import Flask, request, redirect, url_for, render_template, flash, send_file
import sqlite3, os, io
import matplotlib.pyplot as plt

DB_PATH = 'grocery.db'
app = Flask(__name__)
app.secret_key = 'change_this_secret'

def get_db():
    need_create = not os.path.exists(DB_PATH)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if need_create:
        init_db(conn)
    return conn

def init_db(conn):
    cur = conn.cursor()
    cur.executescript("""
    CREATE TABLE products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT,
        price REAL NOT NULL,
        stock INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_name TEXT,
        total REAL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER,
        product_id INTEGER,
        qty INTEGER,
        price REAL
    );
    """)
    sample = [
        ('Milk', 'Dairy', 45.0, 50),
        ('Bread', 'Bakery', 30.0, 40),
        ('Rice (1kg)', 'Grains', 60.0, 30),
        ('Eggs (6)', 'Poultry', 60.0, 25),
        ('Sugar (1kg)', 'Grocery', 40.0, 20)
    ]
    cur.executemany('INSERT INTO products (name, category, price, stock) VALUES (?,?,?,?)', sample)
    conn.commit()

@app.teardown_appcontext
def close_conn(exc):
    try:
        get_db().close()
    except:
        pass

def query_db(query, args=(), one=False):
    conn = get_db()
    cur = conn.execute(query, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows

def execute_db(query, args=()):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(query, args)
    conn.commit()
    return cur.lastrowid

# Simple cart stored in a file for demo (no login)
CART_FILE = 'cart_session.txt'
def get_cart():
    if not os.path.exists(CART_FILE):
        return {}
    try:
        with open(CART_FILE,'r') as f:
            text = f.read().strip()
            if not text:
                return {}
            parts = text.split(',')
            cart = {}
            for p in parts:
                pid,q = p.split(':')
                cart[pid] = int(q)
            return cart
    except:
        return {}
def save_cart(cart):
    if not cart:
        if os.path.exists(CART_FILE):
            os.remove(CART_FILE)
        return
    with open(CART_FILE,'w') as f:
        arr = [f"{pid}:{qty}" for pid,qty in cart.items()]
        f.write(','.join(arr))

@app.route('/')
def index():
    products = query_db('SELECT * FROM products')
    cart = get_cart()
    cart_count = sum(cart.values()) if cart else 0
    return render_template('index.html', products=products, cart_count=cart_count)

@app.route('/add_to_cart', methods=['POST'])
def add_to_cart():
    pid = request.form.get('product_id')
    qty = int(request.form.get('qty',1))
    prod = query_db('SELECT * FROM products WHERE id=?', (pid,), one=True)
    if not prod:
        flash('Product not found')
        return redirect(url_for('index'))
    if qty > prod['stock']:
        flash('Requested quantity not available')
        return redirect(url_for('index'))
    cart = get_cart()
    cart[pid] = cart.get(pid,0) + qty
    save_cart(cart)
    flash('Added to cart')
    return redirect(url_for('index'))

@app.route('/cart')
def cart():
    cart = get_cart()
    cart_count = sum(cart.values()) if cart else 0
    items = []
    total = 0
    for pid,qty in (cart.items() if cart else []):
        p = query_db('SELECT * FROM products WHERE id=?', (pid,), one=True)
        if not p: continue
        subtotal = p['price'] * qty
        total += subtotal
        items.append({'id':pid, 'name':p['name'], 'price':p['price'], 'qty':qty, 'subtotal':subtotal})
    return render_template('cart.html', items=items, total=total, cart_count=cart_count)

@app.route('/update_cart', methods=['POST'])
def update_cart():
    cart = {}
    for key, val in request.form.items():
        if key.startswith('qty_'):
            pid = key.split('_',1)[1]
            try:
                q = int(val)
            except:
                q = 0
            if q>0:
                cart[pid] = q
    save_cart(cart)
    flash('Cart updated')
    return redirect(url_for('cart'))

@app.route('/remove_from_cart/<int:pid>')
def remove_from_cart(pid):
    cart = get_cart()
    cart.pop(str(pid),None)
    save_cart(cart)
    flash('Removed from cart')
    return redirect(url_for('cart'))

@app.route('/checkout', methods=['GET','POST'])
def checkout():
    cart = get_cart()
    if not cart:
        flash('Cart is empty')
        return redirect(url_for('index'))
    if request.method=='GET':
        return render_template('checkout.html', cart_count=sum(cart.values()))
    name = request.form.get('name')
    total = 0
    items=[]
    for pid,qty in cart.items():
        p = query_db('SELECT * FROM products WHERE id=?', (pid,), one=True)
        if not p: continue
        if qty > p['stock']:
            flash(f'Not enough stock for {p["name"]}')
            return redirect(url_for('cart'))
        total += p['price']*qty
        items.append((pid,qty,p['price']))
    order_id = execute_db('INSERT INTO orders (customer_name, total) VALUES (?,?)', (name,total))
    for pid,qty,price in items:
        execute_db('INSERT INTO order_items (order_id,product_id,qty,price) VALUES (?,?,?,?)', (order_id,pid,qty,price))
        execute_db('UPDATE products SET stock = stock - ? WHERE id=?', (qty,pid))
    save_cart({})
    flash(f'Order placed (ID: {order_id})')
    return redirect(url_for('index'))

@app.route('/admin', methods=['GET','POST'])
def admin():
    if request.method=='GET':
        prods = query_db('SELECT * FROM products')
        return render_template('admin.html', products=prods, cart_count=sum(get_cart().values()))
    name = request.form.get('name')
    category = request.form.get('category')
    price = float(request.form.get('price',0))
    stock = int(request.form.get('stock',0))
    execute_db('INSERT INTO products (name,category,price,stock) VALUES (?,?,?,?)', (name,category,price,stock))
    flash('Product added')
    return redirect(url_for('admin'))

@app.route('/help')
def help_page():
    return render_template('help.html', cart_count=sum(get_cart().values()))

@app.route('/orders')
def orders():
    rows = query_db('SELECT * FROM orders ORDER BY created_at DESC')
    data=[]
    for o in rows:
        items = query_db('SELECT oi.qty, oi.price, p.name FROM order_items oi JOIN products p ON oi.product_id=p.id WHERE oi.order_id=?', (o['id'],))
        data.append({'order':o, 'items':items})
    return render_template('orders.html', orders=data, cart_count=sum(get_cart().values()))

@app.route('/analytics')
def analytics():
    rows = query_db('SELECT p.name, SUM(oi.qty) as sold FROM order_items oi JOIN products p ON p.id=oi.product_id GROUP BY p.name')
    names = [r['name'] for r in rows]
    sold = [r['sold'] for r in rows]
    if not names:
        return "<h3>No sales yet to show analytics.</h3>"
    plt.figure(figsize=(6,4))
    plt.bar(names, sold)
    plt.xticks(rotation=45, ha='right')
    plt.title('Product-wise Sold Quantity')
    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format='png')
    buf.seek(0)
    plt.close()
    return send_file(buf, mimetype='image/png')

if __name__ == '__main__':
    app.run(debug=True)
