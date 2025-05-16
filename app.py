from flask import Flask, render_template, request, jsonify, flash, redirect, url_for, session, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, time, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import os
from functools import wraps
import pandas as pd
from io import BytesIO

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///pizzeria.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Models
class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    pin = db.Column(db.String(100), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    checked_in = db.Column(db.Boolean, default=False)
    check_in_time = db.Column(db.DateTime)
    shift_type = db.Column(db.String(20))
    shifts = db.relationship('Shift', backref='employee', lazy=True)

class Shift(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    check_in_time = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    check_out_time = db.Column(db.DateTime)
    shift_type = db.Column(db.String(20), nullable=False)

# Helper Functions
def get_shift_type():
    now = datetime.now()
    if now.weekday() >= 5:  # Weekend
        return 'weekend'
    elif now.hour < 16:  # Before 4 PM
        return 'day'
    else:
        return 'evening'

def get_shift_hours():
    now = datetime.now()
    if now.weekday() >= 5:  # Weekend
        return {
            'start': time(10, 0),  # 10:00 AM
            'end': time(22, 0)     # 10:00 PM
        }
    elif now.hour < 16:  # Day shift
        return {
            'start': time(8, 0),   # 8:00 AM
            'end': time(16, 0)     # 4:00 PM
        }
    else:  # Evening shift
        return {
            'start': time(16, 0),  # 4:00 PM
            'end': time(23, 0)     # 11:00 PM
        }

def validate_check_in(employee):
    if employee.checked_in:
        return False, "Already checked in"
    
    # Check if employee has an ongoing shift
    ongoing_shift = Shift.query.filter_by(
        employee_id=employee.id,
        check_out_time=None
    ).first()
    
    if ongoing_shift:
        return False, "You have an ongoing shift"
    
    # Check if within valid shift hours
    current_time = datetime.now().time()
    shift_hours = get_shift_hours()
    
    if not (shift_hours['start'] <= current_time <= shift_hours['end']):
        return False, f"Outside of shift hours ({shift_hours['start'].strftime('%I:%M %p')} - {shift_hours['end'].strftime('%I:%M %p')})"
    
    return True, "Can check in"

# Authentication decorator
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'employee_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'employee_id' not in session:
            return redirect(url_for('login'))
        employee = Employee.query.get(session['employee_id'])
        if not employee or not employee.is_admin:
            flash('You do not have permission to access this page.', 'danger')
            return redirect(url_for('employee_dashboard'))
        return f(*args, **kwargs)
    return decorated_function

# Routes
@app.route('/')
def index():
    if 'employee_id' in session:
        employee = Employee.query.get(session['employee_id'])
        if employee.is_admin:
            return redirect(url_for('admin_dashboard'))
        return redirect(url_for('employee_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        pin = request.form.get('pin')
        if not pin:
            return render_template('login.html', error="Please enter your PIN")
        
        # Find employee with matching PIN
        employees = Employee.query.all()
        for employee in employees:
            if check_password_hash(employee.pin, pin):
                session['employee_id'] = employee.id
                if employee.is_admin:
                    return redirect(url_for('admin_dashboard'))
                return redirect(url_for('employee_dashboard'))
        
        return render_template('login.html', error="Invalid PIN")
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    if 'employee_id' in session:
        employee = Employee.query.get(session['employee_id'])
        if employee and employee.checked_in:
            # Update ongoing shift
            ongoing_shift = Shift.query.filter_by(
                employee_id=employee.id,
                check_out_time=None
            ).first()
            
            if ongoing_shift:
                ongoing_shift.check_out_time = datetime.utcnow()
            
            employee.checked_in = False
            employee.check_in_time = None
            employee.shift_type = None
            
            db.session.commit()
    
    session.pop('employee_id', None)
    return redirect(url_for('login'))

@app.route('/employee/dashboard')
@login_required
def employee_dashboard():
    employee = Employee.query.get(session['employee_id'])
    if employee.is_admin:
        return redirect(url_for('admin_dashboard'))
    
    # Get recent shifts
    shifts = Shift.query.filter_by(employee_id=employee.id)\
        .order_by(Shift.check_in_time.desc())\
        .limit(10)\
        .all()
    
    return render_template('employee_dashboard.html', employee=employee, shifts=shifts)

@app.route('/admin/dashboard')
@admin_required
def admin_dashboard():
    checked_in_employees = Employee.query.filter_by(checked_in=True).all()
    return render_template('admin_dashboard.html', checked_in_employees=checked_in_employees)

@app.route('/admin/employees')
@admin_required
def manage_employees():
    employees = Employee.query.filter_by(is_admin=False).all()
    return render_template('manage_employees.html', employees=employees)

@app.route('/admin/employees/add', methods=['POST'])
@admin_required
def add_employee():
    name = request.form.get('name')
    pin = request.form.get('pin')
    
    if not name or not pin:
        return jsonify({'success': False, 'message': 'Name and PIN are required'})
    
    if len(pin) != 4 or not pin.isdigit():
        return jsonify({'success': False, 'message': 'PIN must be 4 digits'})
    
    # Check if PIN already exists (fix: check using check_password_hash)
    employees = Employee.query.all()
    for employee in employees:
        if check_password_hash(employee.pin, pin):
            return jsonify({'success': False, 'message': 'PIN already in use'})
    
    employee = Employee(
        name=name,
        pin=generate_password_hash(pin),
        is_admin=False
    )
    
    db.session.add(employee)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/admin/employees/<int:employee_id>/delete', methods=['POST'])
@admin_required
def delete_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    if employee.is_admin:
        flash('Cannot delete admin user.', 'danger')
        return redirect(url_for('manage_employees'))
    
    db.session.delete(employee)
    db.session.commit()
    
    flash('Employee deleted successfully!', 'success')
    return redirect(url_for('manage_employees'))

@app.route('/admin/shifts')
@admin_required
def view_shifts():
    # Get date filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Base query
    query = Shift.query
    
    # Apply date filters if provided
    if start_date:
        start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
        query = query.filter(Shift.check_in_time >= start_datetime)
    
    if end_date:
        end_datetime = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        query = query.filter(Shift.check_in_time < end_datetime)
    
    # Get filtered shifts
    shifts = query.order_by(Shift.check_in_time.desc()).all()
    
    # Group shifts by day of week
    shifts_by_day = {
        'Monday': [],
        'Tuesday': [],
        'Wednesday': [],
        'Thursday': [],
        'Friday': [],
        'Saturday': [],
        'Sunday': []
    }
    
    for shift in shifts:
        day = shift.check_in_time.strftime('%A')
        shifts_by_day[day].append(shift)
    
    return render_template('view_shifts.html', shifts_by_day=shifts_by_day)

@app.route('/admin/shifts/export')
@admin_required
def export_shifts():
    # Get date filter parameters
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    
    # Base query
    query = Shift.query
    
    # Apply date filters if provided
    if start_date:
        start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
        query = query.filter(Shift.check_in_time >= start_datetime)
    
    if end_date:
        end_datetime = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        query = query.filter(Shift.check_in_time < end_datetime)
    
    # Get filtered shifts
    shifts = query.order_by(Shift.check_in_time.desc()).all()
    
    # Create DataFrame
    data = []
    for shift in shifts:
        duration = None
        if shift.check_out_time:
            duration = (shift.check_out_time - shift.check_in_time).total_seconds() / 3600
        
        data.append({
            'Employee': shift.employee.name,
            'Shift Type': shift.shift_type.title(),
            'Check In': shift.check_in_time.strftime('%Y-%m-%d %H:%M:%S'),
            'Check Out': shift.check_out_time.strftime('%Y-%m-%d %H:%M:%S') if shift.check_out_time else 'Not checked out',
            'Duration (hours)': f"{duration:.2f}" if duration else 'Ongoing'
        })
    
    df = pd.DataFrame(data)
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Shifts', index=False)
        
        # Auto-adjust columns width
        worksheet = writer.sheets['Shifts']
        for i, col in enumerate(df.columns):
            max_length = max(df[col].astype(str).apply(len).max(), len(col)) + 2
            worksheet.set_column(i, i, max_length)
    
    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'shifts_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    )

@app.route('/check-in', methods=['POST'])
@login_required
def check_in():
    employee = Employee.query.get(session['employee_id'])
    
    can_check_in, message = validate_check_in(employee)
    if not can_check_in:
        return jsonify({'success': False, 'message': message})
    
    shift_type = get_shift_type()
    employee.checked_in = True
    employee.check_in_time = datetime.utcnow()
    employee.shift_type = shift_type
    
    # Create new shift
    shift = Shift(
        employee_id=employee.id,
        shift_type=shift_type
    )
    
    db.session.add(shift)
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/check-out', methods=['POST'])
@login_required
def check_out():
    employee = Employee.query.get(session['employee_id'])
    
    if not employee.checked_in:
        return jsonify({'success': False, 'message': 'Not checked in'})
    
    # Update ongoing shift
    ongoing_shift = Shift.query.filter_by(
        employee_id=employee.id,
        check_out_time=None
    ).first()
    
    if ongoing_shift:
        ongoing_shift.check_out_time = datetime.utcnow()
    
    employee.checked_in = False
    employee.check_in_time = None
    employee.shift_type = None
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/check-out/<int:employee_id>', methods=['POST'])
@admin_required
def admin_check_out(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    
    if not employee.checked_in:
        return jsonify({'success': False, 'message': 'Employee not checked in'})
    
    # Update ongoing shift
    ongoing_shift = Shift.query.filter_by(
        employee_id=employee.id,
        check_out_time=None
    ).first()
    
    if ongoing_shift:
        ongoing_shift.check_out_time = datetime.utcnow()
    
    employee.checked_in = False
    employee.check_in_time = None
    employee.shift_type = None
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/status')
@login_required
def status():
    employees = Employee.query.all()
    return jsonify([{
        'id': emp.id,
        'name': emp.name,
        'checked_in': emp.checked_in,
        'check_in_time': emp.check_in_time.strftime('%Y-%m-%d %H:%M:%S') if emp.check_in_time else None,
        'shift_type': emp.shift_type
    } for emp in employees])

@app.route('/admin/shifts/weekend-hours')
@admin_required
def weekend_hours():
    # Get all shifts
    shifts = Shift.query.all()
    
    # Initialize weekend hours tracking
    weekend_hours = {
        'total_hours': 0,
        'employees': {}
    }
    
    for shift in shifts:
        # Check if shift is on weekend
        if shift.check_in_time.weekday() >= 5:  # Saturday (5) or Sunday (6)
            employee_name = shift.employee.name
            
            # Calculate shift duration
            if shift.check_out_time:
                duration = (shift.check_out_time - shift.check_in_time).total_seconds() / 3600
            else:
                # For ongoing shifts, calculate until now
                duration = (datetime.utcnow() - shift.check_in_time).total_seconds() / 3600
            
            # Update total hours
            weekend_hours['total_hours'] += duration
            
            # Update employee hours
            if employee_name not in weekend_hours['employees']:
                weekend_hours['employees'][employee_name] = 0
            weekend_hours['employees'][employee_name] += duration
    
    # Round all hours to 2 decimal places
    weekend_hours['total_hours'] = round(weekend_hours['total_hours'], 2)
    for employee in weekend_hours['employees']:
        weekend_hours['employees'][employee] = round(weekend_hours['employees'][employee], 2)
    
    return jsonify(weekend_hours)

@app.route('/admin/shifts/weekend-hours/export')
@admin_required
def export_weekend_hours():
    # Get all shifts
    shifts = Shift.query.all()
    
    # Initialize weekend hours tracking
    weekend_hours = {
        'total_hours': 0,
        'employees': {}
    }
    
    # Get weekend shifts
    weekend_shifts = []
    for shift in shifts:
        if shift.check_in_time.weekday() >= 5:  # Saturday (5) or Sunday (6)
            employee_name = shift.employee.name
            
            # Calculate shift duration
            if shift.check_out_time:
                duration = (shift.check_out_time - shift.check_in_time).total_seconds() / 3600
            else:
                duration = (datetime.utcnow() - shift.check_in_time).total_seconds() / 3600
            
            # Update total hours
            weekend_hours['total_hours'] += duration
            
            # Update employee hours
            if employee_name not in weekend_hours['employees']:
                weekend_hours['employees'][employee_name] = 0
            weekend_hours['employees'][employee_name] += duration
            
            # Add to weekend shifts list
            weekend_shifts.append({
                'Employee': employee_name,
                'Date': shift.check_in_time.strftime('%Y-%m-%d'),
                'Day': shift.check_in_time.strftime('%A'),
                'Check In': shift.check_in_time.strftime('%H:%M'),
                'Check Out': shift.check_out_time.strftime('%H:%M') if shift.check_out_time else 'Not checked out',
                'Duration (hours)': f"{duration:.2f}"
            })
    
    # Create DataFrame
    df = pd.DataFrame(weekend_shifts)
    
    # Add summary rows
    summary_rows = []
    for employee, hours in weekend_hours['employees'].items():
        summary_rows.append({
            'Employee': employee,
            'Date': 'Total',
            'Day': '',
            'Check In': '',
            'Check Out': '',
            'Duration (hours)': f"{hours:.2f}"
        })
    
    # Add grand total
    summary_rows.append({
        'Employee': 'All Employees',
        'Date': 'Grand Total',
        'Day': '',
        'Check In': '',
        'Check Out': '',
        'Duration (hours)': f"{weekend_hours['total_hours']:.2f}"
    })
    
    # Add summary rows to DataFrame
    df = pd.concat([df, pd.DataFrame(summary_rows)], ignore_index=True)
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, sheet_name='Weekend Hours', index=False)
        
        # Auto-adjust columns width
        worksheet = writer.sheets['Weekend Hours']
        for i, col in enumerate(df.columns):
            max_length = max(df[col].astype(str).apply(len).max(), len(col)) + 2
            worksheet.set_column(i, i, max_length)
        
        # Add some formatting
        workbook = writer.book
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#2C3E50',
            'font_color': 'white'
        })
        
        # Apply header format
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
        
        # Format summary rows
        summary_format = workbook.add_format({
            'bold': True,
            'bg_color': '#E8F0FE'
        })
        
        # Apply summary format to the last rows
        for row in range(len(df) - len(summary_rows), len(df)):
            for col in range(len(df.columns)):
                worksheet.write(row, col, df.iloc[row, col], summary_format)
    
    output.seek(0)
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'weekend_hours_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
    )

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Only create tables if they don't exist
    app.run(debug=True, port=5001) 