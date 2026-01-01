from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email_or_phone = db.Column(db.String(100), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='customer') # 'admin' or 'customer'
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=True)
    customer = db.relationship('Customer', backref='user_account', uselist=False)

class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=True)
    rate_per_liter = db.Column(db.Float, nullable=False, default=50.0)
    route_priority = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    attendance = db.relationship('Attendance', backref='customer', lazy=True)
    bills = db.relationship('Billing', backref='customer', lazy=True)

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow().date)
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    morning_liters = db.Column(db.Float, default=0.0)
    evening_liters = db.Column(db.Float, default=0.0)
    total_liters = db.Column(db.Float, default=0.0)

    __table_args__ = (db.UniqueConstraint('date', 'customer_id', name='_date_customer_uc'),)

class Billing(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    month = db.Column(db.String(20), nullable=False) # e.g., '2023-10'
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'), nullable=False)
    total_liters = db.Column(db.Float, default=0.0)
    total_amount = db.Column(db.Float, default=0.0)
    paid_amount = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='Due') # 'Paid', 'Partial', 'Due'
    pdf_path = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    payments = db.relationship('Payment', backref='billing', lazy=True)

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    billing_id = db.Column(db.Integer, db.ForeignKey('billing.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    mode = db.Column(db.String(50), nullable=False) # 'Cash', 'UPI', 'Online'
    date = db.Column(db.DateTime, default=datetime.utcnow)


