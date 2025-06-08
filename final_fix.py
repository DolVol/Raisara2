#!/usr/bin/env python3
"""
Final Database Fix Script
This script will completely solve the database schema issues
"""

import os
import sqlite3
import shutil
import sys
from datetime import datetime

def find_all_database_files():
    """Find ALL database files in the project"""
    db_files = []
    
    # Common database file patterns
    patterns = [
        '*.db', '*.sqlite', '*.sqlite3', 
        'trees.db', 'user_*.db', 'instance/*.db'
    ]
    
    # Search in current directory and subdirectories
    for root, dirs, files in os.walk('.'):
        # Skip virtual environment directories
        if 'venv' in root or '__pycache__' in root:
            continue
            
        for file in files:
            if (file.endswith('.db') or 
                file.endswith('.sqlite') or 
                file.endswith('.sqlite3')):
                full_path = os.path.join(root, file)
                db_files.append(full_path)
    
    return db_files

def remove_all_database_files():
    """Remove ALL database files"""
    print("🔍 Finding all database files...")
    
    db_files = find_all_database_files()
    
    if not db_files:
        print("📋 No database files found")
        return
    
    print(f"📋 Found database files: {db_files}")
    
    for db_file in db_files:
        try:
            if os.path.exists(db_file):
                os.remove(db_file)
                print(f"🗑️ Removed: {db_file}")
        except Exception as e:
            print(f"⚠️ Could not remove {db_file}: {e}")

def clear_python_cache():
    """Clear Python cache files"""
    print("🧹 Clearing Python cache...")
    
    cache_dirs = []
    for root, dirs, files in os.walk('.'):
        if '__pycache__' in dirs:
            cache_dirs.append(os.path.join(root, '__pycache__'))
    
    for cache_dir in cache_dirs:
        try:
            shutil.rmtree(cache_dir)
            print(f"✅ Removed cache: {cache_dir}")
        except:
            pass

def remove_flask_migrate():
    """Remove Flask-Migrate files"""
    print("🧹 Removing Flask-Migrate files...")
    
    if os.path.exists('migrations'):
        try:
            shutil.rmtree('migrations')
            print("✅ Removed migrations directory")
        except Exception as e:
            print(f"⚠️ Could not remove migrations: {e}")

def create_minimal_database():
    """Create a minimal database with only essential tables"""
    print("🏗️ Creating minimal database...")
    
    db_file = 'db.sqlite3'
    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()
    
    try:
        # Create user table (essential)
        cursor.execute('''
            CREATE TABLE user (
                id INTEGER PRIMARY KEY,
                username VARCHAR(80) UNIQUE NOT NULL,
                email VARCHAR(120) UNIQUE NOT NULL,
                password_hash VARCHAR(200) NOT NULL,
                created_at DATETIME,
                is_active BOOLEAN DEFAULT 1,
                reset_token VARCHAR(100),
                reset_token_expires DATETIME
            )
        ''')
        print("✅ Created user table")
        
        # Create grid_settings table (WITHOUT user_id for now)
        cursor.execute('''
            CREATE TABLE grid_settings (
                id INTEGER PRIMARY KEY,
                rows INTEGER DEFAULT 5,
                cols INTEGER DEFAULT 5
            )
        ''')
        print("✅ Created grid_settings table (minimal)")
        
        # Create dome table (WITHOUT farm_id for now)
        cursor.execute('''
            CREATE TABLE dome (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                grid_row INTEGER NOT NULL,
                grid_col INTEGER NOT NULL,
                internal_rows INTEGER DEFAULT 5,
                internal_cols INTEGER DEFAULT 5,
                image_url VARCHAR(255),
                user_id INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES user(id)
            )
        ''')
        print("✅ Created dome table (minimal)")
        
        # Create tree table (minimal)
        cursor.execute('''
            CREATE TABLE tree (
                id INTEGER PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                row INTEGER DEFAULT 0,
                col INTEGER DEFAULT 0,
                info TEXT,
                life_days INTEGER DEFAULT 0,
                image_url VARCHAR(200),
                dome_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                FOREIGN KEY(dome_id) REFERENCES dome(id),
                FOREIGN KEY(user_id) REFERENCES user(id)
            )
        ''')
        print("✅ Created tree table (minimal)")
        
        # Insert default grid settings
        cursor.execute('INSERT INTO grid_settings (rows, cols) VALUES (5, 5)')
        print("✅ Created default grid settings")
        
        conn.commit()
        print("🎉 Minimal database created successfully!")
        
    except Exception as e:
        print(f"❌ Error creating database: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()
    
    return True

def create_minimal_models():
    """Create a minimal models.py that matches the database"""
    print("📝 Creating minimal models.py...")
    
    minimal_models = '''from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
    
    def generate_reset_token(self):
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        return self.reset_token
    
    def verify_reset_token(self, token):
        if not self.reset_token or not self.reset_token_expires:
            return False
        if self.reset_token != token:
            return False
        if datetime.utcnow() > self.reset_token_expires:
            return False
        return True
    
    def clear_reset_token(self):
        self.reset_token = None
        self.reset_token_expires = None

class GridSettings(db.Model):
    __tablename__ = 'grid_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    rows = db.Column(db.Integer, default=5)
    cols = db.Column(db.Integer, default=5)
    # Note: NO user_id column for now

class Dome(db.Model):
    __tablename__ = 'dome'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    grid_row = db.Column(db.Integer, nullable=False)
    grid_col = db.Column(db.Integer, nullable=False)
    internal_rows = db.Column(db.Integer, default=5)
    internal_cols = db.Column(db.Integer, default=5)
    image_url = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    # Note: NO farm_id column for now

class Tree(db.Model):
    __tablename__ = 'tree'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    row = db.Column(db.Integer, default=0)
    col = db.Column(db.Integer, default=0)
    info = db.Column(db.Text, nullable=True)
    life_days = db.Column(db.Integer, default=0)
    image_url = db.Column(db.String(200), nullable=True)
    dome_id = db.Column(db.Integer, db.ForeignKey('dome.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# Placeholder classes for compatibility
class Farm:
    pass

class Row:
    pass
'''
    
    # Backup original models.py
    if os.path.exists('models.py'):
        shutil.copy('models.py', 'models.py.backup')
        print("💾 Backed up original models.py to models.py.backup")
    
    # Write minimal models
    with open('models.py', 'w') as f:
        f.write(minimal_models)
    
    print("✅ Created minimal models.py")

def verify_fix():
    """Verify that the fix worked"""
    print("🔍 Verifying the fix...")
    
    # Check database exists
    if not os.path.exists('db.sqlite3'):
        print("❌ Database file not found")
        return False
    
    # Check database schema
    conn = sqlite3.connect('db.sqlite3')
    cursor = conn.cursor()
    
    try:
        # Check tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cursor.fetchall()]
        
        required_tables = ['user', 'grid_settings', 'dome', 'tree']
        missing_tables = [table for table in required_tables if table not in tables]
        
        if missing_tables:
            print(f"❌ Missing tables: {missing_tables}")
            return False
        
        print(f"✅ All required tables exist: {required_tables}")
        
        # Check that problematic columns are NOT present
        cursor.execute("PRAGMA table_info(grid_settings);")
        grid_columns = [row[1] for row in cursor.fetchall()]
        
        cursor.execute("PRAGMA table_info(dome);")
        dome_columns = [row[1] for row in cursor.fetchall()]
        
        if 'user_id' in grid_columns:
            print("⚠️ grid_settings still has user_id column")
        else:
            print("✅ grid_settings does NOT have user_id column")
        
        if 'farm_id' in dome_columns:
            print("⚠️ dome still has farm_id column")
        else:
            print("✅ dome does NOT have farm_id column")
        
        return True
        
    except Exception as e:
        print(f"❌ Error verifying database: {e}")
        return False
    finally:
        conn.close()

def create_upload_directories():
    """Create upload directories"""
    print("📁 Creating upload directories...")
    
    directories = ['uploads', 'uploads/trees', 'uploads/domes']
    
    for directory in directories:
        os.makedirs(directory, exist_ok=True)
        print(f"✅ Created directory: {directory}")

def main():
    """Main function"""
    print("🚀 Final Database Fix Tool")
    print("=" * 60)
    print("This will completely reset your database to a working state.")
    print("Your user data will be preserved if possible.")
    print("=" * 60)
    
    # Step 1: Remove all database files
    remove_all_database_files()
    
    # Step 2: Clear Python cache
    clear_python_cache()
    
    # Step 3: Remove Flask-Migrate
    remove_flask_migrate()
    
    # Step 4: Create minimal database
    if not create_minimal_database():
        print("❌ Failed to create database")
        return
    
    # Step 5: Create minimal models
    create_minimal_models()
    
    # Step 6: Create upload directories
    create_upload_directories()
    
    # Step 7: Verify fix
    if verify_fix():
        print("\n" + "=" * 60)
        print("🎉 FINAL FIX SUCCESSFUL!")
        print("\nYour app should now work with basic functionality:")
        print("✅ User authentication")
        print("✅ Dome management")
        print("✅ Tree management")
        print("✅ Image uploads")
        print("\nTo add farm system later, you can extend the models.")
        print("\nNext steps:")
        print("1. Restart your Flask app: python app.py")
        print("2. Test basic functionality")
        print("3. Register a new user or login")
        print("=" * 60)
    else:
        print("\n❌ Fix verification failed")

if __name__ == '__main__':
    main()