"""
Cafe Management System (CLI) - Single-file Python app using SQLite
Features:
- Menu management: add/update/delete/list items
- Inventory management (stock levels)
- Place orders (select items + quantities)
- Generate bill and store orders in DB
- View past orders and simple sales report (by date range)
- Export orders to CSV (optional)

Run: python3 cafe_management_system.py

This is a simple, extensible starting point you can expand with a GUI or web frontend later.
"""

import sqlite3
import datetime
import csv
import os
from tabulate import tabulate

DB_FILE = "cafe.db"


def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute('''
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        price REAL NOT NULL,
        stock INTEGER DEFAULT 0
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        total REAL NOT NULL
    )
    ''')

    cur.execute('''
    CREATE TABLE IF NOT EXISTS order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        item_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        price REAL NOT NULL,
        FOREIGN KEY(order_id) REFERENCES orders(id),
        FOREIGN KEY(item_id) REFERENCES items(id)
    )
    ''')

    conn.commit()
    conn.close()



def add_item(name, price, stock=0):
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("INSERT INTO items (name, price, stock) VALUES (?, ?, ?)", (name, price, stock))
        conn.commit()
        print(f"Item '{name}' added.")
    except sqlite3.IntegrityError:
        print("Error: Item with that name already exists.")
    finally:
        conn.close()


def update_item(item_id, name=None, price=None, stock=None):
    conn = get_connection()
    cur = conn.cursor()
    fields = []
    values = []
    if name is not None:
        fields.append("name = ?")
        values.append(name)
    if price is not None:
        fields.append("price = ?")
        values.append(price)
    if stock is not None:
        fields.append("stock = ?")
        values.append(stock)
    values.append(item_id)
    sql = f"UPDATE items SET {', '.join(fields)} WHERE id = ?"
    cur.execute(sql, values)
    conn.commit()
    conn.close()
    print("Item updated.")


def delete_item(item_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    conn.close()
    print("Item deleted (if existed).")


def list_items(show_zero_stock=False):
    conn = get_connection()
    cur = conn.cursor()
    if show_zero_stock:
        cur.execute("SELECT * FROM items ORDER BY id")
    else:
        cur.execute("SELECT * FROM items WHERE stock > 0 ORDER BY id")
    rows = cur.fetchall()
    conn.close()
    if rows:
        table = [(r["id"], r["name"], f"{r['price']:.2f}", r["stock"]) for r in rows]
        print(tabulate(table, headers=["ID", "Name", "Price", "Stock"]))
    else:
        print("No items found.")


def place_order():
    conn = get_connection()
    cur = conn.cursor()

    cart = []  

    while True:
        print('\nCurrent menu:')
        cur.execute("SELECT * FROM items ORDER BY id")
        items = cur.fetchall()
        table = [(i['id'], i['name'], f"{i['price']:.2f}", i['stock']) for i in items]
        print(tabulate(table, headers=["ID", "Name", "Price", "Stock"]))

        choice = input("Enter item ID to add to cart (or 'done' to finish): ").strip()
        if choice.lower() == 'done':
            break
        if not choice.isdigit():
            print("Invalid ID")
            continue
        item_id = int(choice)
        cur.execute("SELECT * FROM items WHERE id = ?", (item_id,))
        item = cur.fetchone()
        if not item:
            print("Item not found.")
            continue
        if item['stock'] <= 0:
            print("Sorry, item out of stock.")
            continue

        qty_str = input(f"Enter quantity (available {item['stock']}): ").strip()
        if not qty_str.isdigit():
            print("Invalid quantity.")
            continue
        qty = int(qty_str)
        if qty <= 0 or qty > item['stock']:
            print("Quantity not available.")
            continue

        cart.append((item['id'], item['name'], item['price'], qty))
        print(f"Added {qty} x {item['name']} to cart.")

    if not cart:
        print("No items in cart. Order cancelled.")
        conn.close()
        return

   
    total = sum(price * qty for (_, _, price, qty) in cart)
    print('\n---- BILL ----')
    bill_table = [(name, qty, f"{price:.2f}", f"{price*qty:.2f}") for (_, name, price, qty) in cart]
    print(tabulate(bill_table, headers=["Name", "Qty", "Unit", "Total"]))
    print(f"Grand Total: {total:.2f}")

    confirm = input("Confirm and place order? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Order cancelled.")
        conn.close()
        return

    
    created_at = datetime.datetime.now().isoformat()
    cur.execute("INSERT INTO orders (created_at, total) VALUES (?, ?)", (created_at, total))
    order_id = cur.lastrowid
    for item_id, name, price, qty in cart:
        cur.execute("INSERT INTO order_items (order_id, item_id, quantity, price) VALUES (?, ?, ?, ?)",
                    (order_id, item_id, qty, price))
        # Deduct stock
        cur.execute("UPDATE items SET stock = stock - ? WHERE id = ?", (qty, item_id))

    conn.commit()
    conn.close()
    print(f"Order #{order_id} placed. Total: {total:.2f}")



def view_orders(limit=20):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM orders ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    if not rows:
        print("No orders found.")
        conn.close()
        return

    for r in rows:
        print(f"\nOrder ID: {r['id']}  Time: {r['created_at']}  Total: {r['total']:.2f}")
        cur.execute("SELECT oi.quantity, oi.price, it.name FROM order_items oi JOIN items it ON oi.item_id = it.id WHERE oi.order_id = ?", (r['id'],))
        items = cur.fetchall()
        table = [(it['name'], it['quantity'], f"{it['price']:.2f}", f"{it['quantity']*it['price']:.2f}") for it in items]
        print(tabulate(table, headers=["Name", "Qty", "Unit", "Line Total"]))

    conn.close()


def sales_report(start_date=None, end_date=None):
    
    conn = get_connection()
    cur = conn.cursor()
    sql = "SELECT * FROM orders WHERE 1=1"
    params = []
    if start_date:
        sql += " AND date(created_at) >= date(?)"
        params.append(start_date)
    if end_date:
        sql += " AND date(created_at) <= date(?)"
        params.append(end_date)
    sql += " ORDER BY created_at"

    cur.execute(sql, params)
    orders = cur.fetchall()
    total_sales = sum(o['total'] for o in orders)
    print(f"Found {len(orders)} orders. Total sales: {total_sales:.2f}")

    
    cur.execute('''
    SELECT it.name, SUM(oi.quantity) as qty_sold, SUM(oi.quantity * oi.price) as revenue
    FROM order_items oi
    JOIN orders o ON oi.order_id = o.id
    JOIN items it ON oi.item_id = it.id
    WHERE 1=1
    ''')
    
    if start_date or end_date:
        conds = []
        params = []
        if start_date:
            conds.append("date(o.created_at) >= date(?)")
            params.append(start_date)
        if end_date:
            conds.append("date(o.created_at) <= date(?)")
            params.append(end_date)
        where_clause = " AND " + " AND ".join(conds)
        query = '''
        SELECT it.name, SUM(oi.quantity) as qty_sold, SUM(oi.quantity * oi.price) as revenue
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        JOIN items it ON oi.item_id = it.id
        WHERE ''' + '1=1' + where_clause + '''
        GROUP BY it.name
        '''
        cur.execute(query, params)
    else:
        cur.execute('''
        SELECT it.name, SUM(oi.quantity) as qty_sold, SUM(oi.quantity * oi.price) as revenue
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.id
        JOIN items it ON oi.item_id = it.id
        GROUP BY it.name
        ''')

    rows = cur.fetchall()
    if rows:
        table = [(r['name'], r['qty_sold'], f"{r['revenue']:.2f}") for r in rows]
        print(tabulate(table, headers=["Item", "Qty Sold", "Revenue"]))
    else:
        print("No item sales in this range.")

    conn.close()



def export_orders_csv(filename='orders_export.csv'):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT * FROM orders ORDER BY id')
    orders = cur.fetchall()
    if not orders:
        print("No orders to export.")
        conn.close()
        return

    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['order_id', 'created_at', 'total', 'item_name', 'qty', 'unit_price'])
        for o in orders:
            cur.execute('SELECT oi.quantity, oi.price, it.name FROM order_items oi JOIN items it ON oi.item_id = it.id WHERE oi.order_id = ?', (o['id'],))
            items = cur.fetchall()
            for it in items:
                writer.writerow([o['id'], o['created_at'], o['total'], it['name'], it['quantity'], it['price']])

    conn.close()
    print(f"Exported orders to {filename}")



def admin_menu():
    while True:
        print('\n--- Admin Menu ---')
        print('1. Add item')
        print('2. Update item')
        print('3. Delete item')
        print('4. List items')
        print('5. Replenish stock')
        print('6. View orders')
        print('7. Sales report')
        print('8. Export orders to CSV')
        print('9. Back to main')
        ch = input('Choice: ').strip()
        if ch == '1':
            name = input('Item name: ').strip()
            price = float(input('Price: ').strip())
            stock = int(input('Stock: ').strip())
            add_item(name, price, stock)
        elif ch == '2':
            list_items(show_zero_stock=True)
            item_id = int(input('Enter item id to update: '))
            nm = input('New name (leave blank to keep): ').strip() or None
            pr = input('New price (leave blank to keep): ').strip()
            pr = float(pr) if pr else None
            st = input('New stock (leave blank to keep): ').strip()
            st = int(st) if st else None
            update_item(item_id, name=nm, price=pr, stock=st)
        elif ch == '3':
            list_items(show_zero_stock=True)
            item_id = int(input('Enter item id to delete: '))
            delete_item(item_id)
        elif ch == '4':
            list_items(show_zero_stock=True)
        elif ch == '5':
            list_items(show_zero_stock=True)
            item_id = int(input('Enter item id to replenish: '))
            qty = int(input('Quantity to add: '))
            conn = get_connection()
            cur = conn.cursor()
            cur.execute('UPDATE items SET stock = stock + ? WHERE id = ?', (qty, item_id))
            conn.commit()
            conn.close()
            print('Stock updated.')
        elif ch == '6':
            view_orders()
        elif ch == '7':
            sd = input('Start date (YYYY-MM-DD) or blank: ').strip() or None
            ed = input('End date (YYYY-MM-DD) or blank: ').strip() or None
            sales_report(sd, ed)
        elif ch == '8':
            fn = input('Filename (default orders_export.csv): ').strip() or 'orders_export.csv'
            export_orders_csv(fn)
        elif ch == '9':
            break
        else:
            print('Invalid choice.')


def main_menu():
    while True:
        print('\n=== Cafe Management System ===')
        print('1. Place Order')
        print('2. Admin Menu')
        print('3. Exit')
        ch = input('Choice: ').strip()
        if ch == '1':
            place_order()
        elif ch == '2':
            admin_menu()
        elif ch == '3':
            print('Goodbye!')
            break
        else:
            print('Invalid choice.')


if __name__ == '__main__':
    
    init_db()
    
    conn = get_connection()
    cur = conn.cursor()
    cur.execute('SELECT COUNT(*) as c FROM items')
    if cur.fetchone()['c'] == 0:
        sample = [
            ('Espresso', 60.0, 20),
            ('Cappuccino', 90.0, 20),
            ('Latte', 100.0, 20),
            ('Sandwich', 120.0, 15),
            ('Cold Coffee', 80.0, 15)
        ]
        cur.executemany('INSERT INTO items (name, price, stock) VALUES (?, ?, ?)', sample)
        conn.commit()
        print('Sample menu created.')
    conn.close()

    try:
        main_menu()
    except KeyboardInterrupt:
        print('\nExiting...')
