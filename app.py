import os
import json
import sqlite3
import random
import string
import csv
import io
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, abort, Response, jsonify, g
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = "super_secret_store_key_for_sessions"

# إعدادات رفع الملفات
UPLOAD_FOLDER = os.path.join('static', 'uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# إعدادات قاعدة البيانات
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'store.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# إعدادات تسجيل الدخول
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "يرجى تسجيل الدخول للوصول لهذه الصفحة"
login_manager.login_message_category = "warning"

# ==========================================
# هيكلة الجداول (Models) للمتجر الواحد
# ==========================================
class SystemConfig(db.Model):
    __tablename__ = 'system_config'
    id = db.Column(db.Integer, primary_key=True)
    is_active = db.Column(db.Boolean, default=True) 
    feature_cart = db.Column(db.Boolean, default=True)
    feature_coupons = db.Column(db.Boolean, default=True)
    feature_tracking = db.Column(db.Boolean, default=True)
    feature_products = db.Column(db.Boolean, default=True)

class WhitelistedIP(db.Model):
    __tablename__ = 'whitelisted_ips'
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20))
    whatsapp = db.Column(db.String(20))
    address = db.Column(db.Text)
    is_admin = db.Column(db.Boolean, default=False)
    is_superadmin = db.Column(db.Boolean, default=False)

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)

class Product(db.Model):
    __tablename__ = 'products'
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    name = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Float, nullable=False)
    discount_price = db.Column(db.Float, default=0)
    image = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=True)
    discount_end_date = db.Column(db.String(50))
    stock = db.Column(db.Integer, default=10)

class Order(db.Model):
    __tablename__ = 'orders'
    id = db.Column(db.Integer, primary_key=True)
    tracking_code = db.Column(db.String(50), unique=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    customer_name = db.Column(db.String(100), nullable=False)
    customer_phone = db.Column(db.String(20), nullable=False)
    customer_address = db.Column(db.Text, nullable=False)
    order_details = db.Column(db.Text, nullable=False)
    total_price = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(50), default='قيد المراجعة')
    cart_items_json = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Coupon(db.Model):
    __tablename__ = 'coupons'
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(50), unique=True, nullable=False)
    discount_type = db.Column(db.String(20), nullable=False)
    discount_value = db.Column(db.Float, nullable=False)
    start_date = db.Column(db.String(50))
    expiry_date = db.Column(db.String(50))
    valid_days = db.Column(db.String(100))
    target_type = db.Column(db.String(20), default='all')
    target_id = db.Column(db.Integer)
    min_order_value = db.Column(db.Float, default=0)
    is_active = db.Column(db.Boolean, default=True)

class Setting(db.Model):
    __tablename__ = 'settings'
    id = db.Column(db.Integer, primary_key=True)
    setting_key = db.Column(db.String(50), unique=True, nullable=False)
    setting_value = db.Column(db.Text)

# ==========================================
# تهيئة قاعدة البيانات 
# ==========================================
def setup_database():
    with app.app_context():
        db.create_all()
        
        if not SystemConfig.query.first():
            db.session.add(SystemConfig())
            db.session.commit()

        if not User.query.filter_by(is_superadmin=True).first():
            super_admin = User(
                name="Developer",
                email="dev@admin.com",
                password=generate_password_hash("dev123"), 
                is_admin=True,
                is_superadmin=True
            )
            db.session.add(super_admin)
            
        if not User.query.filter_by(email="admin@store.com").first():
            store_admin = User(
                name="المدير العام",
                email="admin@store.com",
                password=generate_password_hash("admin123"),
                phone="01000000000",
                address="الإدارة",
                is_admin=True
            )
            db.session.add(store_admin)

        if Setting.query.count() == 0:
            defaults = [("whatsapp", "201234567890"), ("phone", "201234567890"), ("instagram", "#"), ("tiktok", "#"), ("facebook", "#")]
            for key, val in defaults:
                db.session.add(Setting(setting_key=key, setting_value=val))
                
        db.session.commit()

setup_database()

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def generate_tracking_code():
    return "TRK-" + ''.join(random.choices(string.digits, k=5))

def get_client_ip():
    # لجلب الـ IP الحقيقي في حالة استخدام سيرفرات سحابية أو Proxies
    if request.headers.getlist("X-Forwarded-For"):
        return request.headers.getlist("X-Forwarded-For")[0].split(',')[0].strip()
    return request.remote_addr

# ==========================================
# Middleware: التحكم الكامل في حالة الموقع والـ IP
# ==========================================
@app.before_request
def check_site_status():
    config = SystemConfig.query.first()
    g.config = config
    
    # السماح للملفات الثابتة وصفحات تسجيل الدخول ولوحة المبرمج دائمًا
    if request.path.startswith('/static') or request.path in ['/login', '/logout', '/superadmin'] or request.path.startswith('/superadmin'):
        return

    # إذا كان الموقع متوقفاً
    if not config.is_active:
        client_ip = get_client_ip()
        is_whitelisted = WhitelistedIP.query.filter_by(ip_address=client_ip).first()
        
        # إذا لم يكن الـ IP في القائمة البيضاء، امنع الدخول
        if not is_whitelisted:
            return "<h1 style='text-align:center; margin-top:20%; color:red; font-family:sans-serif;'>الموقع متوقف حالياً لأعمال الصيانة أو من قبل الإدارة.</h1>", 403

@app.context_processor
def inject_settings():
    settings_query = Setting.query.all()
    settings = {s.setting_key: s.setting_value for s in settings_query}
    return dict(store_settings=settings, sys_config=g.config)

# ==========================================
# لوحة تحكم المبرمج (Super Admin)
# ==========================================
@app.route('/superadmin')
@login_required
def superadmin_dashboard():
    if not current_user.is_superadmin: abort(403)
    ips = WhitelistedIP.query.all()
    current_ip = get_client_ip()
    return render_template('superadmin.html', config=g.config, ips=ips, current_ip=current_ip)

@app.route('/superadmin/toggle/<feature_name>')
@login_required
def superadmin_toggle(feature_name):
    if not current_user.is_superadmin: abort(403)
    config = SystemConfig.query.first()
    if hasattr(config, feature_name):
        current_status = getattr(config, feature_name)
        setattr(config, feature_name, not current_status)
        db.session.commit()
        flash(f"تم تعديل الخاصية {feature_name} بنجاح!", "success")
    return redirect(url_for('superadmin_dashboard'))

@app.route('/superadmin/add_ip', methods=['POST'])
@login_required
def superadmin_add_ip():
    if not current_user.is_superadmin: abort(403)
    ip_address = request.form.get('ip_address', '').strip()
    description = request.form.get('description', '').strip()
    
    if ip_address:
        try:
            db.session.add(WhitelistedIP(ip_address=ip_address, description=description))
            db.session.commit()
            flash("تم إضافة عنوان الـ IP للقائمة البيضاء.", "success")
        except:
            db.session.rollback()
            flash("عنوان الـ IP مسجل بالفعل!", "error")
            
    return redirect(url_for('superadmin_dashboard'))

@app.route('/superadmin/delete_ip/<int:ip_id>')
@login_required
def superadmin_delete_ip(ip_id):
    if not current_user.is_superadmin: abort(403)
    ip_entry = WhitelistedIP.query.get_or_404(ip_id)
    db.session.delete(ip_entry)
    db.session.commit()
    flash("تم إزالة عنوان الـ IP من القائمة.", "success")
    return redirect(url_for('superadmin_dashboard'))

# ==========================================
# مسارات العميل (Customer Routes)
# ==========================================
def calculate_coupon_discount(code, cart_items, total_price):
    if not code: return False, " ", 0, total_price
    coupon = Coupon.query.filter_by(code=code).first()
    if not coupon or not coupon.is_active: return False, "الكوبون غير صالح!", 0, total_price
    
    now = datetime.now()
    current_time_str = now.strftime('%Y-%m-%dT%H:%M')
    current_day = str(now.weekday())
         
    if coupon.start_date and current_time_str < coupon.start_date: return False, "الكوبون لم يبدأ بعد!", 0, total_price
    if coupon.expiry_date and current_time_str > coupon.expiry_date: return False, "الكوبون منتهي!", 0, total_price
    if coupon.valid_days and current_day not in coupon.valid_days.split(','): return False, "الكوبون غير صالح اليوم!", 0, total_price
    if float(total_price) < float(coupon.min_order_value): return False, f"الحد الأدنى للطلب هو {coupon.min_order_value}!", 0, total_price
         
    eligible_total = 0; applicable = False
    for item in cart_items:
        prod_id = item['id']; qty = int(item['quantity']); price = float(item['price'])
        if coupon.target_type == 'all': eligible_total += (price * qty); applicable = True
        elif coupon.target_type == 'product' and str(prod_id) == str(coupon.target_id): eligible_total += (price * qty); applicable = True
        elif coupon.target_type == 'category':
            prod = Product.query.get(prod_id)
            if prod and str(prod.category_id) == str(coupon.target_id): eligible_total += (price * qty); applicable = True
         
    if not applicable or eligible_total == 0: return False, "الكوبون لا يشمل هذه المنتجات!", 0, total_price
    discount_amount = (eligible_total * float(coupon.discount_value)) / 100 if coupon.discount_type == "percent" else (float(coupon.discount_value) if float(coupon.discount_value) <= eligible_total else eligible_total)
    new_total = float(total_price) - float(discount_amount)
    return True, f"تم التطبيق بنجاح! (-{round(discount_amount, 2)})", discount_amount, new_total

@app.route("/api/validate_coupon", methods=["POST"])
def validate_coupon():
    if not g.config.feature_coupons:
        return jsonify({"valid": False, "message": "نظام الكوبونات مغلق حالياً."})
    data = request.get_json()
    is_valid, message, discount_amount, new_total = calculate_coupon_discount(data.get("code", "").strip().upper(), data.get("cart", []), float(data.get("total", 0)))
    return jsonify({"valid": is_valid, "message": message, "discount_amount": round(discount_amount, 2), "new_total": round(new_total, 2)})

@app.route("/")
def index():
    if not g.config.feature_products: 
        return "<h2 style='text-align:center; margin-top:10%;'>نظام عرض المنتجات مغلق حالياً من قبل المبرمج.</h2>"
        
    if current_user.is_authenticated and current_user.is_admin and request.args.get('view') != 'store':
        return redirect(url_for('superadmin_dashboard') if current_user.is_superadmin else url_for('admin_dashboard'))
             
    cat_id = request.args.get("category", type=int)
    categories = Category.query.all()
    
    if cat_id:
        products = Product.query.filter_by(category_id=cat_id).order_by(Product.id.desc()).all()
    else:
        products = Product.query.order_by(Product.id.desc()).all()
        
    return render_template("index.html", products=products, categories=categories, selected_cat=cat_id, current_time=datetime.now().strftime('%Y-%m-%dT%H:%M'))

@app.route("/cart")
def cart():
    if not g.config.feature_cart: return "<h2 style='text-align:center; margin-top:10%;'>خاصية سلة المشتريات والطلب مغلقة حالياً.</h2>"
    return render_template("cart.html")

@app.route("/checkout", methods=["POST"])
def checkout():
    if not g.config.feature_cart: abort(403)
    if current_user.is_authenticated and current_user.is_admin: abort(403)
    
    name = request.form.get("full_name") or (current_user.name if current_user.is_authenticated else None)
    phone = request.form.get("phone_number") or (current_user.whatsapp or current_user.phone if current_user.is_authenticated else None)
    address = request.form.get("address") or (current_user.address if current_user.is_authenticated else "")
    cart_data_str = request.form.get("cart_data")
    coupon_code = request.form.get("applied_coupon", "").strip().upper()
         
    if not name or not phone or not cart_data_str: flash("البيانات ناقصة.", "error"); return redirect(url_for("cart"))
    cart_items = json.loads(cart_data_str)
    if not cart_items: flash("السلة فارغة!", "error"); return redirect(url_for("cart"))
         
    total_price = sum(float(item['price']) * int(item['quantity']) for item in cart_items)
    discount_text = ""
    
    if coupon_code and g.config.feature_coupons:
        is_valid, msg, discount_amount, new_total = calculate_coupon_discount(coupon_code, cart_items, total_price)
        if is_valid: 
            total_price = new_total
            discount_text = f"\n | كود الخصم: {coupon_code} ( خصم: {round(discount_amount, 2)} )"
             
    order_summary_list = [f"  {item['name']} ( كمية: {item['quantity']}) - {float(item['price']) * int(item['quantity'])} " for item in cart_items]
    order_details_text = "\n".join(order_summary_list) + discount_text
    tracking_code = generate_tracking_code()
         
    try:
        for item in cart_items:
            qty = int(item['quantity'])
            prod_id = int(item['id'])
            product = Product.query.get(prod_id)
            if product and product.stock >= qty:
                product.stock -= qty
            else:
                db.session.rollback()
                flash(f"كمية '{item['name']}' غير كافية.", "error")
                return redirect(url_for("cart"))
                
        new_order = Order(
            tracking_code=tracking_code,
            user_id=current_user.id if current_user.is_authenticated else None,
            customer_name=name,
            customer_phone=phone,
            customer_address=address,
            order_details=order_details_text,
            total_price=float(total_price),
            cart_items_json=json.dumps(cart_items)
        )
        db.session.add(new_order)
        db.session.commit()
             
    except Exception as e:
        db.session.rollback()
        flash("حدث خطأ أثناء الطلب.", "error")
        return redirect(url_for("cart"))
        
    return render_template("success.html", tracking_code=tracking_code, name=name)

@app.route("/track", methods=["GET", "POST"])
def track_order():
    if not g.config.feature_tracking: return "<h2 style='text-align:center; margin-top:10%;'>خاصية تتبع الطلبات مغلقة حالياً.</h2>"
    if current_user.is_authenticated and current_user.is_admin: return redirect(url_for('admin_dashboard'))
        
    orders = []; searched = False
    if request.method == "POST":
        query = request.form.get("query", "").strip()
        searched = True
        orders = Order.query.filter((Order.tracking_code==query) | (Order.customer_phone.like(f"%{query}%"))).order_by(Order.created_at.desc()).all()
    elif current_user.is_authenticated:
        searched = True
        orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template("track.html", orders=orders, searched=searched)

# ==========================================
# المصادقة وملف المستخدم (Auth & Profile)
# ==========================================
@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        if current_user.is_superadmin: return redirect(url_for('superadmin_dashboard'))
        return redirect(url_for('admin_dashboard') if current_user.is_admin else url_for('index'))
        
    if request.method == "POST":
        hashed_password = generate_password_hash(request.form.get("password"))
        new_user = User(
            name=request.form.get("name"),
            email=request.form.get("email"),
            password=hashed_password,
            phone=request.form.get("phone"),
            whatsapp=request.form.get("whatsapp"),
            address=request.form.get("address"),
            is_admin=False,
            is_superadmin=False
        )
        try:
            db.session.add(new_user)
            db.session.commit()
            flash("تم إنشاء الحساب بنجاح.", "success")
            return redirect(url_for("login"))
        except:
            db.session.rollback()
            flash("البريد الإلكتروني مستخدم بالفعل!", "error")
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        if current_user.is_superadmin: return redirect(url_for('superadmin_dashboard'))
        return redirect(url_for('admin_dashboard') if current_user.is_admin else url_for('index'))
        
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        
        user = User.query.filter_by(email=email).first()
            
        if user and check_password_hash(user.password, password):
            login_user(user)
            if user.is_superadmin: return redirect(url_for('superadmin_dashboard'))
            return redirect(url_for('admin_dashboard') if user.is_admin else url_for('index'))
        else: 
            flash("بيانات الدخول خاطئة!", "error")
    return render_template("login.html")

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if current_user.is_superadmin: return redirect(url_for('superadmin_dashboard'))
    
    if request.method == "POST":
        if current_user.is_admin and "update_store_settings" in request.form:
            settings_data = {
                "whatsapp": request.form.get("store_whatsapp"),
                "phone": request.form.get("store_phone"),
                "instagram": request.form.get("store_instagram"),
                "tiktok": request.form.get("store_tiktok"),
                "facebook": request.form.get("store_facebook")
            }
            for key, val in settings_data.items():
                setting = Setting.query.filter_by(setting_key=key).first()
                if setting: setting.setting_value = val
            db.session.commit()
            flash("تم تحديث بيانات تواصل المتجر بنجاح!", "success")
        else:
            current_user.name = request.form.get("name")
            current_user.phone = request.form.get("phone")
            current_user.whatsapp = request.form.get("whatsapp")
            current_user.address = request.form.get("address")
            db.session.commit()
            flash("تم تحديث بياناتك الشخصية بنجاح!", "success")
        return redirect(url_for("profile"))
         
    user_orders = []
    admin_stats = {}
    if current_user.is_admin:
        admin_stats['total_products'] = Product.query.count()
        admin_stats['active_coupons'] = Coupon.query.filter_by(is_active=True).count()
    else:
        user_orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
             
    return render_template("profile.html", user_orders=user_orders, admin_stats=admin_stats)

@app.route("/logout")
@login_required
def logout(): 
    logout_user()
    return redirect(url_for("index"))

# ==========================================
# لوحة تحكم المتجر (Store Admin)
# ==========================================
@app.route("/admin")
@login_required
def admin_dashboard():
    if not current_user.is_admin or current_user.is_superadmin: abort(403)
    
    orders = Order.query.order_by(Order.created_at.desc()).all()
    stats_sales = sum(o.total_price for o in orders if o.status != 'ملغي')
    stats_orders = len(orders)
    stats_pending = len([o for o in orders if o.status == 'قيد المراجعة'])
    stats_users = User.query.filter_by(is_admin=False).count()
    
    return render_template("admin.html", orders=orders, active_tab="orders", stats={'sales':round(stats_sales,2), 'orders':stats_orders, 'pending':stats_pending, 'users':stats_users})

@app.route("/admin/invoice/<int:order_id>")
@login_required
def print_invoice(order_id):
    if not current_user.is_admin: abort(403)
    order = Order.query.get_or_404(order_id)
    return render_template("admin_invoice.html", order=order)

@app.route("/admin/update_status/<int:order_id>", methods=["POST"])
@login_required
def update_order_status(order_id):
    if not current_user.is_admin: abort(403)
    order = Order.query.get_or_404(order_id)
    order.status = request.form.get("status")
    db.session.commit()
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/export")
@login_required
def export_orders():
    if not current_user.is_admin: abort(403)
    orders = Order.query.order_by(Order.created_at.desc()).all()
    output = io.StringIO(); output.write('\ufeff'); writer = csv.writer(output); writer.writerow(["رقم الطلب", "كود التتبع", "اسم العميل", "رقم العميل", "العنوان", "التفاصيل", "الإجمالي", "الحالة", "التاريخ"])
    for ord in orders: writer.writerow([ord.id, ord.tracking_code, ord.customer_name, ord.customer_phone, ord.customer_address, ord.order_details.replace('\n', ' | '), ord.total_price, ord.status, ord.created_at])
    response = Response(output.getvalue(), mimetype="text/csv; charset=utf-8")
    response.headers["Content-Disposition"] = "attachment; filename=orders.csv"
    return response

@app.route("/admin/categories", methods=["GET", "POST"])
@login_required
def admin_categories():
    if not current_user.is_admin: abort(403)
    if request.method == "POST":
        try:
            new_cat = Category(name=request.form.get("name").strip())
            db.session.add(new_cat)
            db.session.commit()
        except:
            db.session.rollback()
            flash("القسم موجود مسبقاً!", "error")
        return redirect(url_for("admin_categories"))
    categories = Category.query.all()
    return render_template("admin_categories.html", categories=categories, active_tab="categories")

@app.route("/admin/categories/delete/<int:cat_id>", methods=["POST"])
@login_required
def delete_category(cat_id):
    if not current_user.is_admin: abort(403)
    cat = Category.query.get_or_404(cat_id)
    db.session.delete(cat)
    db.session.commit()
    return redirect(url_for("admin_categories"))

@app.route("/admin/coupons", methods=["GET", "POST"])
@login_required
def admin_coupons():
    if not current_user.is_admin: abort(403)
    if not g.config.feature_coupons: return "<h2 style='text-align:center;'>الكوبونات مغلقة من الإدارة العليا.</h2>", 403
    
    if request.method == "POST":
        try:
            new_coupon = Coupon(
                code=request.form.get("code", "").strip().upper(),
                discount_type=request.form.get("discount_type"),
                discount_value=float(request.form.get("discount_value") or 0),
                start_date=request.form.get("start_date") or None,
                expiry_date=request.form.get("expiry_date") or None,
                valid_days=",".join(request.form.getlist("valid_days")) if request.form.getlist("valid_days") else None,
                target_type=request.form.get("target_type") or 'all',
                target_id=int(request.form.get("target_product") or 0) if request.form.get("target_type")=='product' else int(request.form.get("target_category") or 0),
                min_order_value=float(request.form.get("min_order_value") or 0)
            )
            db.session.add(new_coupon)
            db.session.commit()
            flash("تم إضافة الكوبون!", "success")
        except:
            db.session.rollback()
            flash("الكود موجود مسبقاً!", "error")
        return redirect(url_for("admin_coupons"))
        
    coupons = Coupon.query.order_by(Coupon.id.desc()).all()
    categories = Category.query.all()
    products = Product.query.all()
    return render_template("admin_coupons.html", coupons=coupons, categories=categories, products=products, active_tab="coupons")

@app.route("/admin/coupons/delete/<int:coupon_id>", methods=["POST"])
@login_required
def delete_coupon(coupon_id):
    if not current_user.is_admin: abort(403)
    coupon = Coupon.query.get_or_404(coupon_id)
    db.session.delete(coupon)
    db.session.commit()
    return redirect(url_for("admin_coupons"))

@app.route("/admin/products", methods=["GET", "POST"])
@login_required
def admin_products():
    if not current_user.is_admin: abort(403)
    if not g.config.feature_products: return "<h2 style='text-align:center;'>المنتجات مغلقة من الإدارة العليا.</h2>", 403
    
    if request.method == "POST":
        file = request.files.get("image_file")
        img_path = request.form.get("image_url") or "https://via.placeholder.com/400"
        if file and allowed_file(file.filename):
            fn = f"{''.join(random.choices(string.ascii_lowercase, k=6))}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
            img_path = url_for('static', filename=f"uploads/{fn}")
            
        new_prod = Product(
            name=request.form.get("name"),
            price=float(request.form.get("price") or 0),
            discount_price=float(request.form.get("discount_price") or 0),
            image=img_path,
            description=request.form.get("description"),
            category_id=int(request.form.get("category_id")) if request.form.get("category_id") else None,
            discount_end_date=request.form.get("discount_end_date") or None,
            stock=int(request.form.get("stock") or 10)
        )
        db.session.add(new_prod)
        db.session.commit()
        flash("تم إضافة المنتج بنجاح!", "success")
        return redirect(url_for("admin_products"))
        
    products = Product.query.order_by(Product.id.desc()).all()
    categories = Category.query.all()
    return render_template("admin_products.html", products=products, categories=categories, active_tab="products")

@app.route("/admin/products/edit/<int:prod_id>", methods=["GET", "POST"])
@login_required
def admin_edit_product(prod_id):
    if not current_user.is_admin: abort(403)
    product = Product.query.get_or_404(prod_id)
    
    if request.method == "POST":
        file = request.files.get("image_file")
        img_path = request.form.get("image_url")
        if file and allowed_file(file.filename):
            fn = f"{''.join(random.choices(string.ascii_lowercase, k=6))}_{secure_filename(file.filename)}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], fn))
            img_path = url_for('static', filename=f"uploads/{fn}")
            
        product.name = request.form.get("name")
        product.price = float(request.form.get("price") or 0)
        product.discount_price = float(request.form.get("discount_price") or 0)
        if img_path: product.image = img_path
        product.description = request.form.get("description")
        product.category_id = int(request.form.get("category_id")) if request.form.get("category_id") else None
        product.discount_end_date = request.form.get("discount_end_date") or None
        product.stock = int(request.form.get("stock") or 0)
        
        db.session.commit()
        flash("تم التعديل بنجاح!", "success")
        return redirect(url_for("admin_products"))
        
    categories = Category.query.all()
    return render_template("admin_edit_product.html", product=product, categories=categories, active_tab="products")

@app.route("/admin/products/delete/<int:prod_id>", methods=["POST"])
@login_required
def delete_product(prod_id):
    if not current_user.is_admin: abort(403)
    product = Product.query.get_or_404(prod_id)
    db.session.delete(product)
    db.session.commit()
    return redirect(url_for("admin_products"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=4000)