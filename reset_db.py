import os
import shutil
from app import app
from models import db, GridSettings

def reset_database():
    # Remove database file
    if os.path.exists('db.sqlite3'):
        os.remove('db.sqlite3')
        print("Removed db.sqlite3")
    
    # Remove migrations folder
    if os.path.exists('migrations'):
        shutil.rmtree('migrations')
        print("Removed migrations folder")
    
    # Create fresh database with proper context
    with app.app_context():
        try:
            # Drop all tables first
            db.drop_all()
            print("Dropped all existing tables")
            
            # Create all tables from current models
            db.create_all()
            print("Created all tables from models")
            
            # Initialize default grid settings
            default_grid = GridSettings(rows=5, cols=5)
            db.session.add(default_grid)
            db.session.commit()
            print("Added default grid settings")
            
            print("Database reset successfully!")
            
        except Exception as e:
            print(f"Error during database reset: {e}")
            db.session.rollback()

if __name__ == '__main__':
    reset_database()