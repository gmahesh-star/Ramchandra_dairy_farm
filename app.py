import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify, send_file
import io
try:
    from weasyprint import HTML
except OSError:
    print("WARNING: WeasyPrint requires GTK. PDF generation may fail.")
    HTML = None
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
from models import db, User, Customer, Attendance, Billing, Payment
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dairy-secret-key-123')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///dairy.db')
if app.config['SQLALCHEMY_DATABASE_URI'].startswith("postgres://"):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)

db.init_app(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_datetime():
    return {'datetime': datetime}

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('Admin access required.', 'error')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- AUTH ROUTES ---

@app.route('/guest')
def guest():
    return render_template('guest.html')

@app.route('/farm')
def farm():
    return render_template('farm.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('identifier')
        password = request.form.get('password')
        user = User.query.filter_by(email_or_phone=identifier).first()
        
        if user and check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            flash('show_welcome_animation', 'animation')
            if user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('customer_dashboard'))
        
        flash('Invalid credentials.', 'error')
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        identifier = request.form.get('identifier') # email or phone
        password = request.form.get('password')
        
        # Check if customer exists in dairy records
        customer = Customer.query.filter((Customer.phone == identifier) | (Customer.email == identifier)).first()
        
        if not customer:
            flash('Your number is not registered with this dairy. Please contact the owner.', 'error')
            return redirect(url_for('signup'))
        
        # Check if user already has an account
        existing_user = User.query.filter_by(email_or_phone=identifier).first()
        if existing_user:
            flash('Account already exists. Please login.', 'info')
            return redirect(url_for('login'))
        
        # Create new user
        new_user = User(
            email_or_phone=identifier,
            password_hash=generate_password_hash(password),
            role='customer',
            customer_id=customer.id
        )
        db.session.add(new_user)
        db.session.commit()
        
        flash('Account created! You can now login.', 'success')
        return redirect(url_for('login'))
        
    return render_template('signup.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

# --- ADMIN ROUTES ---

@app.route('/admin')
@admin_required
def admin_dashboard():
    date_str = request.args.get('date')
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            target_date = date.today()
    else:
        target_date = date.today()

    customers_count = Customer.query.count()
    
    # Get attendance for the target date
    attendance = Attendance.query.filter_by(date=target_date).all()
    morning_total = sum(a.morning_liters for a in attendance)
    evening_total = sum(a.evening_liters for a in attendance)
    
    # Calculate daily sales (Revenue)
    daily_revenue = 0
    for a in attendance:
        customer = Customer.query.get(a.customer_id)
        if customer:
            daily_revenue += a.total_liters * customer.rate_per_liter
            
    return render_template('admin/dashboard.html', 
                           customers_count=customers_count,
                           morning_total=morning_total,
                           evening_total=evening_total,
                           daily_revenue=round(daily_revenue, 2),
                           selected_date=target_date)

@app.route('/admin/customers', methods=['GET', 'POST'])
@admin_required
def manage_customers():
    if request.method == 'POST':
        name = request.form.get('name')
        phone = request.form.get('phone')
        email = request.form.get('email')
        rate = request.form.get('rate')
        
        # FIX: SQLite considers "" as a value, so multiple empty emails fail UNIQUE constraint.
        # Use None (NULL in DB) for empty fields.
        email = email.strip() if email else None
        if email == "": email = None
        
        # Check if phone already exists to give a better error message
        existing = Customer.query.filter_by(phone=phone).first()
        if existing:
            flash(f'Customer with phone {phone} already exists!', 'error')
            return redirect(url_for('manage_customers'))

        try:
            # Set route_priority to the end of the list
            max_priority = db.session.query(db.func.max(Customer.route_priority)).scalar() or 0
            new_cust = Customer(name=name, phone=phone, email=email, rate_per_liter=float(rate), route_priority=max_priority + 1)
            db.session.add(new_cust)
            db.session.commit()
            flash('Customer added successfully.', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding customer: {str(e)}', 'error')
        
    customers = Customer.query.order_by(Customer.route_priority.asc()).all()
    return render_template('admin/customers.html', customers=customers)

@app.route('/admin/customer/<int:customer_id>/history')
@admin_required
def admin_view_history(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    # Fetch all bills for this customer ordered by month
    bills = Billing.query.filter_by(customer_id=customer.id).order_by(Billing.month.desc()).all()
    return render_template('customer/history.html', customer=customer, bills=bills, is_admin=True)

@app.route('/admin/attendance', methods=['GET', 'POST'])
@admin_required
def manage_attendance():
    date_str = request.args.get('date')
    if date_str:
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except:
            target_date = date.today()
    else:
        target_date = date.today()

    if request.method == 'POST':
        # Get date from hidden field to ensure we save to the correct day being viewed
        form_date_str = request.form.get('target_date')
        if form_date_str:
            target_date = datetime.strptime(form_date_str, '%Y-%m-%d').date()

        customer_ids = request.form.getlist('customer_id')
        mornings = request.form.getlist('morning')
        evenings = request.form.getlist('evening')
        
        for cid, m, e in zip(customer_ids, mornings, evenings):
            morning = float(m or 0)
            evening = float(e or 0)
            
            att = Attendance.query.filter_by(date=target_date, customer_id=cid).first()
            if not att:
                att = Attendance(date=target_date, customer_id=cid)
                db.session.add(att)
            
            att.morning_liters = morning
            att.evening_liters = evening
            att.total_liters = morning + evening
            
        db.session.commit()
        flash(f'Attendance for {target_date.strftime("%d %b")} updated successfully.', 'success')
        return redirect(url_for('manage_attendance', date=target_date))

    # Order by route_priority
    customers = Customer.query.order_by(Customer.route_priority.asc()).all()
    attendance_records = {a.customer_id: a for a in Attendance.query.filter_by(date=target_date).all()}
    return render_template('admin/attendance.html', customers=customers, records=attendance_records, today=target_date)

@app.route('/admin/reorder_customers', methods=['POST'])
@admin_required
def reorder_customers():
    order = request.json.get('order', []) # List of customer IDs in order
    for index, cid in enumerate(order):
        customer = Customer.query.get(cid)
        if customer:
            customer.route_priority = index
    db.session.commit()
    return {"status": "success"}



@app.route('/admin/payment/mark', methods=['POST'])
@admin_required
def mark_payment():
    bill_id = request.form.get('bill_id')
    amount = float(request.form.get('amount', 0))
    mode = request.form.get('mode', 'Cash')
    
    bill = Billing.query.get_or_404(bill_id)
    payment = Payment(billing_id=bill.id, amount=amount, mode=mode)
    db.session.add(payment)
    
    bill.paid_amount += amount
    if bill.paid_amount >= bill.total_amount:
        bill.status = 'Paid'
    elif bill.paid_amount > 0:
        bill.status = 'Partial'
    
    db.session.commit()
    flash('Payment marked.', 'success')
    return redirect(url_for('manage_billing'))

# --- CUSTOMER ROUTES ---

@app.route('/')
@login_required
def index():
    if current_user.role == 'admin':
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('customer_dashboard'))

@app.route('/dashboard')
@login_required
def customer_dashboard():
    customer = current_user.customer
    today_att = Attendance.query.filter_by(date=date.today(), customer_id=customer.id).first()
    
    # Monthly stats
    current_month_str = datetime.now().strftime('%Y-%m')
    bill = Billing.query.filter_by(month=current_month_str, customer_id=customer.id).first()
    
    # Yesterday's attendance
    yesterday_date = date.today() - timedelta(days=1)
    yesterday_att = Attendance.query.filter_by(date=yesterday_date, customer_id=customer.id).first()
    
    return render_template('customer/dashboard.html', 
                           customer=customer, 
                           today_att=today_att,
                           yesterday_att=yesterday_att,
                           bill=bill,
                           datetime=datetime)

@app.route('/attendance')
@login_required
def customer_attendance():
    customer = current_user.customer
    records = Attendance.query.filter_by(customer_id=customer.id).order_by(Attendance.date.desc()).all()
    return render_template('customer/attendance.html', records=records, datetime=datetime)

@app.route('/bills')
@login_required
def customer_bills():
    customer = current_user.customer
    current_month = datetime.now().strftime('%Y-%m')
    current_bill = Billing.query.filter_by(month=current_month, customer_id=customer.id).first()
    return render_template('customer/bills.html', current_bill=current_bill)

@app.route('/history')
@login_required
def customer_history():
    customer = current_user.customer
    # Fetch all bills for this customer ordered by month
    bills = Billing.query.filter_by(customer_id=customer.id).order_by(Billing.month.desc()).all()
    return render_template('customer/history.html', customer=customer, bills=bills, is_admin=False)



@app.route('/profile')
@login_required
def profile():
    return render_template('customer/profile.html')

@app.route('/download_bill/<int:bill_id>')
@login_required
def download_bill(bill_id):
    bill = Billing.query.get_or_404(bill_id)
    if current_user.role != 'admin' and bill.customer_id != current_user.customer_id:
        return "Access denied", 403
    
    customer = Customer.query.get(bill.customer_id)
    
    # Fetch all attendance records for this bill's month
    # bill.month is 'YYYY-MM'
    year, month = map(int, bill.month.split('-'))
    import calendar
    last_day = calendar.monthrange(year, month)[1]
    start_date = date(year, month, 1)
    end_date = date(year, month, last_day)
    
    attendances = Attendance.query.filter(
        Attendance.customer_id == customer.id,
        Attendance.date >= start_date,
        Attendance.date <= end_date
    ).order_by(Attendance.date.asc()).all()

    # Render HTML
    rendered_html = render_template('invoice.html', 
                                   bill=bill, 
                                   customer=customer, 
                                   attendances=attendances,
                                   datetime=datetime)
    
    if not HTML:
        return "PDF generation library (WeasyPrint) not fully installed on server. Please contact admin.", 500

    # Generate PDF
    pdf_file = io.BytesIO()
    try:
        # Pass base_url to resolve relative paths like static/images/...
        HTML(string=rendered_html, base_url=os.path.dirname(__file__)).write_pdf(pdf_file)
        pdf_file.seek(0)
        return send_file(pdf_file, download_name=f'Ramchandra_Dairy_Bill_{bill.month}_{customer.name.replace(" ", "_")}.pdf', as_attachment=True)
    except Exception as e:
        print(f"PDF Generation Error: {e}")
        return f"Error generating PDF: {e}", 500

# --- BILLING LOGIC ---

@app.route('/admin/billing')
@admin_required
def manage_billing():
    current_month = datetime.now().strftime('%Y-%m')
    display_month = datetime.now().strftime('%B %Y')
    customers = Customer.query.all()
    bills = {b.customer_id: b for b in Billing.query.filter_by(month=current_month).all()}
    return render_template('admin/billing.html', customers=customers, bills=bills, month=current_month, display_month=display_month)

@app.route('/admin/generate_bills', methods=['POST'])
@admin_required
def generate_bills():
    current_month = datetime.now().strftime('%Y-%m')
    customers = Customer.query.all()
    
    for customer in customers:
        # Sum all liters for the month
        # This is a simplified query for MVP
        start_date = date(datetime.now().year, datetime.now().month, 1)
        # End date is today for simplicity in MVP
        end_date = date.today()
        
        attendances = Attendance.query.filter(
            Attendance.customer_id == customer.id,
            Attendance.date >= start_date,
            Attendance.date <= end_date
        ).all()
        
        total_liters = sum(a.total_liters for a in attendances)
        total_amount = total_liters * customer.rate_per_liter
        
        bill = Billing.query.filter_by(month=current_month, customer_id=customer.id).first()
        if not bill:
            bill = Billing(month=current_month, customer_id=customer.id, paid_amount=0.0)
            db.session.add(bill)
        
        bill.total_liters = total_liters
        bill.total_amount = total_amount
        
        # Update Status based on new amount
        paid = bill.paid_amount or 0.0
        if paid >= bill.total_amount:
            bill.status = 'Paid'
        elif paid > 0:
            bill.status = 'Partial'
        else:
            bill.status = 'Due'
        
    db.session.commit()
    flash(f'Bills generated for {datetime.now().strftime("%B %Y")}', 'success')
    return redirect(url_for('manage_billing'))

# --- PWA ROUTES ---

@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')

@app.route('/sw.js')
def service_worker():
    return send_from_directory('static', 'sw.js')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        # Create admin if not exists
        if not User.query.filter_by(role='admin').first():
            admin = User(
                email_or_phone='admin@dairy.com',
                password_hash=generate_password_hash('admin123'),
                role='admin'
            )
            db.session.add(admin)
            db.session.commit()
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
