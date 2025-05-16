from app import app, db, Employee
from werkzeug.security import generate_password_hash

def init_db():
    with app.app_context():
        # Create tables
        db.create_all()
        
        # Check if admin user exists
        admin = Employee.query.filter_by(name='Admin').first()
        if not admin:
            # Create admin user
            admin = Employee(
                name='Admin',
                pin=generate_password_hash('1234'),  # Default admin PIN
                is_admin=True
            )
            db.session.add(admin)
            db.session.commit()
            print("Admin user created successfully!")
        else:
            print("Admin user already exists!")

if __name__ == '__main__':
    init_db() 