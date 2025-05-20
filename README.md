# Pizzeria Time Tracking System

A web-based time tracking system for managing employee shifts and work hours in a pizzeria.

## Features

- Employee check-in/check-out system
- Shift management (day, evening, weekend shifts)
- Admin dashboard for monitoring employee status
- Shift history and reporting
- Export functionality for shift data
- Weekend hours tracking
- Date range filtering for reports

## Setup

1. Create a virtual environment:
```bash
python -m venv venv
```

2. Activate the virtual environment:
- On Windows:
```bash
venv\Scripts\activate
```
- On macOS/Linux:
```bash
source venv/bin/activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Run the application:
```bash
python app.py
```

5. Access the application at `http://localhost:5000`

## Default Login

- Admin PIN: 1234
- Employee PINs: 1111, 2222, 3333, 4444

## Technologies Used

- Python
- Flask
- SQLAlchemy
- Bootstrap 5
- Font Awesome
- Pandas
- XlsxWriter

## Adding Employees

To add employees to the system, you can use the Python shell:

```python
from app import app, db, Employee

with app.app_context():
    # Add a new employee
    new_employee = Employee(name="John Doe")
    db.session.add(new_employee)
    db.session.commit()
```

## Usage

1. The main page displays all active employees
2. Each employee card shows:
   - Employee name
   - Current status
   - Check-in buttons for different shifts
   - Check-out button (when checked in)
3. The status automatically updates every 30 seconds
4. Employees can only check in once (duplicate check-ins are prevented)
5. The system automatically detects the current shift type based on time

## Technical Details

- Built with Flask and SQLite
- Uses Bootstrap 5 for responsive design
- Real-time updates using JavaScript fetch API
- Automatic shift detection based on time of day 