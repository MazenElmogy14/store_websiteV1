from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Store(db.Model):
    __tablename__ = 'stores'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    domain_name = db.Column(db.String(150), unique=True, nullable=False)
    
    # بيانات دخول أدمن الموقع
    admin_username = db.Column(db.String(100), nullable=False)
    admin_password = db.Column(db.String(255), nullable=False)
    
    # أزرار التحكم في الخصائص (Feature Flags)
    feature_cart_enabled = db.Column(db.Boolean, default=True)
    feature_coupons_enabled = db.Column(db.Boolean, default=True)
    feature_reviews_enabled = db.Column(db.Boolean, default=True)
    feature_tracking_enabled = db.Column(db.Boolean, default=True)
    
    # حالة المتجر (شغال أو موقوف)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # العلاقات مع الجداول الأخرى
    products = db.relationship('Product', backref='store', lazy=True, cascade="all, delete-orphan")
    categories = db.relationship('Category', backref='store', lazy=True, cascade="all, delete-orphan")

class Category(db.Model):
    __tablename__ = 'categories'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)

class Product(db.Model):
    __tablename__ = 'products'
    
    id = db.Column(db.Integer, primary_key=True)
    store_id = db.Column(db.Integer, db.ForeignKey('stores.id'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id'), nullable=True)
    
    title = db.Column(db.String(150), nullable=False)
    price = db.Column(db.Float, nullable=False)
    description = db.Column(db.Text, nullable=True)
    image_file = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)