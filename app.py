import os
import json
import sqlite3
import random
import string
import csv
import io
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, abort, Response, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "super_secret_store_key_for_sessions"

UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

MERCHANT_PHONE = "201234567890"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "يرجى تسجيل الدخول للوصول إلى هذه الصفحة."
login_manager.login_message_category = "warning"

class User(UserMixin):
    def __init__(self, id, name, email, phone, whatsapp, address, is_admin=0):
        self.id = id
        self.name = name
        self.email = email
        self.phone = phone
        self.whatsapp = whatsapp
        self.address = address
        self.is_admin = bool(is_admin)

# =========================================================================
# --- حل مشكلة التزامن (Concurrency Fixes) ---
# =========================================================================
def get_db_connection():
    """
    إنشاء اتصال بقاعدة البيانات مع تفعيل وضع WAL و Timeout
    لتجنب مشكلة database is locked عند الضغط العالي
    """
    conn = sqlite3.connect("store.db", timeout=20.0) # الانتظار 20 ثانية في طابور الكتابة بدل الفشل
    conn.execute("PRAGMA journal_mode=WAL;") # تفعيل Write-Ahead Logging للقراءة والكتابة المتزامنة
    conn.execute("PRAGMA busy_timeout=20000;")
    return conn

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email, phone, whatsapp, address, is_admin FROM users WHERE id = ?", (user_id,))
    u = cursor.fetchone()
    conn.close()
    if u: return User(id=u[0], name=u[1], email=u[2], phone=u[3], whatsapp=u[4], address=u[5], is_admin=u[6])
    return None

def generate_tracking_code():
    return "TRK-" + ''.join(random.choices(string.digits, k=5))

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)")
    cursor.execute("CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, price REAL NOT NULL, discount_price REAL DEFAULT 0, image TEXT NOT NULL, description TEXT, category_id INTEGER, discount_end_date TEXT, stock INTEGER DEFAULT 10, FOREIGN KEY(category_id) REFERENCES categories(id))")
    cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, email TEXT UNIQUE NOT NULL, password TEXT NOT NULL, phone TEXT, whatsapp TEXT, address TEXT, is_admin INTEGER DEFAULT 0)")
    cursor.execute("CREATE TABLE IF NOT EXISTS orders (id INTEGER PRIMARY KEY AUTOINCREMENT, tracking_code TEXT UNIQUE, user_id INTEGER, customer_name TEXT NOT NULL, customer_phone TEXT NOT NULL, customer_address TEXT NOT NULL, order_details TEXT NOT NULL, total_price REAL NOT NULL, status TEXT DEFAULT 'قيد المراجعة', cart_items_json TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cursor.execute("CREATE TABLE IF NOT EXISTS coupons (id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT UNIQUE NOT NULL, discount_type TEXT NOT NULL, discount_value REAL NOT NULL, start_date TEXT, expiry_date TEXT, valid_days TEXT, target_type TEXT DEFAULT 'all', target_id INTEGER, min_order_value REAL DEFAULT 0, is_active INTEGER DEFAULT 1)")
    
    try: cursor.execute("ALTER TABLE products ADD COLUMN discount_end_date TEXT")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE products ADD COLUMN stock INTEGER DEFAULT 10")
    except sqlite3.OperationalError: pass
    try: cursor.execute("ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    for col, col_type in [("tracking_code", "TEXT UNIQUE"), ("customer_address", "TEXT"), ("status", "TEXT DEFAULT 'قيد المراجعة'"), ("cart_items_json", "TEXT")]:
        try: cursor.execute(f"ALTER TABLE orders ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError: pass
    for col, col_type in [("start_date", "TEXT"), ("valid_days", "TEXT"), ("target_type", "TEXT DEFAULT 'all'"), ("target_id", "INTEGER"), ("min_order_value", "REAL DEFAULT 0")]:
        try: cursor.execute(f"ALTER TABLE coupons ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError: pass
        
    cursor.execute("SELECT COUNT(*) FROM users WHERE email = 'admin@store.com'")
    if cursor.fetchone()[0] == 0:
        admin_pass = generate_password_hash("admin123")
        # تم تصحيح الخطأ هنا: إضافة 7 علامات استفهام لتناسب الـ 7 قيم الممررة
        cursor.execute("INSERT INTO users (name, email, password, phone, whatsapp, address, is_admin) VALUES (?, ?, ?, ?, ?, ?, ?)", ("المدير العام", "admin@store.com", admin_pass, "01000000000", "01000000000", "المقر الرئيسي", 1))
    conn.commit()
    conn.close()

init_db()

def calculate_coupon_discount(code, cart_items, total_price):
    if not code: return False, "لم يتم إدخال كود", 0, total_price
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT discount_type, discount_value, start_date, expiry_date, valid_days, target_type, target_id, min_order_value, is_active FROM coupons WHERE code = ?", (code,))
    coupon = cursor.fetchone()
    if not coupon or not coupon[8]: conn.close(); return False, "الكوبون غير صالح أو غير مفعل!", 0, total_price
    discount_type, discount_value, start_date, expiry_date, valid_days, target_type, target_id, min_order_value, _ = coupon
    now = datetime.now()
    current_time_str = now.strftime('%Y-%m-%dT%H:%M')
    current_day = str(now.weekday())
    
    if start_date and current_time_str < start_date: conn.close(); return False, "هذا الكوبون لم يبدأ بعد!", 0, total_price
    if expiry_date and current_time_str > expiry_date: conn.close(); return False, "هذا الكوبون منتهي الصلاحية!", 0, total_price
    if valid_days and current_day not in valid_days.split(','): conn.close(); return False, "الكوبون غير صالح اليوم!", 0, total_price
    if float(total_price) < float(min_order_value): conn.close(); return False, f"الحد الأدنى لتطبيق الكوبون هو {min_order_value} ج.م!", 0, total_price
    
    eligible_total = 0; applicable = False
    for item in cart_items:
        prod_id = item['id']; qty = int(item['quantity']); price = float(item['price'])
        if target_type == 'all': eligible_total += (price * qty); applicable = True
        elif target_type == 'product' and str(prod_id) == str(target_id): eligible_total += (price * qty); applicable = True
        elif target_type == 'category':
            cursor.execute("SELECT category_id FROM products WHERE id=?", (prod_id,))
            res = cursor.fetchone()
            if res and str(res[0]) == str(target_id): eligible_total += (price * qty); applicable = True
    conn.close()
    
    if not applicable or eligible_total == 0: return False, "الكوبون لا ينطبق على المنتجات في سلتك!", 0, total_price
    discount_amount = (eligible_total * float(discount_value)) / 100 if discount_type == "percent" else (float(discount_value) if float(discount_value) <= eligible_total else eligible_total)
    new_total = float(total_price) - float(discount_amount)
    return True, f"تم تطبيق الخصم بنجاح! (-{round(discount_amount, 2)} ج.م)", discount_amount, new_total

@app.route("/api/validate_coupon", methods=["POST"])
def validate_coupon():
    data = request.get_json()
    is_valid, message, discount_amount, new_total = calculate_coupon_discount(data.get("code", "").strip().upper(), data.get("cart", []), float(data.get("total", 0)))
    return jsonify({"valid": is_valid, "message": message, "discount_amount": round(discount_amount, 2), "new_total": round(new_total, 2)})

@app.route("/api/get_order_items/<tracking_code>")
def get_order_items(tracking_code):
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT cart_items_json FROM orders WHERE tracking_code = ?", (tracking_code,))
    res = cursor.fetchone(); conn.close()
    if res and res[0]: return jsonify({"success": True, "items": json.loads(res[0])})
    return jsonify({"success": False})

@app.route("/")
def index():
    if current_user.is_authenticated and current_user.is_admin and request.args.get('view') != 'store':
        return redirect(url_for('admin_dashboard'))
        
    cat_id = request.args.get("category", type=int)
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT * FROM categories"); categories = cursor.fetchall()
    query = "SELECT p.id, p.name, p.price, p.discount_price, p.image, p.description, p.category_id, p.discount_end_date, p.stock, c.name as cat_name FROM products p LEFT JOIN categories c ON p.category_id = c.id"
    if cat_id: cursor.execute(query + " WHERE p.category_id = ? ORDER BY p.id DESC", (cat_id,))
    else: cursor.execute(query + " ORDER BY p.id DESC")
    products = cursor.fetchall(); conn.close()
    return render_template("index.html", products=products, categories=categories, selected_cat=cat_id, current_time=datetime.now().strftime('%Y-%m-%dT%H:%M'))

@app.route("/cart")
def cart():
    if current_user.is_authenticated and current_user.is_admin:
        flash("عفواً، لا يمكن للمدير استخدام سلة المشتريات.", "warning")
        return redirect(url_for('admin_dashboard'))
    return render_template("cart.html")

# =========================================================================
# --- كود الـ Checkout المعدل (المضاد لتداخل الـ 100 أوردر) ---
# =========================================================================
@app.route("/checkout", methods=["POST"])
def checkout():
    if current_user.is_authenticated and current_user.is_admin: abort(403)
    name = request.form.get("full_name") or (current_user.name if current_user.is_authenticated else None)
    phone = request.form.get("phone_number") or (current_user.whatsapp or current_user.phone if current_user.is_authenticated else None)
    address = request.form.get("address") or (current_user.address if current_user.is_authenticated else "عنوان غير محدد")
    cart_data_str = request.form.get("cart_data")
    coupon_code = request.form.get("applied_coupon", "").strip().upper()
    
    if not name or not phone or not cart_data_str: flash("يرجى إكمال جميع البيانات المطلوبة.", "error"); return redirect(url_for("cart"))
    cart_items = json.loads(cart_data_str)
    if not cart_items: flash("سلة المشتريات فارغة!", "error"); return redirect(url_for("cart"))
    
    total_price = sum(float(item['price']) * int(item['quantity']) for item in cart_items)
    discount_text = ""
    if coupon_code:
        is_valid, msg, discount_amount, new_total = calculate_coupon_discount(coupon_code, cart_items, total_price)
        if is_valid: total_price = new_total; discount_text = f"\n | كود الخصم: {coupon_code} (خصم: {round(discount_amount, 2)} ج.م)"
        
    order_summary_list = [f"• {item['name']} (الكمية: {item['quantity']}) - {float(item['price']) * int(item['quantity'])} ج.م" for item in cart_items]
    order_details_text = "\n".join(order_summary_list) + discount_text
    tracking_code = generate_tracking_code()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    try:
        # 1. بدء المعاملة الفورية (BEGIN IMMEDIATE) لحجز قفل الكتابة ومنع التداخل
        cursor.execute("BEGIN IMMEDIATE")
        
        # 2. خصم المخزون بشكل ذكي (Atomic Decrement) لكل منتج
        for item in cart_items:
            qty = int(item['quantity'])
            prod_id = int(item['id'])
            
            # الشرط AND stock >= ? يضمن عدم البيع إذا كان المخزون أقل من المطلوب
            cursor.execute("UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= ?", (qty, prod_id, qty))
            
            # إذا لم يتم تعديل أي صف (rowcount == 0)، فهذا يعني أن الكمية نفدت في هذه اللحظة!
            if cursor.rowcount == 0:
                cursor.execute("SELECT stock FROM products WHERE id = ?", (prod_id,))
                res = cursor.fetchone()
                rem_stock = res[0] if res else 0
                
                conn.rollback()
                flash(f"عفواً! المنتج '{item['name']}' نفدت كميته أو المتبقي منه ({rem_stock} قطع) لا يكفي لطلبك.", "error")
                return redirect(url_for("cart"))

        # 3. إذا نجح خصم المخزون لكل المنتجات، يتم تسجيل الأوردر بأمان
        cursor.execute("INSERT INTO orders (tracking_code, user_id, customer_name, customer_phone, customer_address, order_details, total_price, status, cart_items_json) VALUES (?, ?, ?, ?, ?, ?, ?, 'قيد المراجعة', ?)",
                        (tracking_code, current_user.id if current_user.is_authenticated else None, name, phone, address, order_details_text, float(total_price), json.dumps(cart_items)))
        
        # 4. حفظ التغييرات نهائياً
        conn.commit()
        
    except sqlite3.OperationalError as e:
        conn.rollback()
        flash("حدث ضغط عالٍ جداً على النظام في هذه اللحظة، يرجى المحاولة مرة أخرى بعد ثوانٍ.", "error")
        return redirect(url_for("cart"))
    finally:
        conn.close()

    return render_template("success.html", tracking_code=tracking_code, name=name)

@app.route("/track", methods=["GET", "POST"])
def track_order():
    if current_user.is_authenticated and current_user.is_admin:
        return redirect(url_for('admin_dashboard'))
    orders = []; searched = False
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        searched = True
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("SELECT tracking_code, customer_name, order_details, total_price, status, created_at FROM orders WHERE tracking_code = ? OR customer_phone LIKE ? ORDER BY created_at DESC", (query, f"%{query}%"))
        orders = cursor.fetchall(); conn.close()
    elif current_user.is_authenticated:
        searched = True
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("SELECT tracking_code, customer_name, order_details, total_price, status, created_at FROM orders WHERE user_id = ? ORDER BY created_at DESC", (current_user.id,))
        orders = cursor.fetchall(); conn.close()
    return render_template("track.html", orders=orders, searched=searched)

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated: return redirect(url_for('admin_dashboard') if current_user.is_admin else url_for('index'))
    if request.method == "POST":
        hashed_password = generate_password_hash(request.form.get("password"))
        conn = get_db_connection(); cursor = conn.cursor()
        try:
            cursor.execute("INSERT INTO users (name, email, password, phone, whatsapp, address, is_admin) VALUES (?, ?, ?, ?, ?, ?, 0)", (request.form.get("name"), request.form.get("email"), hashed_password, request.form.get("phone"), request.form.get("whatsapp"), request.form.get("address")))
            conn.commit(); flash("تم إنشاء حسابك بنجاح! يمكنك تسجيل الدخول الآن.", "success"); return redirect(url_for("login"))
        except: flash("هذا البريد الإلكتروني مسجل لدينا بالفعل!", "error")
        finally: conn.close()
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated: return redirect(url_for('admin_dashboard') if current_user.is_admin else url_for('index'))
    if request.method == "POST":
        conn = get_db_connection(); cursor = conn.cursor()
        cursor.execute("SELECT id, name, email, password, phone, whatsapp, address, is_admin FROM users WHERE email = ?", (request.form.get("email"),))
        u = cursor.fetchone(); conn.close()
        if u and check_password_hash(u[3], request.form.get("password")):
            login_user(User(id=u[0], name=u[1], email=u[2], phone=u[4], whatsapp=u[5], address=u[6], is_admin=u[7]))
            if u[7]:
                flash(f"أهلاً بك يا {u[1]} في لوحة التحكم", "success")
                return redirect(url_for("admin_dashboard"))
            flash(f"أهلاً بك مجدداً يا {u[1]}!", "success")
            return redirect(url_for("index"))
        else: flash("بيانات الدخول غير صحيحة!", "error")
    return render_template("login.html")

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    conn = get_db_connection(); cursor = conn.cursor()
    if request.method == "POST":
        cursor.execute("UPDATE users SET name=?, phone=?, whatsapp=?, address=? WHERE id=?", (request.form.get("name"), request.form.get("phone"), request.form.get("whatsapp"), request.form.get("address"), current_user.id))
        conn.commit(); flash("تم تحديث بياناتك بنجاح!", "success"); return redirect(url_for("profile"))
    
    user_orders = []
    admin_stats = {}
    
    if current_user.is_admin:
        cursor.execute("SELECT COUNT(*) FROM products")
        admin_stats['total_products'] = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM coupons WHERE is_active=1")
        admin_stats['active_coupons'] = cursor.fetchone()[0]
    else:
        cursor.execute("SELECT tracking_code, order_details, total_price, status, created_at FROM orders WHERE user_id = ? ORDER BY created_at DESC", (current_user.id,))
        user_orders = cursor.fetchall()
        
    conn.close()
    return render_template("profile.html", user_orders=user_orders, admin_stats=admin_stats)

@app.route("/logout")
@login_required
def logout(): logout_user(); return redirect(url_for("index"))

# =========================================================================
# --- لوحة تحكم الإدارة (Admin Dashboard) ---
# =========================================================================
@app.route("/admin")
@login_required
def admin_dashboard():
    if not current_user.is_admin: abort(403)
    conn = get_db_connection(); cursor = conn.cursor()
    cursor.execute("SELECT SUM(total_price) FROM orders WHERE status != 'ملغي'"); stats_sales = cursor.fetchone()[0] or 0
    cursor.execute("SELECT COUNT(*) FROM orders"); stats_orders = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM orders WHERE status = 'قيد المراجعة'"); stats_pending = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE is_admin = 0"); stats_users = cursor.fetchone()[0]
    cursor.execute("SELECT id, tracking_code, customer_name, customer_phone, customer_address, order_details, total_price, status, created_at FROM orders ORDER BY created_at DESC")
    orders = cursor.fetchall(); conn.close()
    return render_template("admin.html", orders=orders, active_tab="orders", stats={'sales':round(stats_sales,2), 'orders':stats_orders, 'pending':stats_pending, 'users':stats_users})

@app.route("/admin/invoice/<int:order_id>")
@login_required
def print_invoice(order_id):
    if not current_user.is_admin: abort(403)
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("SELECT id, tracking_code, customer_name, customer_phone, customer_address, order_details, total_price, status, created_at FROM orders WHERE id = ?", (order_id,)); order = cursor.fetchone(); conn.close()
    if not order: abort(404)
    return render_template("admin_invoice.html", order=order)

@app.route("/admin/update_status/<int:order_id>", methods=["POST"])
@login_required
def update_order_status(order_id):
    if not current_user.is_admin: abort(403)
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("UPDATE orders SET status = ? WHERE id = ?", (request.form.get("status"), order_id)); conn.commit(); conn.close(); return redirect(url_for("admin_dashboard"))

@app.route("/admin/export")
@login_required
def export_orders():
    if not current_user.is_admin: abort(403)
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("SELECT * FROM orders ORDER BY created_at DESC"); orders = cursor.fetchall(); conn.close()
    output = io.StringIO(); output.write('\ufeff'); writer = csv.writer(output); writer.writerow(["رقم التعريف", "كود التتبع", "معرف العميل", "اسم العميل", "رقم الهاتف", "العنوان", "تفاصيل الأوردر", "الإجمالي", "الحالة", "تاريخ الطلب"])
    for ord in orders: writer.writerow([ord[0], ord[1], ord[2], ord[3], ord[4], ord[5], ord[6].replace('\n', ' | '), ord[7], ord[8], ord[9]])
    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8"); response.headers["Content-Disposition"] = "attachment; filename=orders.csv"; return response

@app.route("/admin/coupons", methods=["GET", "POST"])
@login_required
def admin_coupons():
    if not current_user.is_admin: abort(403)
    conn = get_db_connection(); cursor = conn.cursor()
    if request.method == "POST":
        code = request.form.get("code", "").strip().upper()
        try:
            cursor.execute("INSERT INTO coupons (code, discount_type, discount_value, start_date, expiry_date, valid_days, target_type, target_id, min_order_value) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            (code, request.form.get("discount_type"), float(request.form.get("discount_value") or 0), request.form.get("start_date") or None, request.form.get("expiry_date") or None, ",".join(request.form.getlist("valid_days")) if request.form.getlist("valid_days") else None, request.form.get("target_type") or 'all', int(request.form.get("target_product") or 0) if request.form.get("target_type")=='product' else int(request.form.get("target_category") or 0), float(request.form.get("min_order_value") or 0)))
            conn.commit(); flash("تم إضافة الكوبون المتقدم بنجاح!", "success")
        except sqlite3.IntegrityError: flash("كود الكوبون مسجل مسبقاً!", "error")
        return redirect(url_for("admin_coupons"))
    cursor.execute("SELECT * FROM coupons ORDER BY id DESC"); coupons = cursor.fetchall(); cursor.execute("SELECT id, name FROM categories"); categories = cursor.fetchall(); cursor.execute("SELECT id, name FROM products"); products = cursor.fetchall(); conn.close()
    return render_template("admin_coupons.html", coupons=coupons, categories=categories, products=products, active_tab="coupons")

@app.route("/admin/coupons/delete/<int:coupon_id>", methods=["POST"])
@login_required
def delete_coupon(coupon_id):
    if not current_user.is_admin: abort(403)
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("DELETE FROM coupons WHERE id = ?", (coupon_id,)); conn.commit(); conn.close(); return redirect(url_for("admin_coupons"))

@app.route("/admin/categories", methods=["GET", "POST"])
@login_required
def admin_categories():
    if not current_user.is_admin: abort(403)
    conn = get_db_connection(); cursor = conn.cursor()
    if request.method == "POST":
        try: cursor.execute("INSERT INTO categories (name) VALUES (?)", (request.form.get("name").strip(),)); conn.commit()
        except: flash("هذا القسم موجود بالفعل!", "error")
        return redirect(url_for("admin_categories"))
    cursor.execute("SELECT * FROM categories"); categories = cursor.fetchall(); conn.close()
    return render_template("admin_categories.html", categories=categories, active_tab="categories")

@app.route("/admin/categories/delete/<int:cat_id>", methods=["POST"])
@login_required
def delete_category(cat_id):
    if not current_user.is_admin: abort(403)
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("DELETE FROM categories WHERE id = ?", (cat_id,)); conn.commit(); conn.close(); return redirect(url_for("admin_categories"))

@app.route("/admin/products", methods=["GET", "POST"])
@login_required
def admin_products():
    if not current_user.is_admin: abort(403)
    conn = get_db_connection(); cursor = conn.cursor()
    if request.method == "POST":
        file = request.files.get("image_file"); img_path = request.form.get("image_url") or "https://via.placeholder.com/400"
        if file and allowed_file(file.filename):
            fn = f"{''.join(random.choices(string.ascii_lowercase, k=6))}_{secure_filename(file.filename)}"; file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn)); img_path = url_for('static', filename=f"uploads/{fn}")
        cursor.execute("INSERT INTO products (name, price, discount_price, image, description, category_id, discount_end_date, stock) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (request.form.get("name"), float(request.form.get("price") or 0), float(request.form.get("discount_price") or 0), img_path, request.form.get("description"), int(request.form.get("category_id")) if request.form.get("category_id") else None, request.form.get("discount_end_date") or None, int(request.form.get("stock") or 10)))
        conn.commit(); flash("تمت إضافة المنتج بنجاح!", "success"); return redirect(url_for("admin_products"))
    cursor.execute("SELECT p.id, p.name, p.price, p.discount_price, p.image, p.description, p.category_id, p.discount_end_date, p.stock, c.name FROM products p LEFT JOIN categories c ON p.category_id = c.id ORDER BY p.id DESC"); products = cursor.fetchall()
    cursor.execute("SELECT * FROM categories"); categories = cursor.fetchall(); conn.close()
    return render_template("admin_products.html", products=products, categories=categories, active_tab="products")

@app.route("/admin/products/edit/<int:prod_id>", methods=["GET", "POST"])
@login_required
def admin_edit_product(prod_id):
    if not current_user.is_admin: abort(403)
    conn = get_db_connection(); cursor = conn.cursor()
    if request.method == "POST":
        cursor.execute("SELECT image FROM products WHERE id=?", (prod_id,)); old_img = cursor.fetchone()[0]
        file = request.files.get("image_file"); img_path = request.form.get("image_url")
        if file and allowed_file(file.filename):
            fn = f"{''.join(random.choices(string.ascii_lowercase, k=6))}_{secure_filename(file.filename)}"; file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn)); img_path = url_for('static', filename=f"uploads/{fn}")
        cursor.execute("UPDATE products SET name=?, price=?, discount_price=?, image=?, description=?, category_id=?, discount_end_date=?, stock=? WHERE id=?",
                        (request.form.get("name"), float(request.form.get("price") or 0), float(request.form.get("discount_price") or 0), img_path or old_img, request.form.get("description"), int(request.form.get("category_id")) if request.form.get("category_id") else None, request.form.get("discount_end_date") or None, int(request.form.get("stock") or 0), prod_id))
        conn.commit(); conn.close(); flash("تم تحديث المنتج بنجاح!", "success"); return redirect(url_for("admin_products"))
    cursor.execute("SELECT * FROM products WHERE id = ?", (prod_id,)); product = cursor.fetchone()
    cursor.execute("SELECT * FROM categories"); categories = cursor.fetchall(); conn.close()
    return render_template("admin_edit_product.html", product=product, categories=categories, active_tab="products")

@app.route("/admin/products/delete/<int:prod_id>", methods=["POST"])
@login_required
def delete_product(prod_id):
    if not current_user.is_admin: abort(403)
    conn = get_db_connection(); cursor = conn.cursor(); cursor.execute("DELETE FROM products WHERE id = ?", (prod_id,)); conn.commit(); conn.close(); return redirect(url_for("admin_products"))

if __name__ == "__main__":
    app.run(host="0.0.0.0" , debug=True, port=4000)