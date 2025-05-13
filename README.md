# Pizzeria Employee Time Tracking System

A simple and efficient web application for managing employee check-ins and checkouts at a pizzeria.

## Features

- Easy check-in/checkout system
- Support for different shift types:
  - Day Shift (08:00 - 16:59)
  - Evening Shift (17:00 - 23:59)
  - Weekend Hours
- Real-time status updates
- Clean, responsive interface
- SQLite database for easy setup and portability

## Setup

1. Create a virtual environment (recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Run the application:
```bash
python app.py
```

4. Access the application at `http://localhost:5000`

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