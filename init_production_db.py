from app import app, db, User
from werkzeug.security import generate_password_hash
import os

def init():
    with app.app_context():
        print("Initializing database...")
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
            print("Admin user created: admin@dairy.com / admin123")
        else:
            print("Admin user already exists.")
        print("Database initialized successfully.")

if __name__ == "__main__":
    init()
