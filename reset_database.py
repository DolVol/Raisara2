import os
import shutil
from app import app
from models import db, GridSettings

def reset_database():
    # Remove database file
    if os.path.exists('db.sqlite3'):
        os.remove('db.sqlite3')
        print("Removed db.sqlite3")
    
    # Remove migrations folder if it exists
    if os.path.exists('migrations'):
        shutil.rmtree('migrations')
        print("Removed migrations folder")
    
    # Create uploads folder if it doesn't exist
    if not os.path.exists('uploads'):
        os.makedirs('uploads')
        print("Created uploads folder")
    
    # Create fresh database with all tables
    with app.app_context():
        try:
            # Create all tables from current models
            db.create_all()
            print("Created all database tables")
            
            # Initialize default grid settings
            if not GridSettings.query.first():
                default_grid = GridSettings(rows=5, cols=5)
                db.session.add(default_grid)
                db.session.commit()
                print("Added default grid settings")
            
            print("Database reset successfully!")
            print("All tables now include image_url columns")
            
        except Exception as e:
            print(f"Error during database reset: {e}")
            db.session.rollback()

if __name__ == '__main__':
    reset_database()