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
    check_in_time = db.Column(db.DateTime, nullable=False, default=datetime.now)
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
                ongoing_shift.check_out_time = datetime.now()
            
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
    # Get all checked-in employees with their latest check-in time
    checked_in_employees = db.session.query(Employee).filter(Employee.checked_in == True).all()
    
    # Debug print
    print("\nChecked-in employees:")
    for emp in checked_in_employees:
        print(f"Employee: {emp.name}, Check-in time: {emp.check_in_time}, Shift: {emp.shift_type}")
    
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
    try:
        employee = Employee.query.get_or_404(employee_id)
        
        if employee.is_admin:
            flash('Cannot delete admin user.', 'danger')
            return redirect(url_for('manage_employees'))
        
        # Check if employee is currently checked in
        if employee.checked_in:
            # Update ongoing shift
            ongoing_shift = Shift.query.filter_by(
                employee_id=employee.id,
                check_out_time=None
            ).first()
            
            if ongoing_shift:
                ongoing_shift.check_out_time = datetime.now()
        
        # Delete all associated shifts first
        Shift.query.filter_by(employee_id=employee.id).delete()
        
        # Now delete the employee
        db.session.delete(employee)
        db.session.commit()
        
        flash('Employee deleted successfully!', 'success')
        return redirect(url_for('manage_employees'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting employee: {str(e)}', 'danger')
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
    
    # If no dates specified, default to current month
    if not start_date and not end_date:
        today = datetime.now()
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        end_date = (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
        end_date = end_date.strftime('%Y-%m-%d')
    
    # Apply date filters
    if start_date:
        start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
        query = query.filter(Shift.check_in_time >= start_datetime)
    
    if end_date:
        end_datetime = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        query = query.filter(Shift.check_in_time < end_datetime)
    
    # Get filtered shifts
    shifts = query.order_by(Shift.check_in_time.desc()).all()
    
    # Get unique employees
    employees = list(set(shift.employee.name for shift in shifts))
    employees.sort()  # Sort alphabetically
    
    # Initialize data structures
    employee_data = {emp: {'day': [], 'evening': [], 'weekend': []} for emp in employees}
    total_hours = {emp: {'day': 0, 'evening': 0, 'weekend': 0} for emp in employees}
    
    # Process shifts
    for shift in shifts:
        duration = None
        if shift.check_out_time:
            duration = (shift.check_out_time - shift.check_in_time).total_seconds() / 3600
            total_hours[shift.employee.name][shift.shift_type] += duration
        
        shift_data = {
            'Date': shift.check_in_time.strftime('%Y-%m-%d'),
            'Day': shift.check_in_time.strftime('%A'),
            'Check In': shift.check_in_time.strftime('%H:%M:%S'),
            'Check Out': shift.check_out_time.strftime('%H:%M:%S') if shift.check_out_time else 'Not checked out',
            'Duration (hours)': f"{duration:.2f}" if duration else 'Ongoing'
        }
        employee_data[shift.employee.name][shift.shift_type].append(shift_data)
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        
        # Create formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#2C3E50',
            'font_color': 'white',
            'border': 1
        })
        
        summary_format = workbook.add_format({
            'bold': True,
            'bg_color': '#E8F0FE',
            'border': 1
        })
        
        total_format = workbook.add_format({
            'bold': True,
            'bg_color': '#FFD700',
            'border': 1
        })
        
        # Create Summary Sheet
        summary_data = []
        for employee in employees:
            hours = total_hours[employee]
            total = sum(hours.values())
            summary_data.append({
                'Employee': employee,
                'Day Hours': f"{hours['day']:.2f}",
                'Evening Hours': f"{hours['evening']:.2f}",
                'Weekend Hours': f"{hours['weekend']:.2f}",
                'Total Hours': f"{total:.2f}"
            })
        
        # Add grand totals
        grand_totals = {
            'Employee': 'GRAND TOTAL',
            'Day Hours': f"{sum(total_hours[emp]['day'] for emp in employees):.2f}",
            'Evening Hours': f"{sum(total_hours[emp]['evening'] for emp in employees):.2f}",
            'Weekend Hours': f"{sum(total_hours[emp]['weekend'] for emp in employees):.2f}",
            'Total Hours': f"{sum(sum(total_hours[emp].values()) for emp in employees):.2f}"
        }
        summary_data.append(grand_totals)
        
        # Create and format summary sheet
        df_summary = pd.DataFrame(summary_data)
        df_summary.to_excel(writer, sheet_name='Summary', index=False)
        worksheet_summary = writer.sheets['Summary']
        
        # Format summary sheet
        for i, col in enumerate(df_summary.columns):
            max_length = max(df_summary[col].astype(str).apply(len).max(), len(col)) + 2
            worksheet_summary.set_column(i, i, max_length)
            worksheet_summary.write(0, i, col, header_format)
        
        # Format grand total row
        for col in range(len(df_summary.columns)):
            worksheet_summary.write(len(df_summary) - 1, col, df_summary.iloc[-1, col], total_format)
        
        # Create individual employee sheets
        for employee in employees:
            # Create DataFrame for each shift type
            dfs = {}
            for shift_type in ['day', 'evening', 'weekend']:
                if employee_data[employee][shift_type]:
                    df = pd.DataFrame(employee_data[employee][shift_type])
                    # Add total row
                    total_row = {
                        'Date': 'Total Hours',
                        'Day': '',
                        'Check In': '',
                        'Check Out': '',
                        'Duration (hours)': f"{total_hours[employee][shift_type]:.2f}"
                    }
                    df = pd.concat([df, pd.DataFrame([total_row])], ignore_index=True)
                    dfs[shift_type] = df
            
            # Write to Excel
            sheet_name = employee[:31]  # Excel sheet names limited to 31 chars
            worksheet = workbook.add_worksheet(sheet_name)
            
            # Write headers
            for col, header in enumerate(['Shift Type', 'Date', 'Day', 'Check In', 'Check Out', 'Duration (hours)']):
                worksheet.write(0, col, header, header_format)
            
            # Write data for each shift type
            current_row = 1
            for shift_type in ['day', 'evening', 'weekend']:
                if shift_type in dfs:
                    df = dfs[shift_type]
                    # Write shift type header
                    worksheet.write(current_row, 0, shift_type.title(), summary_format)
                    current_row += 1
                    
                    # Write shift data
                    for _, row in df.iterrows():
                        for col, value in enumerate(row):
                            worksheet.write(current_row, col + 1, value)
                        current_row += 1
                    
                    current_row += 1  # Add space between shift types
            
            # Set column widths
            worksheet.set_column(0, 0, 15)  # Shift Type
            worksheet.set_column(1, 1, 12)  # Date
            worksheet.set_column(2, 2, 12)  # Day
            worksheet.set_column(3, 4, 12)  # Check In/Out
            worksheet.set_column(5, 5, 15)  # Duration
    
    output.seek(0)
    
    # Create filename with date range
    filename = f'shifts_{start_date}_to_{end_date}.xlsx' if start_date and end_date else f'shifts_{datetime.now().strftime("%Y-%m")}.xlsx'
    
    return send_file(
        output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=filename
    )

@app.route('/check-in', methods=['POST'])
@login_required
def check_in():
    try:
        employee = Employee.query.get(session['employee_id'])
        print(f"Attempting check-in for employee: {employee.name}")
        
        can_check_in, message = validate_check_in(employee)
        print(f"Can check in: {can_check_in}, Message: {message}")
        
        if not can_check_in:
            return jsonify({'success': False, 'message': message})
        
        shift_type = get_shift_type()
        current_time = datetime.now()
        
        # Update employee status
        employee.checked_in = True
        employee.check_in_time = current_time
        employee.shift_type = shift_type
        
        # Create new shift
        shift = Shift(
            employee_id=employee.id,
            check_in_time=current_time,
            shift_type=shift_type
        )
        
        db.session.add(shift)
        db.session.commit()
        
        # Verify the update
        db.session.refresh(employee)
        print(f"Employee check-in status after update: {employee.checked_in}")
        print(f"Employee check-in time after update: {employee.check_in_time}")
        
        return jsonify({'success': True})
    except Exception as e:
        db.session.rollback()
        print(f"Error during check-in: {str(e)}")
        return jsonify({'success': False, 'message': 'Error during check-in'})

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
        ongoing_shift.check_out_time = datetime.now()
    
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
        ongoing_shift.check_out_time = datetime.now()
    
    employee.checked_in = False
    employee.check_in_time = None
    employee.shift_type = None
    
    db.session.commit()
    
    return jsonify({'success': True})

@app.route('/status')
@login_required
def status():
    # Get all employees
    employees = Employee.query.all()
    status_data = [{
        'id': emp.id,
        'name': emp.name,
        'checked_in': emp.checked_in,
        'check_in_time': emp.check_in_time.strftime('%Y-%m-%d %H:%M:%S') if emp.check_in_time else None,
        'shift_type': emp.shift_type
    } for emp in employees]
    print(f"Status data: {status_data}")
    return jsonify(status_data)

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
                duration = (datetime.now() - shift.check_in_time).total_seconds() / 3600
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
                duration = (datetime.now() - shift.check_in_time).total_seconds() / 3600
            
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

@app.route('/admin/shifts/delete', methods=['POST'])
@admin_required
def delete_shifts():
    try:
        data = request.get_json()
        start_date = data.get('start_date')
        end_date = data.get('end_date')
        
        if not start_date or not end_date:
            return jsonify({
                'success': False,
                'message': 'Start date and end date are required'
            }), 400
        
        # Convert dates to datetime objects
        start_datetime = datetime.strptime(start_date, '%Y-%m-%d')
        end_datetime = datetime.strptime(end_date, '%Y-%m-%d') + timedelta(days=1)
        
        # Delete shifts within the date range
        deleted = Shift.query.filter(
            Shift.check_in_time >= start_datetime,
            Shift.check_in_time < end_datetime
        ).delete()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Successfully deleted {deleted} shifts'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({
            'success': False,
            'message': str(e)
        }), 500

if __name__ == '__main__':
    with app.app_context():
        # Create tables if they don't exist
        db.create_all()
        
        # Check if admin user exists, if not create one
        admin = Employee.query.filter_by(is_admin=True).first()
        if not admin:
            admin = Employee(
                name='Admin',
                pin=generate_password_hash('1234'),
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print("Created admin user")
    
    app.run(debug=True, port=5000) 