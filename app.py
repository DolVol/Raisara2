import json 
from dotenv import load_dotenv
import os
import qrcode
import io
import re
import base64
from PIL import Image
from sqlalchemy import text
import time
import requests
import json
# Load environment variables from .env file
load_dotenv()

# Now import other modules
from flask import Flask,Blueprint, render_template, request, jsonify, send_from_directory, send_file, redirect, session, flash, url_for,current_app, make_response, abort
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from models import (
    db, User, Farm, Dome, Tree, GridSettings, 
    DragArea, DragAreaTree, RegularArea, RegularAreaCell,
    PlantRelationship, TreeBreed, ClipboardData  # ✅ ADD ClipboardData
)
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
from datetime import datetime, timedelta
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from services.life_updater import TreeLifeUpdater
from flask_mail import Mail, Message
import sqlite3
import logging
from auto_fix_db import auto_fix_user_table
mail = Mail()

# Configuration constants
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}


def fix_plant_relationship_constraints():
    """Fix plant_relationship table constraints to allow NULL values"""
    try:
        with app.app_context():
            # Check if plant_relationship table exists
            if 'plant_relationship' in db.metadata.tables:
                print("🔧 Fixing plant_relationship table constraints...")
                
                # For SQLite, we need to recreate the table
                db.engine.execute("""
                    CREATE TABLE plant_relationship_new (
                        id INTEGER PRIMARY KEY,
                        mother_tree_id INTEGER,
                        cutting_tree_id INTEGER,
                        relationship_type VARCHAR(50) DEFAULT 'cutting',
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        notes TEXT,
                        FOREIGN KEY (mother_tree_id) REFERENCES trees(id) ON DELETE SET NULL,
                        FOREIGN KEY (cutting_tree_id) REFERENCES trees(id) ON DELETE SET NULL
                    )
                """)
                
                # Copy existing data
                db.engine.execute("""
                    INSERT INTO plant_relationship_new 
                    SELECT * FROM plant_relationship
                """)
                
                # Drop old table and rename new one
                db.engine.execute("DROP TABLE plant_relationship")
                db.engine.execute("ALTER TABLE plant_relationship_new RENAME TO plant_relationship")
                
                print("✅ plant_relationship table constraints fixed")
            else:
                print("ℹ️ plant_relationship table does not exist")
                
    except Exception as e:
        print(f"❌ Error fixing constraints: {e}")
def add_missing_columns():
    """Add missing columns to existing tables"""
    try:
        # Check if created_at column exists in drag_area_tree table
        cursor = db.session.execute(text("PRAGMA table_info(drag_area_tree)"))
        columns = [row[1] for row in cursor.fetchall()]
        
        if 'created_at' not in columns:
            print("Adding created_at column to drag_area_tree table...")
            db.session.execute(text("""
                ALTER TABLE drag_area_tree 
                ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            """))
            db.session.commit()
            print("✅ Successfully added created_at column")
        else:
            print("✅ created_at column already exists")
            
    except Exception as e:
        print(f"❌ Error adding missing columns: {e}")
        db.session.rollback()
# ✅ FIXED: Database configuration with better error handling
def get_database_url():
    """Get database URL based on environment"""
    # Check if we're on Render (production)
    if os.getenv('RENDER'):
        # Use PostgreSQL on Render
        database_url = os.getenv('DATABASE_URL')
        if database_url:
            if database_url.startswith('postgres://'):
                # Fix for SQLAlchemy 1.4+ compatibility
                database_url = database_url.replace('postgres://', 'postgresql://', 1)
            return database_url
        else:
            # Fallback to SQLite if DATABASE_URL is not set
            print("⚠️ WARNING: DATABASE_URL not found on Render, falling back to SQLite")
            return 'sqlite:///db.sqlite3'
    else:
        # Use SQLite for local development
        return 'sqlite:///db.sqlite3'

DATABASE_URL = get_database_url()

# Configuration
SECRET_KEY = os.getenv('SECRET_KEY', 'fallback-secret-key')
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = os.getenv('MAIL_USERNAME')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD')

print(f"Environment: {'Production (Render)' if os.getenv('RENDER') else 'Development'}")
print(f"Loaded MAIL_USERNAME: {MAIL_USERNAME}")
print(f"Loaded SECRET_KEY: {SECRET_KEY[:20]}...")
if DATABASE_URL:
    print(f"Database URL: {DATABASE_URL[:50]}..." if len(DATABASE_URL) > 50 else f"Database URL: {DATABASE_URL}")
else:
    print("No DATABASE_URL")

# ✅ FIXED: Initialize TreeLifeUpdater with proper error handling
try:
    life_updater = TreeLifeUpdater(DATABASE_URL)
except Exception as e:
    print(f"⚠️ Warning: Could not initialize TreeLifeUpdater: {e}")
    life_updater = None

# Initialize Flask-Login
login_manager = LoginManager()

# Add these helper functions
def is_postgresql():
    """Check if we're using PostgreSQL"""
    return 'postgresql' in DATABASE_URL or os.getenv('RENDER') or os.getenv('DATABASE_URL', '').startswith('postgres')

def is_sqlite():
    """Check if we're using SQLite"""
    return 'sqlite' in DATABASE_URL and not os.getenv('RENDER')

def get_grid_settings(grid_type='dome', user_id=None, farm_id=None):
    """Get grid settings for specific type, user, and optionally farm"""
    try:
        # If it's a farm dome view, use farm-specific dome settings
        if grid_type == 'dome' and farm_id:
            grid_type_key = f'farm_{farm_id}_dome'
        else:
            grid_type_key = grid_type
            
        settings = GridSettings.query.filter_by(
            grid_type=grid_type_key,
            user_id=user_id
        ).first()
        
        if not settings:
            # Create default settings with better defaults for different contexts
            if grid_type == 'farm':
                default_rows, default_cols = 10, 10
            elif farm_id:  # Farm-specific dome settings
                default_rows, default_cols = 8, 8  # Reasonable default for farm domes
            else:  # Global dome settings
                default_rows, default_cols = 10, 10  # Larger default for global domes
            
            settings = GridSettings(
                rows=default_rows,
                cols=default_cols,
                grid_type=grid_type_key,
                user_id=user_id
            )
            db.session.add(settings)
            
            try:
                db.session.commit()
                print(f"✅ Created default {grid_type_key} settings: {default_rows}x{default_cols}")
            except Exception as commit_error:
                db.session.rollback()
                print(f"⚠️ Failed to create grid settings: {commit_error}")
                # Return a default object instead
                return type('obj', (object,), {
                    'rows': default_rows,
                    'cols': default_cols,
                    'grid_type': grid_type_key
                })
            
        return settings
    except Exception as e:
        print(f"Error getting grid settings: {e}")
        # Return default object
        if grid_type == 'farm':
            default_rows, default_cols = 10, 10
        elif farm_id:
            default_rows, default_cols = 8, 8
        else:
            default_rows, default_cols = 10, 10
            
        return type('obj', (object,), {
            'rows': default_rows,
            'cols': default_cols,
            'grid_type': grid_type_key if 'grid_type_key' in locals() else grid_type
        })
def update_grid_settings(grid_type, rows, cols, user_id=None, farm_id=None):
    """Update grid settings for specific type, user, and optionally farm"""
    try:
        # If it's a farm dome view, use farm-specific dome settings
        if grid_type == 'dome' and farm_id:
            grid_type_key = f'farm_{farm_id}_dome'
        else:
            grid_type_key = grid_type
            
        settings = GridSettings.query.filter_by(
            grid_type=grid_type_key,
            user_id=user_id
        ).first()
        
        if not settings:
            settings = GridSettings(
                grid_type=grid_type_key,
                user_id=user_id
            )
            db.session.add(settings)
        
        settings.rows = rows
        settings.cols = cols
        db.session.commit()
        
        print(f"✅ Updated {grid_type_key} grid settings to {rows}x{cols} for user {user_id}")
        return True
    except Exception as e:
        print(f"Error updating grid settings: {e}")
        db.session.rollback()
        return False

def initialize_defaults():
    """Initialize default grid settings with error handling"""
    try:
        if not GridSettings.query.first():
            default_grid = GridSettings(rows=5, cols=5)
            db.session.add(default_grid)
            db.session.commit()
            print("✅ Created default grid settings")
    except Exception as e:
        print(f"⚠️ Could not initialize grid settings: {e}")
        # Don't crash - the app can work without this

def save_image_to_database(image_file, entity_type, entity_id):
    """Save image as compressed base64 in database"""
    try:
        # Read the image
        image_data = image_file.read()
        
        # Open with PIL for processing
        img = Image.open(io.BytesIO(image_data))
        
        # ✅ AGGRESSIVE COMPRESSION: Smaller max size for database storage
        max_size = (600, 400)  # Reduced from 800x600
        if img.size[0] > max_size[0] or img.size[1] > max_size[1]:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)
            print(f"🔄 Resized image from original to {img.size}")
        
        # ✅ COMPRESS: Convert to RGB if needed and save as JPEG with compression
        if img.mode in ('RGBA', 'P'):
            # Convert RGBA/P to RGB
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = rgb_img
        
        # Save to bytes with aggressive compression
        img_byte_arr = io.BytesIO()
        img.save(img_byte_arr, format='JPEG', quality=75, optimize=True)  # Reduced quality from 85 to 75
        compressed_data = img_byte_arr.getvalue()
        
        # Convert to base64
        image_base64 = base64.b64encode(compressed_data).decode('utf-8')
        
        # Create data URL
        data_url = f'data:image/jpeg;base64,{image_base64}'
        
        # ✅ CHECK: Size validation
        size_kb = len(data_url) / 1024
        print(f"📊 Image size: {size_kb:.1f}KB ({len(data_url)} chars)")
        
        if len(data_url) > 500000:  # 500KB limit
            print(f"⚠️ Image too large: {size_kb:.1f}KB - consider reducing quality further")
            return None
        
        return data_url
        
    except Exception as e:
        print(f"❌ Error saving image: {e}")
        return None

def force_schema_refresh():
    """Force SQLAlchemy to refresh its schema cache"""
    try:
        print("🔄 Forcing SQLAlchemy schema refresh...")
        
        # Method 1: Clear all metadata completely
        db.metadata.clear()
        
        # Method 2: Force reflection with explicit bind
        db.metadata.reflect(bind=db.engine)
        
        # Method 3: Direct SQL check to verify column exists
        with db.engine.connect() as conn:
            if is_postgresql():
                # ✅ FIXED: PostgreSQL version
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'dome' AND column_name = 'farm_id'
                """))
                columns = [row[0] for row in result.fetchall()]
                print(f"✅ PostgreSQL check - Dome columns with farm_id: {columns}")
            else:
                # SQLite version
                result = conn.execute(text("PRAGMA table_info(dome)"))
                columns = [row[1] for row in result.fetchall()]
                print(f"✅ SQLite check - Dome columns: {columns}")
            
            if 'farm_id' in columns:
                print("✅ farm_id column confirmed in database")
                
                # Test actual query
                try:
                    test_result = conn.execute(text('SELECT farm_id FROM dome LIMIT 1'))
                    print("✅ farm_id column is queryable")
                    return True
                    
                except Exception as query_error:
                    print(f"❌ Cannot query farm_id: {query_error}")
                    return False
            else:
                print("❌ farm_id column missing from database")
                return False
            
    except Exception as e:
        print(f"⚠️ Schema refresh error: {e}")
        return False

def create_app():
    app = Flask(__name__)
    
    # ✅ AUTO-FIX: Run database column fix on startup (Render only)
    auto_fix_user_table()
    
    # ✅ FIXED: Use the determined database URL
    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    
    # ✅ Production security settings
    if os.getenv('RENDER'):
        # Production settings for Render
        app.config['REMEMBER_COOKIE_SECURE'] = True  # HTTPS only
        app.config['SESSION_COOKIE_SECURE'] = True   # HTTPS only
        app.config['SESSION_COOKIE_HTTPONLY'] = True
        app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    else:
        # Development settings
        app.config['REMEMBER_COOKIE_SECURE'] = False
        app.config['SESSION_COOKIE_SECURE'] = False
        app.config['SESSION_COOKIE_HTTPONLY'] = True
    
    # Session configuration for persistence
    app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=30)
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)
    
    # Mail configuration
    app.config['MAIL_SERVER'] = MAIL_SERVER
    app.config['MAIL_PORT'] = MAIL_PORT
    app.config['MAIL_USE_TLS'] = MAIL_USE_TLS
    app.config['MAIL_USERNAME'] = MAIL_USERNAME
    app.config['MAIL_PASSWORD'] = MAIL_PASSWORD
    app.config['MAIL_DEFAULT_SENDER'] = MAIL_USERNAME
    
    # Upload configuration
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    
    # Initialize mail
    mail.init_app(app)
    
    # Initialize extensions
    db.init_app(app)
    Migrate(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'
    
    # Configure Flask-Login for persistence
    login_manager.remember_cookie_duration = timedelta(days=30)
    login_manager.session_protection = "strong"
    
    # Create necessary directories
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    # ✅ FIXED: Better database initialization with proper schema refresh
    # ✅ FIXED: PostgreSQL-compatible migration code
    with app.app_context():
        try:
            # Create all tables
            db.create_all()
            
            # ✅ FIXED: Add missing columns to existing tables
            try:
                with db.engine.connect() as conn:
                    # ✅ FIXED: Add farm_id column to dome table if it doesn't exist
                    if is_postgresql():
                        # PostgreSQL version
                        result = conn.execute(text("""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = 'dome'
                        """))
                        dome_columns = [row[0] for row in result.fetchall()]
                    else:
                        # SQLite version (for local development)
                        result = conn.execute(text("PRAGMA table_info(dome)"))
                        dome_columns = [row[1] for row in result.fetchall()]
                    
                    print(f"📋 Dome table columns: {dome_columns}")
                    
                    # Add farm_id column if it doesn't exist
                    if 'farm_id' not in dome_columns:
                        print("🔧 Adding farm_id column to dome table...")
                        if is_postgresql():
                            # ✅ FIXED: PostgreSQL syntax with proper table reference
                            conn.execute(text('ALTER TABLE dome ADD COLUMN farm_id INTEGER'))
                            # Add foreign key constraint separately for PostgreSQL
                            try:
                                conn.execute(text('ALTER TABLE dome ADD CONSTRAINT fk_dome_farm FOREIGN KEY (farm_id) REFERENCES farm(id)'))
                            except Exception as fk_error:
                                print(f"⚠️ Could not add foreign key constraint: {fk_error}")
                        else:
                            conn.execute(text("ALTER TABLE dome ADD COLUMN farm_id INTEGER"))
                        conn.commit()
                        print("✅ Added farm_id column to dome table")
                    else:
                        print("✅ farm_id column already exists in dome table")
                    
                    # ✅ FIXED: Check and add grid_settings columns
                    if is_postgresql():
                        # PostgreSQL version
                        result = conn.execute(text("""
                            SELECT column_name 
                            FROM information_schema.columns 
                            WHERE table_name = 'grid_settings'
                        """))
                        grid_columns = [row[0] for row in result.fetchall()]
                    else:
                        # SQLite version (for local development)
                        result = conn.execute(text("PRAGMA table_info(grid_settings)"))
                        grid_columns = [row[1] for row in result.fetchall()]
                    
                    print(f"📋 Grid settings columns: {grid_columns}")
                    
                    # Add missing columns with PostgreSQL-compatible syntax
                    if 'grid_type' not in grid_columns:
                        if is_postgresql():
                            conn.execute(text("ALTER TABLE grid_settings ADD COLUMN grid_type VARCHAR(20) DEFAULT 'dome'"))
                        else:
                            conn.execute(text("ALTER TABLE grid_settings ADD COLUMN grid_type VARCHAR(20) DEFAULT 'dome'"))
                        print("✅ Added grid_type column")
                    
                    if 'user_id' not in grid_columns:
                        conn.execute(text("ALTER TABLE grid_settings ADD COLUMN user_id INTEGER"))
                        print("✅ Added user_id column")
                    
                    if 'created_at' not in grid_columns:
                        if is_postgresql():
                            conn.execute(text("ALTER TABLE grid_settings ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                        else:
                            conn.execute(text("ALTER TABLE grid_settings ADD COLUMN created_at TIMESTAMP"))
                        print("✅ Added created_at column")
                    
                    if 'updated_at' not in grid_columns:
                        if is_postgresql():
                            conn.execute(text("ALTER TABLE grid_settings ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                        else:
                            conn.execute(text("ALTER TABLE grid_settings ADD COLUMN updated_at TIMESTAMP"))
                        print("✅ Added updated_at column")
                    
                    conn.commit()
                    
                    # Update existing records
                    conn.execute(text("UPDATE grid_settings SET grid_type = 'dome' WHERE grid_type IS NULL"))
                    
                    # Get the first user ID to assign to existing settings
                    if is_postgresql():
                        # ✅ FIXED: PostgreSQL table name with quotes
                        result = conn.execute(text('SELECT id FROM "user" LIMIT 1'))
                    else:
                        result = conn.execute(text("SELECT id FROM user LIMIT 1"))
                    first_user = result.fetchone()
                    
                    if first_user:
                        user_id = first_user[0]
                        conn.execute(text("UPDATE grid_settings SET user_id = :user_id WHERE user_id IS NULL"), 
                                   {"user_id": user_id})
                        print(f"✅ Assigned existing settings to user {user_id}")
                    
                    # Set timestamps for existing records
                    from datetime import datetime
                    current_time = datetime.utcnow()
                    conn.execute(text("UPDATE grid_settings SET created_at = :time WHERE created_at IS NULL"), {"time": current_time})
                    conn.execute(text("UPDATE grid_settings SET updated_at = :time WHERE updated_at IS NULL"), {"time": current_time})
                    
                    conn.commit()
                    print("✅ Database migration completed successfully")
                    
            except Exception as e:
                print(f"⚠️ Database migration warning: {e}")
            
            # Force schema refresh to recognize new columns
            if force_schema_refresh():
                print("✅ Database schema refreshed successfully")
            else:
                print("⚠️ Schema refresh had issues, but continuing...")
            
            # Initialize defaults with error handling
            try:
                initialize_defaults()
                print("✅ Database initialized successfully")
            except Exception as init_error:
                print(f"⚠️ Warning during defaults initialization: {init_error}")
                # Continue anyway - the app can still work
                
        except Exception as e:
            print(f"❌ Database initialization error: {e}")
            # Don't crash the app, just log the error
    
    return app

@login_manager.user_loader
def load_user(user_id):
    # ✅ FIXED: Use db.session.get() instead of User.query.get() for SQLAlchemy 2.0 compatibility
    return db.session.get(User, int(user_id))

def send_reset_email(email, token, username):
    """Send password reset email using Flask-Mail"""
    try:
        reset_url = f"{request.url_root}reset_password?token={token}"
        msg = Message(
            subject="Password Reset Request",
            recipients=[email],
            sender=os.getenv('MAIL_USERNAME'),
            body=f"""Password reset requested for: {email} ({username})
Reset URL: {reset_url}

If you did not request this, please ignore this email.
"""
        )
        mail.send(msg)
        print(f"Password reset email sent to: {email}")
        return True
    except Exception as e:
        print(f"Failed to send reset email: {e}")
        raise

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS
def save_image_to_database(image_file, entity_type, entity_id):
    """Save image as base64 in database instead of filesystem"""
    try:
        # Read and process the image
        image_data = image_file.read()
        
        # Convert to base64
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        
        # Get file extension
        filename = image_file.filename.lower()
        if filename.endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            ext = filename.split('.')[-1]
        else:
            ext = 'jpg'
        
        # Create data URL
        mime_type = f'image/{ext}' if ext != 'jpg' else 'image/jpeg'
        data_url = f'data:{mime_type};base64,{image_base64}'
        
        return data_url
        
    except Exception as e:
        print(f"❌ Error saving image: {e}")
        return None
def initialize_scheduler():
    """Initialize the daily life updater when the app starts"""
    global life_updater
    if life_updater:
        try:
            life_updater.start_scheduler()
            print("Tree life updater scheduler initialized successfully")
        except Exception as e:
            print(f"Failed to initialize scheduler: {str(e)}")
    else:
        print("⚠️ TreeLifeUpdater not available, skipping scheduler initialization")

app = create_app()

with app.app_context():
    initialize_scheduler()

# ============= AUTHENTICATION ROUTES =============
with app.app_context():
    try:
        db.create_all()
        print("✅ Database tables created/verified")
        
    except Exception as e:
        print(f"⚠️ Database initialization warning: {e}")
 
@app.route('/register', methods=['GET', 'POST'])
def register():
    try:
        if request.method == 'POST':
            data = request.get_json() if request.is_json else request.form
            
            username = data.get('username', '').strip()
            email = data.get('email', '').strip()
            password = data.get('password', '')
            confirm_password = data.get('confirm_password', '')
            
            print(f"Registration attempt for: {username}")
            
            # Validation
            if not username or not email or not password:
                return jsonify({'success': False, 'error': 'All fields are required'}), 400
            
            if len(username) < 3:
                return jsonify({'success': False, 'error': 'Username must be at least 3 characters'}), 400
            
            if len(password) < 6:
                return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
            
            if password != confirm_password:
                return jsonify({'success': False, 'error': 'Passwords do not match'}), 400
            
            # Check if user already exists
            if User.query.filter_by(username=username).first():
                return jsonify({'success': False, 'error': 'Username already exists'}), 400
            
            if User.query.filter_by(email=email).first():
                return jsonify({'success': False, 'error': 'Email already registered'}), 400
            
            # Create new user
            user = User(username=username, email=email)
            user.set_password(password)
            
            try:
                db.session.add(user)
                db.session.commit()
                
                # Auto login after registration
                login_user(user)
                print(f"Registration successful for: {username}")
                
                return jsonify({'success': True, 'message': 'Registration successful'})
                
            except Exception as e:
                db.session.rollback()
                print(f"Database error during registration: {e}")
                return jsonify({'success': False, 'error': 'Registration failed'}), 500
        
        # GET request - show the registration form
        return render_template('auth/register.html')
        
    except Exception as e:
        print(f"❌ Register error: {e}")
        if request.method == 'POST':
            return jsonify({'success': False, 'message': f'Registration failed: {str(e)}'})
        else:
            flash('Registration system temporarily unavailable', 'error')
            return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            
            username = data.get('username', '').strip()
            password = data.get('password', '')
            remember = data.get('remember', True)  # ✅ Default to True for persistence
            
            print(f"🔐 Login attempt for: {username}")
            
            if not username or not password:
                error_msg = 'Username and password are required'
                print(f"❌ Login validation error: {error_msg}")
                return jsonify({'success': False, 'error': error_msg}), 400
            
            # Find user by username or email
            user = User.query.filter(
                (User.username == username) | (User.email == username)
            ).first()
            
            print(f"👤 User found: {user is not None}")
            
            if user and user.check_password(password):
                try:
                    # ✅ FIXED: Calculate days since last login BEFORE updating
                    days_since_last = user.get_days_since_last_login()
                    was_first_login = user.last_login is None
                    
                    # ✅ FIXED: Update last login timestamp and tree reference times
                    user.update_last_login()
                    db.session.commit()
                    
                    # ✅ FIXED: Set permanent session and remember user
                    session.permanent = True
                    login_user(user, remember=remember, duration=timedelta(days=30))
                    
                    print(f"✅ Login successful for user: {user.username} (Remember: {remember})")
                    
                    # ✅ FIXED: Prepare response with tree growth info
                    response_data = {
                        'success': True, 
                        'message': 'Login successful', 
                        'redirect': '/farms',
                        'user': {
                            'username': user.username,
                            'login_count': user.login_count,
                            'days_since_last_login': days_since_last,
                            'is_first_login': was_first_login
                        }
                    }
                    
                    # ✅ FIXED: Add tree growth message if applicable
                    if not was_first_login and days_since_last > 0:
                        tree_count = Tree.query.filter_by(user_id=user.id).count()
                        if tree_count > 0:
                            growth_message = f"Welcome back! Your {tree_count} tree{'s' if tree_count != 1 else ''} {'have' if tree_count != 1 else 'has'} grown for {days_since_last} day{'s' if days_since_last != 1 else ''} since your last visit."
                            response_data['growth_message'] = growth_message
                            print(f"🌱 Tree growth: {growth_message}")
                    elif was_first_login:
                        response_data['welcome_message'] = "Welcome to your farm! Start by creating your first dome and planting trees."
                        print(f"🎉 First login for user: {user.username}")
                    
                    return jsonify(response_data)
                    
                except Exception as login_process_error:
                    print(f"❌ Error during login process: {login_process_error}")
                    db.session.rollback()
                    return jsonify({
                        'success': False, 
                        'error': 'Login process failed. Please try again.'
                    }), 500
                    
            else:
                print(f"❌ Invalid credentials for: {username}")
                return jsonify({
                    'success': False, 
                    'error': 'Invalid username or password'
                }), 401
                
        except Exception as e:
            print(f"❌ Login error: {e}")
            import traceback
            print(f"❌ Login traceback: {traceback.format_exc()}")
            return jsonify({
                'success': False, 
                'error': 'Login failed due to server error'
            }), 500
    
    # ✅ FIXED: Handle GET request
    try:
        return render_template('auth/login.html')
    except Exception as template_error:
        print(f"❌ Template error: {template_error}")
        # Fallback simple login form
        return '''
        <!DOCTYPE html>
        <html>
        <head><title>Login</title></head>
        <body>
            <h2>Login</h2>
            <form method="post" action="/login">
                <div>
                    <label>Username/Email:</label>
                    <input type="text" name="username" required>
                </div>
                <div>
                    <label>Password:</label>
                    <input type="password" name="password" required>
                </div>
                <div>
                    <input type="checkbox" name="remember" checked>
                    <label>Remember me</label>
                </div>
                <button type="submit">Login</button>
            </form>
            <p><a href="/register">Don't have an account? Register here</a></p>
        </body>
        </html>
        '''
@app.route('/api/tree/<int:tree_id>/update_mother', methods=['POST'])
@login_required
def update_tree_mother(tree_id):
    """Update the mother plant relationship for a cutting tree"""
    try:
        # Get the cutting tree
        cutting_tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not cutting_tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        data = request.get_json()
        new_mother_id = data.get('new_mother_id')
        transfer_notes = data.get('transfer_notes', '')
        
        if not new_mother_id:
            return jsonify({'success': False, 'error': 'New mother ID is required'}), 400
        
        # Get the new mother tree
        new_mother = Tree.query.filter_by(id=new_mother_id, user_id=current_user.id).first()
        if not new_mother:
            return jsonify({'success': False, 'error': 'New mother tree not found'}), 404
        
        # Verify the new mother is actually a mother plant
        if getattr(new_mother, 'plant_type', 'mother') != 'mother':
            return jsonify({'success': False, 'error': 'Target tree is not a mother plant'}), 400
        
        # Store old mother info for logging
        old_mother_id = getattr(cutting_tree, 'mother_plant_id', None)
        old_mother = None
        if old_mother_id:
            old_mother = Tree.query.filter_by(id=old_mother_id, user_id=current_user.id).first()
        
        # Update the cutting tree's mother relationship
        cutting_tree.mother_plant_id = new_mother_id
        cutting_tree.plant_type = 'cutting'  # Ensure it's marked as cutting
        
        # Add transfer notes to the cutting tree's info
        if transfer_notes:
            current_info = getattr(cutting_tree, 'info', '') or ''
            if current_info:
                cutting_tree.info = f"{current_info}\n\n{transfer_notes}"
            else:
                cutting_tree.info = transfer_notes
        
        # Update cutting notes if available
        if hasattr(cutting_tree, 'cutting_notes'):
            current_notes = cutting_tree.cutting_notes or ''
            transfer_note = f"Transferred from mother '{old_mother.name if old_mother else 'Unknown'}' to '{new_mother.name}'"
            if current_notes:
                cutting_tree.cutting_notes = f"{current_notes}\n{transfer_note}"
            else:
                cutting_tree.cutting_notes = transfer_note
        
        db.session.commit()
        
        print(f"✅ Transferred cutting '{cutting_tree.name}' from mother {old_mother_id} to mother {new_mother_id}")
        
        return jsonify({
            'success': True,
            'message': f'Successfully transferred cutting "{cutting_tree.name}" to new mother "{new_mother.name}"',
            'cutting_tree': {
                'id': cutting_tree.id,
                'name': cutting_tree.name,
                'old_mother_id': old_mother_id,
                'old_mother_name': old_mother.name if old_mother else 'Unknown',
                'new_mother_id': new_mother_id,
                'new_mother_name': new_mother.name
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error updating tree mother relationship: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tree/<int:tree_id>/pause_life', methods=['POST'])
@login_required
def pause_tree_life(tree_id):
    """Pause life day counting for a tree"""
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        if tree.pause_life_counting():
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Tree life counting paused',
                'tree': tree.to_dict()
            })
        else:
            return jsonify({'success': False, 'error': 'Tree is already paused'}), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tree/<int:tree_id>/resume_life', methods=['POST'])
@login_required
def resume_tree_life(tree_id):
    """Resume life day counting for a tree"""
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        if tree.resume_life_counting():
            db.session.commit()
            return jsonify({
                'success': True,
                'message': 'Tree life counting resumed',
                'tree': tree.to_dict()
            })
        else:
            return jsonify({'success': False, 'error': 'Tree is not paused'}), 400
            
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tree/<int:tree_id>/adjust_life', methods=['POST'])
@login_required
def adjust_tree_life(tree_id):
    """Manually adjust tree life days"""
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        data = request.get_json()
        adjustment = data.get('adjustment', 0)
        
        if not isinstance(adjustment, int):
            return jsonify({'success': False, 'error': 'Adjustment must be an integer'}), 400
        
        new_life_days = tree.adjust_life_days(adjustment)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Tree life days adjusted by {adjustment} days',
            'new_life_days': new_life_days,
            'tree': tree.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return jsonify({'success': True, 'message': 'Logged out successfully'})
# ============= FARM MANAGEMENT ROUTES =============
# ✅ MAKE SURE you only have ONE grid route like this:
@app.route('/grid/<int:dome_id>')
@login_required
def grid(dome_id):
    """Enhanced grid route with improved drag area persistence"""
    try:
        print(f"🎯 Grid route called for dome_id: {dome_id}")
        print(f"🎯 User ID: {current_user.id}")
        
        # Get the dome and verify ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            print(f"❌ Dome {dome_id} not found for user {current_user.id}")
            flash('Dome not found', 'error')
            return redirect(url_for('farms'))
        
        print(f"✅ Dome found: {dome.name}")
        
        # Get all trees for this dome with explicit loading
        trees = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
        print(f"✅ Found {len(trees)} trees for dome {dome_id}")
        
        # Convert trees to JSON-serializable dictionaries
        trees_data = []
        for tree in trees:
            try:
                tree_dict = {
                    'id': tree.id,
                    'name': tree.name,
                    'breed': tree.breed or '',
                    'dome_id': tree.dome_id,
                    'internal_row': tree.internal_row,
                    'internal_col': tree.internal_col,
                    'image_url': tree.image_url,
                    'info': tree.info or '',
                    'life_days': tree.life_days or 0,
                    'user_id': tree.user_id,
                    'plant_type': getattr(tree, 'plant_type', 'mother'),
                    'cutting_notes': getattr(tree, 'cutting_notes', ''),
                    # ✅ CRITICAL: Include mother_plant_id for relationship preservation
                    'mother_plant_id': getattr(tree, 'mother_plant_id', None),
                    'life_stage': tree.get_life_stage() if hasattr(tree, 'get_life_stage') else 'Unknown',
                    'age_category': tree.get_age_category() if hasattr(tree, 'get_age_category') else 'unknown',
                    'position_string': f"({tree.internal_row}, {tree.internal_col})",
                    'created_at': tree.created_at.isoformat() if tree.created_at else None,
                    'updated_at': tree.updated_at.isoformat() if tree.updated_at else None
                }
                trees_data.append(tree_dict)
                print(f"🌳 Grid Tree {tree.id} '{tree.name}' - Breed: '{tree.breed or 'None'}' - Position: ({tree.internal_row}, {tree.internal_col})")
                
            except Exception as tree_error:
                print(f"⚠️ Error processing tree {tree.id}: {tree_error}")
                # Add basic tree data even if enhanced processing fails
                basic_tree_dict = {
                    'id': tree.id,
                    'name': tree.name,
                    'breed': tree.breed or '',
                    'dome_id': tree.dome_id,
                    'internal_row': tree.internal_row,
                    'internal_col': tree.internal_col,
                    'image_url': tree.image_url,
                    'info': tree.info or '',
                    'life_days': tree.life_days or 0,
                    'user_id': tree.user_id,
                    'plant_type': 'mother',
                    'cutting_notes': '',
                    'life_stage': 'Unknown',
                    'age_category': 'unknown',
                    'position_string': f"({tree.internal_row}, {tree.internal_col})",
                    'created_at': None,
                    'updated_at': None
                }
                trees_data.append(basic_tree_dict)
        
        # ✅ ENHANCED: Load drag areas with better error handling and explicit relationships
        drag_areas = []
        drag_areas_count = 0
        drag_areas_errors = []
        
        try:
            # ✅ FIXED: Use explicit join to ensure relationships are loaded
            from sqlalchemy.orm import joinedload
            
            try:
                # Try to load with relationships
                drag_areas_db = DragArea.query.options(
                    joinedload(DragArea.drag_area_trees).joinedload(DragAreaTree.tree)
                ).filter_by(dome_id=dome_id).all()
                print(f"✅ Loaded drag areas with relationships using joinedload")
            except Exception as join_error:
                print(f"⚠️ Joinedload failed, falling back to basic query: {join_error}")
                # Fallback to basic query
                drag_areas_db = DragArea.query.filter_by(dome_id=dome_id).all()
            
            drag_areas_count = len(drag_areas_db)
            print(f"🔍 Found {drag_areas_count} drag areas in database for dome {dome_id}")
            
            for area in drag_areas_db:
                try:
                    # ✅ ENHANCED: Validate area data before processing
                    if not area:
                        drag_areas_errors.append("Null drag area found")
                        continue
                    
                    if not hasattr(area, 'id') or area.id is None:
                        drag_areas_errors.append("Drag area missing ID")
                        continue
                    
                    # ✅ ENHANCED: Get trees in this drag area with better error handling
                    area_trees = []
                    tree_ids = []
                    
                    try:
                        # Check if drag_area_trees relationship exists and is loaded
                        if hasattr(area, 'drag_area_trees'):
                            drag_area_trees = area.drag_area_trees
                            
                            # If relationship is not loaded, query explicitly
                            if not drag_area_trees:
                                drag_area_trees = DragAreaTree.query.filter_by(drag_area_id=area.id).all()
                                print(f"🔄 Explicitly loaded {len(drag_area_trees)} drag area trees for area {area.id}")
                            
                            for dat in drag_area_trees:
                                if dat and hasattr(dat, 'tree_id') and dat.tree_id:
                                    tree_ids.append(dat.tree_id)
                                    
                                    # Get tree data
                                    tree = dat.tree if hasattr(dat, 'tree') and dat.tree else None
                                    if not tree:
                                        # Query tree explicitly if not loaded
                                        tree = Tree.query.filter_by(id=dat.tree_id).first()
                                    
                                    if tree:
                                        tree_data = {
                                            'id': tree.id,
                                            'name': tree.name,
                                            'breed': tree.breed or '',
                                            'relative_row': getattr(dat, 'relative_row', 0),
                                            'relative_col': getattr(dat, 'relative_col', 0),
                                            'absolute_row': tree.internal_row,
                                            'absolute_col': tree.internal_col
                                        }
                                        area_trees.append(tree_data)
                                    else:
                                        print(f"⚠️ Tree {dat.tree_id} not found for drag area {area.id}")
                        else:
                            print(f"⚠️ No drag_area_trees relationship for area {area.id}")
                            
                    except Exception as tree_error:
                        error_msg = f"Error loading trees for drag area {area.id}: {tree_error}"
                        print(f"⚠️ {error_msg}")
                        drag_areas_errors.append(error_msg)
                    
                    # ✅ ENHANCED: Create drag area data structure with validation
                    try:
                        drag_area_data = {
                            'id': area.id,
                            'name': area.name or f'Drag Area {area.id}',
                            'color': getattr(area, 'color', '#007bff') or '#007bff',
                            'minRow': area.min_row if area.min_row is not None else 0,
                            'maxRow': area.max_row if area.max_row is not None else 0,
                            'minCol': area.min_col if area.min_col is not None else 0,
                            'maxCol': area.max_col if area.max_col is not None else 0,
                            'width': getattr(area, 'width', None) or (area.max_col - area.min_col + 1),
                            'height': getattr(area, 'height', None) or (area.max_row - area.min_row + 1),
                            'visible': getattr(area, 'visible', True),
                            'tree_ids': tree_ids,
                            'tree_count': len(area_trees),
                            'trees': area_trees,
                            'cell_count': (getattr(area, 'width', None) or (area.max_col - area.min_col + 1)) * (getattr(area, 'height', None) or (area.max_row - area.min_row + 1)),
                            'bounds_string': f"({area.min_row},{area.min_col}) to ({area.max_row},{area.max_col})",
                            'size_string': f"{getattr(area, 'width', None) or (area.max_col - area.min_col + 1)}×{getattr(area, 'height', None) or (area.max_row - area.min_row + 1)}",
                            'created_at': area.created_at.isoformat() if hasattr(area, 'created_at') and area.created_at else None,
                            'updated_at': area.updated_at.isoformat() if hasattr(area, 'updated_at') and area.updated_at else None
                        }
                        
                        # ✅ ENHANCED: Validate drag area data integrity
                        if drag_area_data['width'] <= 0 or drag_area_data['height'] <= 0:
                            print(f"⚠️ Invalid area dimensions for area {area.id}: {drag_area_data['width']}x{drag_area_data['height']}")
                            drag_area_data['width'] = max(1, drag_area_data['width'])
                            drag_area_data['height'] = max(1, drag_area_data['height'])
                        
                        drag_areas.append(drag_area_data)
                        
                        print(f"🔲 Drag Area {area.id} '{drag_area_data['name']}' - Position: ({drag_area_data['minRow']},{drag_area_data['minCol']}) to ({drag_area_data['maxRow']},{drag_area_data['maxCol']}) - Trees: {len(area_trees)} - Visible: {drag_area_data['visible']}")
                        
                    except Exception as data_error:
                        error_msg = f"Error creating data structure for drag area {area.id}: {data_error}"
                        print(f"⚠️ {error_msg}")
                        drag_areas_errors.append(error_msg)
                        continue
                    
                except Exception as area_error:
                    error_msg = f"Error processing drag area {getattr(area, 'id', 'unknown')}: {area_error}"
                    print(f"⚠️ {error_msg}")
                    drag_areas_errors.append(error_msg)
                    continue
                    
        except Exception as drag_error:
            error_msg = f"Error loading drag areas from database: {drag_error}"
            print(f"❌ {error_msg}")
            drag_areas_errors.append(error_msg)
            import traceback
            print(f"❌ Drag areas traceback: {traceback.format_exc()}")
            drag_areas = []
        
        # ✅ ENHANCED: Calculate statistics with error handling
        try:
            area_stats = {
                'drag_areas_count': len(drag_areas),
                'total_areas': len(drag_areas),
                'total_drag_trees': sum(area.get('tree_count', 0) for area in drag_areas),
                'visible_drag_areas': len([area for area in drag_areas if area.get('visible', True)]),
                'drag_areas_db_count': drag_areas_count,
                'areas_loaded_successfully': len(drag_areas) == drag_areas_count and len(drag_areas_errors) == 0,
                'loading_errors': drag_areas_errors,
                'error_count': len(drag_areas_errors),
                # Regular areas disabled
                'regular_areas_count': 0,
                'total_regular_cells': 0,
                'total_regular_trees': 0,
                'visible_regular_areas': 0,
                'regular_areas_db_count': 0
            }
        except Exception as stats_error:
            print(f"⚠️ Error calculating area stats: {stats_error}")
            area_stats = {
                'drag_areas_count': len(drag_areas),
                'total_areas': len(drag_areas),
                'total_drag_trees': 0,
                'visible_drag_areas': len(drag_areas),
                'drag_areas_db_count': drag_areas_count,
                'areas_loaded_successfully': False,
                'loading_errors': drag_areas_errors,
                'error_count': len(drag_areas_errors),
                'regular_areas_count': 0,
                'total_regular_cells': 0,
                'total_regular_trees': 0,
                'visible_regular_areas': 0,
                'regular_areas_db_count': 0
            }
        
        # ✅ Breed analysis
        try:
            trees_with_breeds = [tree for tree in trees if tree.breed and tree.breed.strip()]
            unique_breeds = list(set([tree.breed for tree in trees_with_breeds]))
            breed_summary = f"{len(trees_with_breeds)}/{len(trees)} trees have breeds"
            
            print(f"🧬 Breed summary: {breed_summary}")
            print(f"🧬 Unique breeds: {unique_breeds}")
        except Exception as breed_error:
            print(f"⚠️ Error analyzing breeds: {breed_error}")
            trees_with_breeds = []
            unique_breeds = []
            breed_summary = "Breed analysis failed"
        
        # ✅ ENHANCED: Log loading results
        print(f"📊 Drag Areas Loading Summary:")
        print(f"   - Database query returned: {drag_areas_count} areas")
        print(f"   - Successfully processed: {len(drag_areas)} areas")
        print(f"   - Processing errors: {len(drag_areas_errors)}")
        print(f"   - Visible areas: {area_stats['visible_drag_areas']}")
        print(f"   - Total trees in areas: {area_stats['total_drag_trees']}")
        
        if drag_areas_errors:
            print(f"⚠️ Drag area loading errors:")
            for error in drag_areas_errors:
                print(f"   - {error}")
        
        print(f"🎯 Rendering grid.html for dome {dome_id} with area stats: {area_stats}")
        
        # ✅ ENHANCED: Template data with comprehensive error information
        try:
            template_data = {
                'dome': dome,
                'trees_data': trees_data,
                'trees': trees,
                'drag_areas': drag_areas,
                'regular_areas': [],  # Empty - no regular areas
                'area_stats': area_stats,
                'breed_summary': breed_summary,
                'unique_breeds': unique_breeds,
                'tree_count': len(trees),
                'rows': dome.internal_rows or 10,
                'cols': dome.internal_cols or 10,
                'dome_id': dome_id,
                'dome_name': dome.name,
                'dome_size_string': f"{dome.internal_rows or 10}×{dome.internal_cols or 10}",
                'timestamp': int(time.time()),
                'current_user': current_user,
                'debug_info': {
                    'areas_loaded_successfully': area_stats.get('areas_loaded_successfully', False),
                    'drag_areas_db_count': drag_areas_count,
                    'drag_areas_processed': len(drag_areas),
                    'loading_errors': drag_areas_errors,
                    'error_count': len(drag_areas_errors),
                    'system_mode': 'DRAG_AREAS_ONLY',
                    'refresh_timestamp': datetime.utcnow().isoformat()
                }
            }
            
            # ✅ ENHANCED: Detailed template data logging
            print(f"📊 Template data summary:")
            print(f"   - Dome: {dome.name} ({dome.internal_rows}x{dome.internal_cols})")
            print(f"   - Trees: {len(trees_data)} items")
            print(f"   - Drag Areas: {len(drag_areas)} items (DB: {drag_areas_count})")
            print(f"   - Regular Areas: 0 items (DISABLED)")
            print(f"   - Visible Drag Areas: {area_stats['visible_drag_areas']}")
            print(f"   - Areas loaded successfully: {area_stats.get('areas_loaded_successfully', False)}")
            print(f"   - Loading errors: {len(drag_areas_errors)}")
            print(f"   - System Mode: DRAG_AREAS_ONLY")
            print(f"   - Refresh timestamp: {template_data['debug_info']['refresh_timestamp']}")
            
            return render_template('grid.html', **template_data)
            
        except Exception as template_error:
            print(f"❌ Error preparing template data: {template_error}")
            import traceback
            print(f"❌ Template preparation traceback: {traceback.format_exc()}")
            
            # ✅ ENHANCED: Fallback with error information
            fallback_data = {
                'dome': dome,
                'trees_data': trees_data,
                'trees': trees,
                'drag_areas': [],
                'regular_areas': [],
                'area_stats': {
                    'drag_areas_count': 0, 
                    'regular_areas_count': 0,
                    'areas_loaded_successfully': False,
                    'loading_errors': [f"Template preparation failed: {str(template_error)}"],
                    'error_count': 1
                },
                'breed_summary': 'Data loading failed',
                'unique_breeds': [],
                'tree_count': len(trees),
                'rows': dome.internal_rows or 10,
                'cols': dome.internal_cols or 10,
                'current_user': current_user,
                'debug_info': {
                    'fallback_mode': True,
                    'template_error': str(template_error)
                }
            }
            
            return render_template('grid.html', **fallback_data)
                                 
    except Exception as e:
        print(f"❌ Critical error in grid route: {str(e)}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        flash('An error occurred while loading the grid', 'error')
        return redirect(url_for('farms'))
@app.route('/debug/drag_areas/<int:dome_id>')
@login_required
def debug_drag_areas_detailed(dome_id):
    """Comprehensive debug route for drag area issues"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'error': 'Dome not found'}), 404
        
        debug_data = {
            'dome_info': {
                'id': dome.id,
                'name': dome.name,
                'size': f"{dome.internal_rows}x{dome.internal_cols}",
                'user_id': dome.user_id,
                'farm_id': dome.farm_id
            },
            'database_checks': {},
            'relationship_checks': {},
            'data_integrity': {},
            'recommendations': []
        }
        
        # Check DragArea table
        try:
            total_drag_areas = DragArea.query.filter_by(dome_id=dome_id).count()
            debug_data['database_checks']['drag_areas_count'] = total_drag_areas
            debug_data['database_checks']['drag_areas_table_exists'] = True
        except Exception as e:
            debug_data['database_checks']['drag_areas_table_exists'] = False
            debug_data['database_checks']['drag_areas_error'] = str(e)
            debug_data['recommendations'].append("DragArea table may not exist or have schema issues")
        
        # Check DragAreaTree table
        try:
            total_drag_area_trees = DragAreaTree.query.join(DragArea).filter(DragArea.dome_id == dome_id).count()
            debug_data['database_checks']['drag_area_trees_count'] = total_drag_area_trees
            debug_data['database_checks']['drag_area_trees_table_exists'] = True
        except Exception as e:
            debug_data['database_checks']['drag_area_trees_table_exists'] = False
            debug_data['database_checks']['drag_area_trees_error'] = str(e)
            debug_data['recommendations'].append("DragAreaTree table may not exist or have schema issues")
        
        # Test relationship loading
        try:
            from sqlalchemy.orm import joinedload
            areas_with_relationships = DragArea.query.options(
                joinedload(DragArea.drag_area_trees).joinedload(DragAreaTree.tree)
            ).filter_by(dome_id=dome_id).all()
            
            debug_data['relationship_checks']['joinedload_success'] = True
            debug_data['relationship_checks']['areas_loaded'] = len(areas_with_relationships)
            
            # Check each area's relationships
            for area in areas_with_relationships:
                area_debug = {
                    'id': area.id,
                    'name': area.name,
                    'has_drag_area_trees_attr': hasattr(area, 'drag_area_trees'),
                    'drag_area_trees_count': len(area.drag_area_trees) if hasattr(area, 'drag_area_trees') else 0,
                    'trees_with_data': 0
                }
                
                if hasattr(area, 'drag_area_trees'):
                    for dat in area.drag_area_trees:
                        if hasattr(dat, 'tree') and dat.tree:
                            area_debug['trees_with_data'] += 1
                
                debug_data['relationship_checks'][f'area_{area.id}'] = area_debug
                
        except Exception as e:
            debug_data['relationship_checks']['joinedload_success'] = False
            debug_data['relationship_checks']['joinedload_error'] = str(e)
            debug_data['recommendations'].append("Relationship loading failed - may need manual queries")
        
        # Data integrity checks
        try:
            areas = DragArea.query.filter_by(dome_id=dome_id).all()
            integrity_issues = []
            
            for area in areas:
                issues = []
                
                if not area.name or area.name.strip() == '':
                    issues.append("Missing or empty name")
                
                if area.min_row is None or area.max_row is None or area.min_col is None or area.max_col is None:
                    issues.append("Missing boundary coordinates")
                
                if area.min_row > area.max_row or area.min_col > area.max_col:
                    issues.append("Invalid boundary coordinates")
                
                if hasattr(area, 'width') and hasattr(area, 'height'):
                    if area.width <= 0 or area.height <= 0:
                        issues.append("Invalid dimensions")
                
                if issues:
                    integrity_issues.append({
                        'area_id': area.id,
                        'area_name': area.name,
                        'issues': issues
                    })
            
            debug_data['data_integrity']['total_areas_checked'] = len(areas)
            debug_data['data_integrity']['areas_with_issues'] = len(integrity_issues)
            debug_data['data_integrity']['issues'] = integrity_issues
            
            if integrity_issues:
                debug_data['recommendations'].append(f"Fix data integrity issues in {len(integrity_issues)} areas")
            
        except Exception as e:
            debug_data['data_integrity']['check_failed'] = True
            debug_data['data_integrity']['error'] = str(e)
        
        # Generate recommendations
        if not debug_data['recommendations']:
            debug_data['recommendations'].append("No issues detected - drag areas should load properly")
        
        return jsonify(debug_data)
        
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
@app.route('/debug/grid/<int:dome_id>/drag_areas')
@login_required
def debug_grid_drag_areas(dome_id):
    """Debug endpoint specifically for grid drag areas"""
    try:
        # Get dome
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'error': 'Dome not found'}), 404
        
        # Get drag areas exactly as the grid route does
        drag_areas_db = DragArea.query.filter_by(dome_id=dome_id).all()
        
        debug_data = {
            'dome': {
                'id': dome.id,
                'name': dome.name,
                'size': f"{dome.internal_rows}x{dome.internal_cols}",
                'farm_id': dome.farm_id
            },
            'database_query': {
                'total_drag_areas_found': len(drag_areas_db),
                'query_used': f"DragArea.query.filter_by(dome_id={dome_id}).all()"
            },
            'drag_areas_raw': [
                {
                    'id': area.id,
                    'name': area.name,
                    'bounds': f"({area.min_row},{area.min_col}) to ({area.max_row},{area.max_col})",
                    'size': f"{area.width}x{area.height}",
                    'visible': area.visible,
                    'color': area.color,
                    'tree_associations': len(area.drag_area_trees) if hasattr(area, 'drag_area_trees') else 'N/A'
                }
                for area in drag_areas_db
            ],
            'template_format': [],
            'potential_issues': []
        }
        
        # Convert to template format
        for area in drag_areas_db:
            try:
                template_area = {
                    'id': area.id,
                    'name': area.name,
                    'color': area.color,
                    'minRow': area.min_row,
                    'maxRow': area.max_row,
                    'minCol': area.min_col,
                    'maxCol': area.max_col,
                    'width': area.width,
                    'height': area.height,
                    'visible': area.visible,
                    'tree_count': len(area.drag_area_trees) if hasattr(area, 'drag_area_trees') else 0
                }
                debug_data['template_format'].append(template_area)
            except Exception as convert_error:
                debug_data['potential_issues'].append(f"Error converting area {area.id}: {str(convert_error)}")
        
        # Check for potential issues
        if len(drag_areas_db) == 0:
            debug_data['potential_issues'].append("No drag areas found in database for this dome")
        
        visible_areas = [area for area in drag_areas_db if area.visible]
        if len(visible_areas) != len(drag_areas_db):
            debug_data['potential_issues'].append(f"Only {len(visible_areas)}/{len(drag_areas_db)} drag areas are visible")
        
        return jsonify(debug_data)
        
    except Exception as e:
        return jsonify({'error': str(e), 'traceback': traceback.format_exc()}), 500
@app.route('/test/grid/<int:dome_id>')
@login_required
def test_grid(dome_id):
    """Test route to verify grid access"""
    try:
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        trees = Tree.query.filter_by(dome_id=dome_id).all()
        
        return f"""
        <h2>Grid Test for Dome {dome_id}</h2>
        <p><strong>Dome found:</strong> {dome is not None}</p>
        <p><strong>Dome name:</strong> {dome.name if dome else 'Not found'}</p>
        <p><strong>Trees count:</strong> {len(trees)}</p>
        <p><strong>User ID:</strong> {current_user.id}</p>
        <p><strong>Grid template exists:</strong> {os.path.exists('templates/grid.html')}</p>
        <hr>
        <a href="/grid/{dome_id}">Try Normal Grid Route</a><br>
        <a href="/tree_info/{trees[0].id if trees else 1}">Back to Tree Info</a>
        """
        
    except Exception as e:
        return f"<h2>Error:</h2><pre>{str(e)}</pre>"
@app.route('/debug/grid/<int:dome_id>')
@login_required
def debug_grid_route(dome_id):
    """Enhanced debug route"""
    try:
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        trees = Tree.query.filter_by(dome_id=dome_id).all()
        
        # Check for route conflicts
        grid_routes = []
        for rule in app.url_map.iter_rules():
            if 'grid' in str(rule):
                grid_routes.append({
                    'rule': str(rule),
                    'endpoint': rule.endpoint,
                    'methods': list(rule.methods)
                })
        
        debug_info = {
            'dome_id': dome_id,
            'user_id': current_user.id,
            'dome_found': dome is not None,
            'dome_name': dome.name if dome else 'Not found',
            'dome_farm_id': dome.farm_id if dome else None,
            'trees_count': len(trees),
            'trees_data': [
                {
                    'id': t.id, 
                    'name': t.name, 
                    'row': getattr(t, 'row', None),
                    'col': getattr(t, 'col', None),
                    'internal_row': getattr(t, 'internal_row', None),
                    'internal_col': getattr(t, 'internal_col', None)
                } for t in trees
            ],
            'grid_template_exists': os.path.exists('templates/grid.html'),
            'grid_routes': grid_routes,
            'route_working': True
        }
        
        return f"<pre>{json.dumps(debug_info, indent=2)}</pre>"
        
    except Exception as e:
        import traceback
        return f"<pre>Error: {str(e)}\n\nTraceback:\n{traceback.format_exc()}</pre>"
@app.route('/fix_tree_columns')
def fix_tree_columns():
    try:
        # Update trees to use internal_row/internal_col
        trees = Tree.query.all()
        for tree in trees:
            if hasattr(tree, 'row') and hasattr(tree, 'col'):
                tree.internal_row = tree.row
                tree.internal_col = tree.col
        
        db.session.commit()
        return f"Fixed {len(trees)} trees"
        
    except Exception as e:
        return f"Error: {str(e)}"
@app.route('/debug/grid/<int:dome_id>')
@login_required
def debug_grid(dome_id):
    """Debug route to test grid access"""
    try:
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        trees = Tree.query.filter_by(dome_id=dome_id).all()
        
        debug_info = {
            'dome_id': dome_id,
            'dome_found': dome is not None,
            'dome_name': dome.name if dome else 'Not found',
            'trees_count': len(trees),
            'user_id': current_user.id,
            'route_working': True,
            'template_should_be': 'grid.html'
        }
        
        return f"<pre>{json.dumps(debug_info, indent=2)}</pre>"
        
    except Exception as e:
        return f"<pre>Error: {str(e)}</pre>"
@app.route('/debug/routes')
def debug_routes():
    """Debug route to see all registered routes"""
    routes = []
    for rule in app.url_map.iter_rules():
        routes.append({
            'endpoint': rule.endpoint,
            'methods': list(rule.methods),
            'rule': str(rule)
        })
    
    # Filter grid routes
    grid_routes = [r for r in routes if 'grid' in r['rule']]
    
    return f"<h3>Grid Routes:</h3><pre>{json.dumps(grid_routes, indent=2)}</pre>"
@app.route('/farms')
@login_required
def farms():
    try:
        # ✅ FIXED: Get FARM-specific grid settings (not dome settings)
        farm_grid_settings = get_grid_settings('farm', current_user.id)
        
        # Get all farms for this user
        farms = Farm.query.filter_by(user_id=current_user.id).all()
        
        print(f"✅ Found {len(farms)} farms")
        print(f"🔧 Farm grid settings: {farm_grid_settings.rows}x{farm_grid_settings.cols}")
        
        return render_template('farm.html', 
                             farms=farms,
                             grid_rows=farm_grid_settings.rows,
                             grid_cols=farm_grid_settings.cols,
                             timestamp=int(time.time()),
                             user=current_user)
                             
    except Exception as e:
        print(f"❌ Error loading farms: {str(e)}")
        flash('Error loading farms', 'error')
        return redirect(url_for('index'))

@app.errorhandler(500)
def internal_error(error):
    """Simple error handler that doesn't require templates"""
    print(f"❌ 500 Error: {error}")
    return f"""
    <html>
    <head><title>Server Error</title></head>
    <body style="font-family: Arial; text-align: center; padding: 50px;">
        <h1>🚨 Server Error</h1>
        <p>Something went wrong. We're working to fix it.</p>
        <p><a href="/farms">🚜 Try Farms Again</a> | <a href="/login">🔐 Back to Login</a></p>
    </body>
    </html>
    """, 500
@app.route('/create_dome', methods=['POST'])
@login_required
def create_dome():
    try:
        data = request.get_json()
        name = data.get('name')
        grid_row = data.get('grid_row')
        grid_col = data.get('grid_col')
        farm_id = data.get('farm_id')  # Required for all domes now
        
        if not name or grid_row is None or grid_col is None or not farm_id:
            return jsonify({'success': False, 'error': 'Missing required fields (name, position, farm_id)'})
        
        # Verify farm ownership
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify({'success': False, 'error': 'Farm not found or access denied'})
        
        # Check if position is occupied within this farm
        existing_dome = Dome.query.filter_by(
            grid_row=grid_row, 
            grid_col=grid_col,
            user_id=current_user.id,
            farm_id=farm_id
        ).first()
        
        if existing_dome:
            return jsonify({'success': False, 'error': 'Position already occupied in this farm'})
        
        # Create new dome with default 5x5 internal grid
        new_dome = Dome(
            name=name,
            grid_row=grid_row,
            grid_col=grid_col,
            internal_rows=5,  # Default 5x5 internal grid
            internal_cols=5,
            user_id=current_user.id,
            farm_id=farm_id  # Always required now
        )
        
        db.session.add(new_dome)
        db.session.commit()
        
        print(f"✅ Dome created: {new_dome.name} at ({grid_row}, {grid_col}) in farm {farm_id}")
        
        return jsonify({
            'success': True, 
            'message': 'Dome created successfully',
            'dome': {
                'id': new_dome.id,
                'name': new_dome.name,
                'grid_row': new_dome.grid_row,
                'grid_col': new_dome.grid_col,
                'internal_rows': new_dome.internal_rows,
                'internal_cols': new_dome.internal_cols,
                'farm_id': new_dome.farm_id
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating dome: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/farm/<int:farm_id>/breeds')
@login_required
def get_farm_breeds(farm_id):
    """Get all breeds for a specific farm"""
    try:
        print(f"🧬 Getting breeds for farm {farm_id}")
        
        # Verify farm ownership
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            print(f"❌ Farm {farm_id} not found or access denied")
            return jsonify({'success': False, 'error': 'Farm not found or access denied'}), 404
        
        # Get breeds for this farm
        try:
            breeds = TreeBreed.query.filter_by(
                farm_id=farm_id, 
                user_id=current_user.id, 
                is_active=True
            ).all()
            print(f"✅ Found {len(breeds)} breeds for farm {farm_id}")
        except Exception as breed_query_error:
            print(f"⚠️ Error querying breeds: {breed_query_error}")
            # Fallback: create some default breeds if table doesn't exist or is empty
            breeds = []
        
        # Convert to list format
        breeds_data = []
        for breed in breeds:
            try:
                breed_dict = breed.to_dict()
                breeds_data.append(breed_dict)
                print(f"🧬 Breed: {breed.name} (ID: {breed.id})")
            except Exception as breed_error:
                print(f"⚠️ Error processing breed {breed.id}: {breed_error}")
        
        # If no breeds found, return some default ones
        if len(breeds_data) == 0:
            print("ℹ️ No breeds found, returning default breeds")
            default_breeds = [
                {'id': 'apple', 'name': 'Apple', 'description': 'Apple tree'},
                {'id': 'mango', 'name': 'Mango', 'description': 'Mango tree'},
                {'id': 'banana', 'name': 'Banana', 'description': 'Banana tree'},
                {'id': 'orange', 'name': 'Orange', 'description': 'Orange tree'}
            ]
            breeds_data = default_breeds
        
        return jsonify({
            'success': True,
            'breeds': breeds_data,
            'count': len(breeds_data)
        })
        
    except Exception as e:
        print(f"❌ Error managing farm breeds: {str(e)}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        
        # Return default breeds as fallback
        default_breeds = [
            {'id': 'apple', 'name': 'Apple', 'description': 'Apple tree'},
            {'id': 'mango', 'name': 'Mango', 'description': 'Mango tree'},
            {'id': 'banana', 'name': 'Banana', 'description': 'Banana tree'},
            {'id': 'orange', 'name': 'Orange', 'description': 'Orange tree'}
        ]
        
        return jsonify({
            'success': True,
            'breeds': default_breeds,
            'count': len(default_breeds),
            'fallback': True
        })

#
@app.route('/api/farm/<int:farm_id>/breeds', methods=['POST'])
@login_required
def add_farm_breed(farm_id):
    """Add a new breed to a farm"""
    try:
        # Verify farm ownership
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify({'success': False, 'error': 'Farm not found or access denied'}), 404
        
        data = request.get_json()
        breed_name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        
        if not breed_name:
            return jsonify({'success': False, 'error': 'Breed name is required'}), 400
        
        if len(breed_name) > 100:
            return jsonify({'success': False, 'error': 'Breed name too long (max 100 characters)'}), 400
        
        # Check if breed already exists
        existing_breed = TreeBreed.query.filter_by(
            farm_id=farm_id, 
            user_id=current_user.id, 
            name=breed_name
        ).first()
        
        if existing_breed:
            return jsonify({'success': False, 'error': 'Breed already exists'}), 400
        
        # Create new breed
        new_breed = TreeBreed(
            name=breed_name,
            description=description,
            farm_id=farm_id,
            user_id=current_user.id,
            is_active=True
        )
        
        db.session.add(new_breed)
        db.session.commit()
        
        print(f"✅ Created new breed: {breed_name} for farm {farm_id}")
        
        return jsonify({
            'success': True,
            'breed': new_breed.to_dict(),
            'message': f'Breed "{breed_name}" created successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error adding breed: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500



# ✅ STEP 5: Create default breeds for existing farms
@app.route('/create_default_breeds/<int:farm_id>')
@login_required
def create_default_breeds(farm_id):
    """Create default breeds for a farm"""
    try:
        # Verify farm ownership
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return "❌ Farm not found or access denied", 404
        
        # Check if breeds already exist
        existing_breeds = TreeBreed.query.filter_by(farm_id=farm_id, user_id=current_user.id).count()
        
        if existing_breeds > 0:
            return f"ℹ️ Farm already has {existing_breeds} breeds", 200
        
        # Create default breeds
        default_breeds = [
            ('Apple', 'Sweet and crispy fruit tree'),
            ('Orange', 'Citrus fruit tree with vitamin C'),
            ('Mango', 'Tropical fruit tree with sweet flesh'),
            ('Banana', 'Tropical fruit tree with potassium-rich fruit'),
            ('Coconut', 'Palm tree with versatile coconut fruit'),
            ('Avocado', 'Nutrient-rich fruit tree'),
            ('Cherry', 'Small stone fruit tree'),
            ('Peach', 'Soft stone fruit tree'),
            ('Lemon', 'Sour citrus fruit tree'),
            ('Lime', 'Small green citrus fruit tree'),
            ('Papaya', 'Tropical fruit tree with enzyme-rich fruit'),
            ('Guava', 'Tropical fruit tree with vitamin C')
        ]
        
        created_count = 0
        for breed_name, description in default_breeds:
            new_breed = TreeBreed(
                name=breed_name,
                description=description,
                farm_id=farm_id,
                user_id=current_user.id,
                is_active=True
            )
            db.session.add(new_breed)
            created_count += 1
        
        db.session.commit()
        
        return f"✅ Created {created_count} default breeds for farm {farm_id}", 200
        
    except Exception as e:
        db.session.rollback()
        return f"❌ Error creating default breeds: {str(e)}", 500
@app.route('/delete_tree/<int:tree_id>', methods=['DELETE', 'POST'])
@login_required
def delete_tree(tree_id):
    """Delete a tree and handle all related data properly"""
    try:
        print(f"🗑️ Delete tree request for ID: {tree_id}")
        
        # Get the tree and verify ownership
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        print(f"🗑️ Deleting tree: '{tree.name}' at ({tree.internal_row}, {tree.internal_col})")
        
        # ✅ CRITICAL: Handle all relationships and constraints properly
        try:
            relationship_stats = {
                'cutting_trees_updated': 0,
                'plant_relationships_deleted': 0,
                'drag_areas_updated': 0
            }
            
            # Step 1: Handle plant_relationship table entries FIRST
            try:
                # ✅ CRITICAL: DELETE (don't update) plant_relationship records
                if hasattr(db.engine, 'execute'):
                    # For newer SQLAlchemy versions
                    result = db.session.execute(
                        db.text("DELETE FROM plant_relationship WHERE mother_tree_id = :tree_id OR cutting_tree_id = :tree_id"),
                        {"tree_id": tree_id}
                    )
                    relationship_stats['plant_relationships_deleted'] = result.rowcount
                else:
                    # For older SQLAlchemy versions
                    result = db.engine.execute(
                        "DELETE FROM plant_relationship WHERE mother_tree_id = ? OR cutting_tree_id = ?",
                        (tree_id, tree_id)
                    )
                    relationship_stats['plant_relationships_deleted'] = result.rowcount
                
                print(f"🗑️ Deleted {relationship_stats['plant_relationships_deleted']} plant_relationship records")
                
            except Exception as rel_error:
                print(f"⚠️ Error deleting plant_relationship records: {rel_error}")
                # Continue - this might not exist
            
            # Step 2: Handle cutting trees that have this tree as mother
            if hasattr(tree, 'plant_type') and tree.plant_type == 'mother':
                cutting_trees = Tree.query.filter_by(mother_plant_id=tree_id).all()
                
                if cutting_trees:
                    print(f"🔗 Found {len(cutting_trees)} cutting trees with this mother")
                    
                    for cutting in cutting_trees:
                        cutting.mother_plant_id = None
                        cutting.plant_type = 'independent'
                        cutting.cutting_notes = (cutting.cutting_notes or '') + f" [Mother tree '{tree.name}' was deleted on {datetime.utcnow().strftime('%Y-%m-%d')}]"
                        cutting.updated_at = datetime.utcnow()
                        relationship_stats['cutting_trees_updated'] += 1
                        print(f"🔗 Updated cutting tree '{cutting.name}' to independent")
            
            # Step 3: Handle drag area relationships
            try:
                drag_area_trees = DragAreaTree.query.filter_by(tree_id=tree_id).all()
                for dat in drag_area_trees:
                    db.session.delete(dat)
                    relationship_stats['drag_areas_updated'] += 1
                    print(f"🗑️ Removed tree from drag area {dat.drag_area_id}")
            except Exception as drag_error:
                print(f"⚠️ Error removing from drag areas: {drag_error}")
                # Continue with deletion
            
            # Step 4: Update dome.info to remove tree references
            try:
                dome = tree.dome
                if dome and dome.info:
                    import json
                    areas_data = json.loads(dome.info)
                    if 'drag_areas' in areas_data:
                        for area in areas_data['drag_areas']:
                            if 'tree_ids' in area and tree_id in area['tree_ids']:
                                area['tree_ids'].remove(tree_id)
                                print(f"🗑️ Removed tree from dome.info area '{area.get('name', 'Unknown')}'")
                        dome.info = json.dumps(areas_data)
                        dome.updated_at = datetime.utcnow()
            except Exception as dome_error:
                print(f"⚠️ Error updating dome.info: {dome_error}")
                # Continue with deletion
            
            # Step 5: Delete the tree itself
            tree_name = tree.name  # Store name before deletion
            db.session.delete(tree)
            
            # Commit all changes
            db.session.commit()
            
            print(f"✅ Tree '{tree_name}' deleted successfully with all relationships handled")
            
            return jsonify({
                'success': True,
                'message': f'Tree "{tree_name}" deleted successfully',
                'tree_id': tree_id,
                'cutting_trees_updated': relationship_stats['cutting_trees_updated'],
                'plant_relationships_deleted': relationship_stats['plant_relationships_deleted'],
                'drag_areas_updated': relationship_stats['drag_areas_updated']
            })
            
        except Exception as relationship_error:
            print(f"❌ Error handling relationships during delete: {relationship_error}")
            db.session.rollback()
            
            # ✅ ENHANCED FALLBACK: Try more aggressive cleanup
            try:
                print("🔄 Attempting enhanced cleanup as fallback...")
                
                # Get fresh tree instance
                tree_to_delete = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
                if not tree_to_delete:
                    return jsonify({'success': False, 'error': 'Tree not found for cleanup'}), 404
                
                tree_name = tree_to_delete.name
                
                # Force delete all related records
                try:
                    # Delete plant_relationship records with raw SQL
                    db.session.execute(
                        db.text("DELETE FROM plant_relationship WHERE mother_tree_id = :tree_id OR cutting_tree_id = :tree_id"),
                        {"tree_id": tree_id}
                    )
                    print("🗑️ Force deleted plant_relationship records")
                except:
                    pass
                
                try:
                    # Delete drag_area_tree records
                    db.session.execute(
                        db.text("DELETE FROM drag_area_tree WHERE tree_id = :tree_id"),
                        {"tree_id": tree_id}
                    )
                    print("🗑️ Force deleted drag_area_tree records")
                except:
                    pass
                
                try:
                    # Update cutting trees
                    db.session.execute(
                        db.text("UPDATE trees SET mother_plant_id = NULL, plant_type = 'independent' WHERE mother_plant_id = :tree_id"),
                        {"tree_id": tree_id}
                    )
                    print("🗑️ Force updated cutting trees")
                except:
                    pass
                
                # Delete the tree
                db.session.delete(tree_to_delete)
                db.session.commit()
                
                print(f"✅ Tree '{tree_name}' deleted successfully (enhanced cleanup)")
                return jsonify({
                    'success': True,
                    'message': f'Tree "{tree_name}" deleted successfully',
                    'tree_id': tree_id,
                    'method': 'enhanced_cleanup',
                    'cutting_trees_updated': 0  # Unknown count with raw SQL
                })
                
            except Exception as cleanup_error:
                print(f"❌ Enhanced cleanup also failed: {cleanup_error}")
                db.session.rollback()
                
                # ✅ LAST RESORT: Simple delete with constraint disabling
                try:
                    print("🔄 Attempting simple delete with constraint handling...")
                    
                    # Disable foreign key constraints temporarily (SQLite specific)
                    db.session.execute(db.text("PRAGMA foreign_keys = OFF"))
                    
                    # Get tree again
                    tree_to_delete = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
                    if tree_to_delete:
                        tree_name = tree_to_delete.name
                        db.session.delete(tree_to_delete)
                        db.session.commit()
                        
                        # Re-enable foreign key constraints
                        db.session.execute(db.text("PRAGMA foreign_keys = ON"))
                        
                        print(f"✅ Tree '{tree_name}' deleted successfully (simple method)")
                        return jsonify({
                            'success': True,
                            'message': f'Tree "{tree_name}" deleted successfully',
                            'tree_id': tree_id,
                            'method': 'simple_delete_no_constraints',
                            'cutting_trees_updated': 0
                        })
                    else:
                        return jsonify({'success': False, 'error': 'Tree not found for simple delete'}), 404
                        
                except Exception as simple_error:
                    print(f"❌ Simple delete also failed: {simple_error}")
                    db.session.rollback()
                    
                    # Re-enable foreign key constraints
                    try:
                        db.session.execute(db.text("PRAGMA foreign_keys = ON"))
                    except:
                        pass
                    
                    return jsonify({
                        'success': False, 
                        'error': f'All delete methods failed. Last error: {str(simple_error)}'
                    }), 500
        
    except Exception as e:
        print(f"❌ Critical error in delete_tree: {str(e)}")
        db.session.rollback()
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': f'Critical error: {str(e)}'}), 500
# ✅ ADD: Enhanced POST method endpoint


        
@app.route('/paste_drag_area_with_relationships/<int:dome_id>', methods=['POST'])
@login_required
def paste_drag_area_with_relationships(dome_id):
    """Enhanced paste endpoint that preserves plant relationships with bidirectional updates"""
    try:
        data = request.get_json()
        print(f"🔗 Pasting area with relationships to dome {dome_id}")
        
        # Get dome and verify ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Extract relationship metadata
        relationship_metadata = data.get('relationship_metadata', {})
        mother_cutting_pairs = relationship_metadata.get('mother_cutting_pairs', [])
        
        print(f"🔗 Processing {len(mother_cutting_pairs)} relationship pairs")
        
        # Step 1: Create all trees first (without relationships)
        trees_data = data.get('trees_data', [])
        old_to_new_id_mapping = {}
        new_tree_ids = []
        relationship_stats = {
            'relationships_preserved': 0,
            'relationships_broken': 0,
            'mothers_created': 0,
            'cuttings_created': 0,
            'mother_cutting_links': []
        }
        
        for tree_data in trees_data:
            try:
                # ✅ CRITICAL: Preserve original mother_plant_id for cutting trees
                original_mother_id = tree_data.get('mother_plant_id')
                plant_type = tree_data.get('plant_type', 'mother')
                
                print(f"🌳 Creating tree '{tree_data.get('name')}' - Type: {plant_type}, Original Mother ID: {original_mother_id}")
                
                new_tree = Tree(
                    name=tree_data.get('name', 'Pasted Tree'),
                    breed=tree_data.get('breed', ''),
                    internal_row=tree_data.get('internal_row'),
                    internal_col=tree_data.get('internal_col'),
                    life_days=tree_data.get('life_days', 0),
                    info=tree_data.get('info', ''),
                    image_url=tree_data.get('image_url', ''),
                    dome_id=dome_id,
                    user_id=current_user.id,
                    plant_type=tree_data.get('plant_type', 'mother'),
                    cutting_notes=tree_data.get('cutting_notes', ''),
                    # ✅ PRESERVE: Keep original mother_plant_id for cutting trees
                    mother_plant_id=original_mother_id,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                
                db.session.add(new_tree)
                db.session.flush()  # Get the new ID
                
                # Map old ID to new ID
                if tree_data.get('relationship_metadata', {}).get('original_tree_id'):
                    old_id = tree_data['relationship_metadata']['original_tree_id']
                    old_to_new_id_mapping[old_id] = new_tree.id
                
                new_tree_ids.append(new_tree.id)
                
                if new_tree.plant_type == 'mother':
                    relationship_stats['mothers_created'] += 1
                elif new_tree.plant_type == 'cutting':
                    relationship_stats['cuttings_created'] += 1
                
                print(f"✅ Created tree '{new_tree.name}' (Type: {new_tree.plant_type}, Mother ID: {new_tree.mother_plant_id}) - old ID: {old_id if 'old_id' in locals() else 'N/A'} -> new ID: {new_tree.id}")
                
            except Exception as tree_error:
                print(f"❌ Error creating tree: {tree_error}")
                continue
        
        # Step 2: Update relationships using the ID mapping
        mother_cutting_counts = {}  # Track how many cuttings each mother has
        
        for pair in mother_cutting_pairs:
            if not pair.get('relationship_preserved', False):
                continue
                
            old_cutting_id = pair.get('cutting_original_id')
            old_mother_id = pair.get('mother_original_id')
            
            new_cutting_id = old_to_new_id_mapping.get(old_cutting_id)
            new_mother_id = old_to_new_id_mapping.get(old_mother_id)
            
            if new_cutting_id and new_mother_id:
                cutting_tree = db.session.get(Tree, new_cutting_id)
                mother_tree = db.session.get(Tree, new_mother_id)
                
                if cutting_tree and mother_tree:
                    # ✅ CRITICAL: Set the relationship
                    cutting_tree.mother_plant_id = new_mother_id
                    cutting_tree.plant_type = 'cutting'  # Ensure it's marked as cutting
                    cutting_tree.updated_at = datetime.utcnow()
                    
                    # ✅ ENHANCED: Ensure mother is marked as mother type
                    if mother_tree.plant_type != 'mother':
                        mother_tree.plant_type = 'mother'
                        mother_tree.updated_at = datetime.utcnow()
                    
                    # ✅ CRITICAL: Track mother-cutting relationships
                    if new_mother_id not in mother_cutting_counts:
                        mother_cutting_counts[new_mother_id] = {
                            'mother_name': mother_tree.name,
                            'cutting_ids': [],
                            'cutting_names': []
                        }
                    
                    mother_cutting_counts[new_mother_id]['cutting_ids'].append(new_cutting_id)
                    mother_cutting_counts[new_mother_id]['cutting_names'].append(cutting_tree.name)
                    
                    relationship_stats['relationships_preserved'] += 1
                    
                    # ✅ CRITICAL: Track that this mother tree was updated
                    if new_mother_id not in relationship_stats['mothers_updated']:
                        relationship_stats['mothers_updated'].append(new_mother_id)
                    relationship_stats['mother_cutting_links'].append({
                        'mother_id': new_mother_id,
                        'mother_name': mother_tree.name,
                        'cutting_id': new_cutting_id,
                        'cutting_name': cutting_tree.name,
                        'cutting_notes': pair.get('cutting_notes', '')
                    })
                    
                    print(f"🔗 Preserved relationship: '{cutting_tree.name}' -> mother '{mother_tree.name}' (ID {new_mother_id})")
                else:
                    relationship_stats['relationships_broken'] += 1
                    print(f"❌ Trees not found for relationship: cutting {new_cutting_id}, mother {new_mother_id}")
            else:
                relationship_stats['relationships_broken'] += 1
                print(f"❌ Broken relationship: cutting {old_cutting_id} -> mother {old_mother_id}")
        
        # ✅ ENHANCED: Update mother trees with cutting counts
        for mother_id, mother_info in mother_cutting_counts.items():
            mother_tree = db.session.get(Tree, mother_id)
            if mother_tree:
                cutting_count = len(mother_info['cutting_ids'])
                
                # ✅ CRITICAL: Update mother tree info to reflect cutting count
                if mother_tree.info:
                    # Remove old cutting count info if exists
                    info_lines = mother_tree.info.split('\n')
                    info_lines = [line for line in info_lines if not line.startswith('Cuttings:')]
                    mother_tree.info = '\n'.join(info_lines)
                    if mother_tree.info:
                        mother_tree.info += f"\nCuttings: {cutting_count} cutting trees"
                    else:
                        mother_tree.info = f"Cuttings: {cutting_count} cutting trees"
                else:
                    mother_tree.info = f"Cuttings: {cutting_count} cutting trees"
                
                mother_tree.updated_at = datetime.utcnow()
                
                print(f"🌳 Updated mother '{mother_tree.name}' with {cutting_count} cuttings: {', '.join(mother_info['cutting_names'])}")
        
        # Step 3: Create drag area
        new_area = DragArea(
            name=data.get('name', 'Pasted Area'),
            color=data.get('color', '#007bff'),
            min_row=data.get('minRow', data.get('min_row')),
            max_row=data.get('maxRow', data.get('max_row')),
            min_col=data.get('minCol', data.get('min_col')),
            max_col=data.get('maxCol', data.get('max_col')),
            width=data.get('width'),
            height=data.get('height'),
            dome_id=dome_id,
            visible=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.session.add(new_area)
        db.session.flush()
        
        # Step 4: Link trees to drag area
        for i, tree_id in enumerate(new_tree_ids):
            try:
                # Find the corresponding tree data to get relative position
                tree_data = trees_data[i] if i < len(trees_data) else {}
                
                # Calculate relative position within the area
                tree = db.session.get(Tree, tree_id)
                if tree:
                    relative_row = tree.internal_row - new_area.min_row
                    relative_col = tree.internal_col - new_area.min_col
                    
                    drag_area_tree = DragAreaTree(
                        drag_area_id=new_area.id,
                        tree_id=tree_id,
                        relative_row=relative_row,
                        relative_col=relative_col,
                        created_at=datetime.utcnow()
                    )
                    
                    db.session.add(drag_area_tree)
                    print(f"🔗 Linked tree {tree_id} to area {new_area.id} at relative position ({relative_row}, {relative_col})")
                    
            except Exception as link_error:
                print(f"❌ Error linking tree {tree_id} to area: {link_error}")
                continue
        
        # Step 5: Commit all changes
        db.session.commit()
        
        # ✅ ENHANCED: Add mother cutting count summary to relationship stats
        relationship_stats['mother_cutting_summary'] = {
            mother_id: {
                'mother_name': info['mother_name'],
                'cutting_count': len(info['cutting_ids']),
                'cutting_names': info['cutting_names']
            }
            for mother_id, info in mother_cutting_counts.items()
        }
        
        # Step 6: Prepare response with comprehensive data
        response_data = {
            'success': True,
            'message': f'Area "{new_area.name}" pasted successfully with relationships!',
            'drag_area_id': new_area.id,
            'trees_created': len(new_tree_ids),
            'tree_ids': new_tree_ids,
            'relationship_stats': relationship_stats,
            'area': {
                'id': new_area.id,
                'name': new_area.name,
                'color': new_area.color,
                'min_row': new_area.min_row,
                'max_row': new_area.max_row,
                'min_col': new_area.min_col,
                'max_col': new_area.max_col,
                'width': new_area.width,
                'height': new_area.height,
                'tree_count': len(new_tree_ids),
                'tree_ids': new_tree_ids
            },
            'trees_created_details': [
                {
                    'new_tree_id': new_tree_ids[i],
                    'original_tree_id': trees_data[i].get('relationship_metadata', {}).get('original_tree_id'),
                    'name': trees_data[i].get('name', 'Pasted Tree'),
                    'plant_type': trees_data[i].get('plant_type', 'mother'),
                    'position': {
                        'row': trees_data[i].get('internal_row'),
                        'col': trees_data[i].get('internal_col')
                    }
                }
                for i in range(min(len(new_tree_ids), len(trees_data)))
            ],
            'id_mapping': old_to_new_id_mapping
        }
        
        print(f"✅ Successfully pasted area with {len(new_tree_ids)} trees and {relationship_stats['relationships_preserved']} preserved relationships")
        print(f"🌳 Mother-cutting summary: {len(mother_cutting_counts)} mothers with cuttings")
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"❌ Error in paste_drag_area_with_relationships: {str(e)}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        
        # Rollback any partial changes
        try:
            db.session.rollback()
        except:
            pass
            
        return jsonify({
            'success': False, 
            'error': f'Failed to paste area with relationships: {str(e)}'
        }), 500
def find_suitable_mother_tree(cutting_tree_data, dome_id, user_id, original_mother_id=None):
    """Find a suitable mother tree for a cutting tree in the destination dome"""
    try:
        # First try to find by original ID (same dome scenario)
        if original_mother_id:
            existing_mother = Tree.query.filter_by(
                dome_id=dome_id,
                user_id=user_id,
                id=original_mother_id
            ).first()

            if existing_mother and (existing_mother.plant_type == 'mother' or not existing_mother.plant_type):
                print(f"โ… Found existing mother tree in dome by ID: {original_mother_id}")
                return existing_mother.id

        # Get all potential mother trees in the destination dome
        potential_mothers = Tree.query.filter_by(
            dome_id=dome_id,
            user_id=user_id,
            plant_type='mother'
        ).all()

        if not potential_mothers:
            print(f"โ No mother trees found in destination dome {dome_id}")
            return None

        cutting_breed = cutting_tree_data.get('breed', '').strip()
        cutting_name = cutting_tree_data.get('name', '').lower()

        # Strategy 1: Exact breed match
        if cutting_breed:
            for potential_mother in potential_mothers:
                if potential_mother.breed and potential_mother.breed.strip() == cutting_breed:
                    print(f"โ… Found mother tree by exact breed match: '{cutting_breed}' -> mother {potential_mother.id} '{potential_mother.name}'")
                    return potential_mother.id

        # Strategy 2: Name similarity (cutting name contains mother name or vice versa)
        for potential_mother in potential_mothers:
            mother_name = potential_mother.name.lower()
            # Check if names are related
            if (mother_name in cutting_name or cutting_name in mother_name or
                any(word in mother_name for word in cutting_name.split() if len(word) > 3)):
                print(f"โ… Found mother tree by name similarity: cutting '{cutting_tree_data.get('name')}' -> mother '{potential_mother.name}'")
                return potential_mother.id

        # Strategy 3: First available mother with same breed (case-insensitive)
        if cutting_breed:
            for potential_mother in potential_mothers:
                if (potential_mother.breed and 
                    potential_mother.breed.strip().lower() == cutting_breed.lower()):
                    print(f"โ… Found mother tree by case-insensitive breed match: '{cutting_breed}' -> mother '{potential_mother.name}'")
                    return potential_mother.id

        # Strategy 4: Use the first available mother tree (last resort)
        if potential_mothers:
            first_mother = potential_mothers[0]
            print(f"โ ๏ธ Using first available mother tree as fallback: '{first_mother.name}' for cutting '{cutting_tree_data.get('name')}'")
            return first_mother.id

        print(f"โ No suitable mother tree found in dome for cutting '{cutting_tree_data.get('name')}'")
        return None

    except Exception as e:
        print(f"โ Error finding suitable mother tree: {e}")
        return None

def create_plant_relationship_record(mother_tree_id, cutting_tree_id, user_id, dome_id, cutting_notes=''):
    """Create a PlantRelationship record for bidirectional relationship tracking"""
    try:
        # Check if relationship already exists
        existing_rel = PlantRelationship.query.filter_by(
            cutting_tree_id=cutting_tree_id
        ).first()
        
        if existing_rel:
            print(f"โ PlantRelationship already exists for cutting {cutting_tree_id}")
            return existing_rel
        
        # Create new relationship
        relationship = PlantRelationship(
            mother_tree_id=mother_tree_id,
            cutting_tree_id=cutting_tree_id,
            cutting_date=datetime.utcnow(),
            notes=cutting_notes or '',
            user_id=user_id,
            dome_id=dome_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.session.add(relationship)
        print(f"โ… Created PlantRelationship record: cutting {cutting_tree_id} -> mother {mother_tree_id}")
        return relationship
        
    except Exception as rel_error:
        print(f"โ ๏ธ Could not create PlantRelationship record: {rel_error}")
        return None

def update_mother_cutting_count(mother_tree):
    """Update a mother tree's info with current cutting count"""
    try:
        # Get all cuttings for this mother
        cuttings = Tree.query.filter_by(
            mother_plant_id=mother_tree.id, 
            user_id=mother_tree.user_id,
            plant_type='cutting'
        ).all()
        
        cutting_count = len(cuttings)
        cutting_names = [c.name for c in cuttings]
        
        # ✅ CRITICAL: Update mother tree info
        if mother_tree.info:
            # Remove old cutting count info if exists
            info_lines = mother_tree.info.split('\n')
            info_lines = [line for line in info_lines if not line.startswith('Cuttings:')]
            mother_tree.info = '\n'.join(info_lines).strip()
            
            if cutting_count > 0:
                if mother_tree.info:
                    mother_tree.info += f"\nCuttings: {cutting_count} cutting trees ({', '.join(cutting_names)})"
                else:
                    mother_tree.info = f"Cuttings: {cutting_count} cutting trees ({', '.join(cutting_names)})"
        else:
            if cutting_count > 0:
                mother_tree.info = f"Cuttings: {cutting_count} cutting trees ({', '.join(cutting_names)})"
        
        mother_tree.updated_at = datetime.utcnow()
        
        print(f"🌳 Updated mother '{mother_tree.name}' cutting count: {cutting_count} cuttings")
        
        return cutting_count
        
    except Exception as e:
        print(f"❌ Error updating mother cutting count: {e}")
        return 0

@app.route('/api/cleanup_orphaned_relationships', methods=['POST'])
@login_required
def cleanup_orphaned_relationships():
    """Clean up orphaned plant_relationship records"""
    try:
        print("🧹 Cleaning up orphaned plant_relationship records...")
        
        # Delete plant_relationship records where trees don't exist
        result = db.session.execute(db.text("""
            DELETE FROM plant_relationship 
            WHERE mother_tree_id NOT IN (SELECT id FROM trees) 
               OR cutting_tree_id NOT IN (SELECT id FROM trees)
        """))
        
        deleted_count = result.rowcount
        db.session.commit()
        
        print(f"✅ Cleaned up {deleted_count} orphaned plant_relationship records")
        
        return jsonify({
            'success': True,
            'message': f'Cleaned up {deleted_count} orphaned relationships',
            'deleted_count': deleted_count
        })
        
    except Exception as e:
        print(f"❌ Error cleaning up relationships: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/delete_tree', methods=['POST'])
@app.route('/api/delete_tree', methods=['POST'])
@login_required
def delete_tree_post():
    """Alternative delete tree endpoint using POST method"""
    try:
        data = request.get_json()
        tree_id = data.get('tree_id')
        
        if not tree_id:
            return jsonify({'success': False, 'error': 'tree_id is required'}), 400
        
        # Call the main delete function
        return delete_tree(tree_id)
        
    except Exception as e:
        print(f"❌ Error in delete_tree_post: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/delete_trees', methods=['POST'])
@login_required
def delete_multiple_trees():
    """Delete multiple trees at once"""
    try:
        data = request.get_json()
        tree_ids = data.get('tree_ids', [])
        
        if not tree_ids or not isinstance(tree_ids, list):
            return jsonify({'success': False, 'error': 'tree_ids array is required'}), 400
        
        deleted_count = 0
        errors = []
        
        for tree_id in tree_ids:
            try:
                # Call individual delete function
                result = delete_tree(tree_id)
                if hasattr(result, 'get_json'):
                    result_data = result.get_json()
                    if result_data.get('success'):
                        deleted_count += 1
                    else:
                        errors.append(f"Tree {tree_id}: {result_data.get('error', 'Unknown error')}")
                else:
                    deleted_count += 1
            except Exception as tree_error:
                errors.append(f"Tree {tree_id}: {str(tree_error)}")
        
        return jsonify({
            'success': deleted_count > 0,
            'deleted_count': deleted_count,
            'total_requested': len(tree_ids),
            'errors': errors,
            'message': f'Deleted {deleted_count} of {len(tree_ids)} trees'
        })
        
    except Exception as e:
        print(f"❌ Error in delete_multiple_trees: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/update_drag_area_trees/<int:dome_id>/<int:area_id>', methods=['POST'])
@login_required
def update_drag_area_trees(dome_id, area_id):
    """Update trees in a drag area when trees are moved"""
    try:
        data = request.get_json()
        new_tree_ids = data.get('tree_ids', [])
        
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Get current areas
        try:
            areas_data = json.loads(dome.info or '{"drag_areas": []}')
            areas = areas_data.get('drag_areas', [])
        except:
            return jsonify({'success': False, 'error': 'No areas found'}), 404
        
        # Find and update the area
        area_found = False
        for area in areas:
            if area.get('id') == area_id:
                # Verify all trees belong to the user and dome
                if new_tree_ids:
                    trees = Tree.query.filter(
                        Tree.id.in_(new_tree_ids),
                        Tree.user_id == current_user.id,
                        Tree.dome_id == dome_id
                    ).all()
                    
                    if len(trees) != len(new_tree_ids):
                        return jsonify({'success': False, 'error': 'Some trees not found or access denied'}), 403
                
                area['tree_ids'] = new_tree_ids
                area['updated_at'] = datetime.utcnow().isoformat()
                area_found = True
                break
        
        if not area_found:
            return jsonify({'success': False, 'error': 'Area not found'}), 404
        
        dome.info = json.dumps(areas_data)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Area updated with {len(new_tree_ids)} trees'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error updating drag area trees: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/regular_areas/<int:dome_id>')
@login_required
def get_regular_areas(dome_id):
    """Disabled regular areas endpoint - returns empty array"""
    print(f"ℹ️ Regular areas API called for dome {dome_id} - returning empty (DISABLED)")
    return jsonify({
        'success': True,
        'regular_areas': [],
        'count': 0,
        'message': 'Regular areas system disabled - using drag areas only'
    })
@app.route('/api/regular_areas/<int:dome_id>', methods=['POST'])
@login_required
def create_regular_area(dome_id):
    """Disabled regular area creation"""
    return jsonify({
        'success': False,
        'error': 'Regular areas system disabled - use drag areas instead'
    }), 400

@app.route('/api/dome/<int:dome_id>/areas', methods=['GET'])
@login_required
def get_dome_areas(dome_id):
    """Get all areas (drag and regular) for a dome"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({
                'success': False,
                'error': 'Dome not found or access denied'
            }), 404
        
        areas_data = {
            'drag_areas': [],
            'regular_areas': [],
            'total_areas': 0,
            'total_trees': 0
        }
        
        # ✅ Get Drag Areas
        try:
            drag_areas = DragArea.query.filter_by(dome_id=dome_id).all()
            for area in drag_areas:
                area_data = {
                    'id': area.id,
                    'name': area.name,
                    'type': 'dragArea',
                    'color': area.color,
                    'width': area.width,
                    'height': area.height,
                    'min_row': area.min_row,
                    'max_row': area.max_row,
                    'min_col': area.min_col,
                    'max_col': area.max_col,
                    'visible': area.visible,
                    'tree_count': 0,
                    'trees': []
                }
                
                # Get trees in this drag area
                if hasattr(area, 'drag_area_trees'):
                    for dat in area.drag_area_trees:
                        if dat.tree:
                            area_data['trees'].append({
                                'id': dat.tree.id,
                                'name': dat.tree.name,
                                'relative_row': dat.relative_row,
                                'relative_col': dat.relative_col
                            })
                    area_data['tree_count'] = len(area_data['trees'])
                
                areas_data['drag_areas'].append(area_data)
                
        except Exception as drag_error:
            print(f"⚠️ Error loading drag areas: {str(drag_error)}")
            # DragArea model might not exist, continue with empty list
        
        # ✅ Get Regular Areas
        try:
            regular_areas = RegularArea.query.filter_by(dome_id=dome_id).all()
            for area in regular_areas:
                area_data = {
                    'id': area.id,
                    'name': area.name,
                    'type': 'regularArea',
                    'color': area.color,
                    'width': area.max_col - area.min_col + 1,
                    'height': area.max_row - area.min_row + 1,
                    'min_row': area.min_row,
                    'max_row': area.max_row,
                    'min_col': area.min_col,
                    'max_col': area.max_col,
                    'visible': area.visible,
                    'cell_count': len(area.cells) if area.cells else 0,
                    'tree_count': len(area.trees) if area.trees else 0,
                    'cells': [],
                    'trees': []
                }
                
                # Get cells
                if area.cells:
                    for cell in area.cells:
                        area_data['cells'].append({
                            'row': cell.row,
                            'col': cell.col
                        })
                
                # Get trees
                if area.trees:
                    for tree in area.trees:
                        area_data['trees'].append({
                            'id': tree.id,
                            'name': tree.name,
                            'internal_row': tree.internal_row,
                            'internal_col': tree.internal_col
                        })
                
                areas_data['regular_areas'].append(area_data)
                
        except Exception as regular_error:
            print(f"⚠️ Error loading regular areas: {str(regular_error)}")
            # Continue with empty list
        
        # Calculate totals
        areas_data['total_areas'] = len(areas_data['drag_areas']) + len(areas_data['regular_areas'])
        areas_data['total_trees'] = sum(area.get('tree_count', 0) for area in areas_data['drag_areas']) + \
                                   sum(area.get('tree_count', 0) for area in areas_data['regular_areas'])
        
        print(f"✅ Loaded {len(areas_data['drag_areas'])} drag areas and {len(areas_data['regular_areas'])} regular areas for dome {dome_id}")
        
        return jsonify({
            'success': True,
            'areas': areas_data
        })
        
    except Exception as e:
        print(f"❌ Error loading areas for dome {dome_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to load areas: {str(e)}'
        }), 500
@app.route('/api/delete_regular_area/<int:dome_id>/<int:area_id>', methods=['DELETE'])
@login_required
def delete_regular_area(dome_id, area_id):
    """Delete a regular area"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404
        
        regular_area = RegularArea.query.filter_by(id=area_id, dome_id=dome_id).first()
        
        if not regular_area:
            return jsonify({
                'success': False,
                'error': 'Regular area not found'
            }), 404
        
        area_name = regular_area.name
        db.session.delete(regular_area)
        db.session.commit()
        
        print(f"✅ Regular area '{area_name}' deleted for dome {dome_id}")
        
        return jsonify({
            'success': True,
            'message': f'Regular area "{area_name}" deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error deleting regular area: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
@app.route('/api/update_regular_area/<int:dome_id>/<int:area_id>', methods=['POST'])
@login_required
def update_regular_area(dome_id, area_id):
    """Update a regular area"""
    try:
        data = request.get_json()
        
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404
        
        regular_area = RegularArea.query.filter_by(id=area_id, dome_id=dome_id).first()
        
        if not regular_area:
            return jsonify({
                'success': False,
                'error': 'Regular area not found'
            }), 404
        
        # Update fields
        if 'name' in data:
            # Check if new name already exists (excluding current area)
            existing_area = RegularArea.query.filter_by(
                dome_id=dome_id,
                name=data['name']
            ).filter(RegularArea.id != area_id).first()
            
            if existing_area:
                return jsonify({
                    'success': False,
                    'error': 'Area name already exists for this dome'
                }), 400
            
            regular_area.name = data['name']
        
        if 'color' in data:
            regular_area.color = data['color']
        
        if 'visible' in data:
            regular_area.visible = data['visible']
        
        db.session.commit()
        
        print(f"✅ Regular area '{regular_area.name}' updated for dome {dome_id}")
        
        return jsonify({
            'success': True,
            'message': f'Regular area updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error updating regular area: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/copy_regular_area/<int:dome_id>/<int:area_id>', methods=['GET'])
@login_required
def copy_regular_area(dome_id, area_id):
    """Copy a regular area to clipboard with enhanced error handling"""
    try:
        # ✅ ENHANCED: Input validation
        if dome_id <= 0 or area_id <= 0:
            return jsonify({
                'success': False,
                'error': 'Invalid dome_id or area_id'
            }), 400
        
        # ✅ ENHANCED: Verify dome ownership with better error messages
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            # Check if dome exists but belongs to different user
            dome_exists = Dome.query.filter_by(id=dome_id).first()
            if dome_exists:
                return jsonify({
                    'success': False,
                    'error': f'Access denied: Dome {dome_id} belongs to another user'
                }), 403
            else:
                return jsonify({
                    'success': False,
                    'error': f'Dome {dome_id} not found'
                }), 404
        
        # ✅ ENHANCED: Get regular area with better error handling
        try:
            regular_area = RegularArea.query.filter_by(id=area_id, dome_id=dome_id).first()
        except Exception as db_error:
            print(f"❌ Database error querying RegularArea: {str(db_error)}")
            return jsonify({
                'success': False,
                'error': 'Database error occurred while fetching regular area'
            }), 500
        
        if not regular_area:
            # ✅ ENHANCED: Check if area exists in different dome
            area_exists = RegularArea.query.filter_by(id=area_id).first()
            if area_exists:
                return jsonify({
                    'success': False,
                    'error': f'Regular area {area_id} exists but not in dome {dome_id}'
                }), 404
            else:
                return jsonify({
                    'success': False,
                    'error': f'Regular area {area_id} not found'
                }), 404
        
        # ✅ ENHANCED: Validate area belongs to user's dome
        if regular_area.dome_id != dome_id:
            return jsonify({
                'success': False,
                'error': 'Regular area does not belong to the specified dome'
            }), 400
        
        # ✅ ENHANCED: Get trees with better error handling and validation
        area_trees = []
        processed_cells = 0
        
        try:
            # Check if cells relationship exists
            if hasattr(regular_area, 'cells') and regular_area.cells:
                for cell in regular_area.cells:
                    # ✅ ENHANCED: Validate cell data
                    if not cell or not hasattr(cell, 'row') or not hasattr(cell, 'col'):
                        print(f"⚠️ Invalid cell data found in area {area_id}")
                        continue
                    
                    if cell.row is None or cell.col is None:
                        print(f"⚠️ Cell with null coordinates found in area {area_id}")
                        continue
                    
                    processed_cells += 1
                    
                    # ✅ ENHANCED: Query tree with error handling
                    try:
                        tree = Tree.query.filter_by(
                            dome_id=dome_id,
                            internal_row=cell.row,
                            internal_col=cell.col
                        ).first()
                    except Exception as tree_query_error:
                        print(f"❌ Error querying tree at ({cell.row}, {cell.col}): {str(tree_query_error)}")
                        continue
                    
                    if tree:
                        # ✅ ENHANCED: Validate tree data and include tree ID
                        tree_data = {
                            'id': tree.id,  # ✅ ADDED: Include tree ID for identification
                            'name': tree.name or f'Tree {tree.id}',
                            'life_days': tree.life_days if tree.life_days is not None else 0,
                            'info': tree.info or '',
                            'image_url': tree.image_url or '',
                            'relativeRow': cell.row - regular_area.min_row,
                            'relativeCol': cell.col - regular_area.min_col,
                            'originalRow': cell.row,
                            'originalCol': cell.col
                        }
                        area_trees.append(tree_data)
            else:
                print(f"⚠️ No cells found for regular area {area_id}")
                
        except Exception as tree_error:
            print(f"❌ Error processing trees for regular area {area_id}: {str(tree_error)}")
            # Continue with trees found so far rather than failing completely
        
        # ✅ ENHANCED: Get cell positions with error handling
        try:
            cell_positions = regular_area.get_cell_positions() if hasattr(regular_area, 'get_cell_positions') else []
        except Exception as cell_error:
            print(f"❌ Error getting cell positions: {str(cell_error)}")
            # Fallback: create cell positions manually
            cell_positions = []
            if hasattr(regular_area, 'cells') and regular_area.cells:
                for cell in regular_area.cells:
                    if hasattr(cell, 'row') and hasattr(cell, 'col'):
                        cell_positions.append({'row': cell.row, 'col': cell.col})
        
        # ✅ ENHANCED: Create clipboard data with validation
        try:
            clipboard_data = {
                'id': regular_area.id,  # ✅ ADDED: Include area ID
                'type': 'regularArea',
                'name': regular_area.name or f'Regular Area {regular_area.id}',
                'color': regular_area.color or '#28a745',
                'width': regular_area.width if hasattr(regular_area, 'width') and regular_area.width is not None else (regular_area.max_col - regular_area.min_col + 1),
                'height': regular_area.height if hasattr(regular_area, 'height') and regular_area.height is not None else (regular_area.max_row - regular_area.min_row + 1),
                'min_row': regular_area.min_row if regular_area.min_row is not None else 0,
                'max_row': regular_area.max_row if regular_area.max_row is not None else 0,
                'min_col': regular_area.min_col if regular_area.min_col is not None else 0,
                'max_col': regular_area.max_col if regular_area.max_col is not None else 0,
                'cells': cell_positions,
                'trees': area_trees,
                'tree_count': len(area_trees),
                'cell_count': len(cell_positions),
                'source_dome': dome_id,
                'source_dome_name': dome.name or f'Dome {dome_id}',
                'copied_at': datetime.utcnow().isoformat(),
                'visible': regular_area.visible if hasattr(regular_area, 'visible') else True
            }
        except Exception as data_error:
            print(f"❌ Error creating clipboard data: {str(data_error)}")
            return jsonify({
                'success': False,
                'error': 'Error preparing area data for copying'
            }), 500
        
        # ✅ ENHANCED: Validate clipboard data integrity
        if clipboard_data['width'] <= 0 or clipboard_data['height'] <= 0:
            print(f"⚠️ Invalid area dimensions: {clipboard_data['width']}x{clipboard_data['height']}")
            clipboard_data['width'] = max(1, clipboard_data['width'])
            clipboard_data['height'] = max(1, clipboard_data['height'])
        
        # ✅ ENHANCED: Detailed logging
        print(f"✅ Regular area '{clipboard_data['name']}' (ID: {regular_area.id}) copied successfully")
        print(f"   📊 Area size: {clipboard_data['width']}x{clipboard_data['height']}")
        print(f"   📍 Position: ({clipboard_data['min_row']},{clipboard_data['min_col']}) to ({clipboard_data['max_row']},{clipboard_data['max_col']})")
        print(f"   🔲 Cells processed: {processed_cells}")
        print(f"   🌳 Trees included: {len(area_trees)}")
        
        return jsonify({
            'success': True,
            'area': clipboard_data,
            'message': f"Regular area '{clipboard_data['name']}' copied with {len(area_trees)} trees from {processed_cells} cells"
        })
        
    except AttributeError as attr_error:
        print(f"❌ Attribute error in copy_regular_area: {str(attr_error)}")
        return jsonify({
            'success': False,
            'error': 'Missing required model attributes. Please check your database schema.'
        }), 500
        
    except Exception as e:
        print(f"❌ Unexpected error copying regular area {area_id} from dome {dome_id}: {str(e)}")
        print(f"   Error type: {type(e).__name__}")
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
        
        return jsonify({
            'success': False,
            'error': f'Failed to copy regular area: {str(e)}'
        }), 500
@app.route('/get_area_trees/<int:dome_id>/<int:area_id>')
@login_required
def get_area_trees(dome_id, area_id):
    """Get all trees in a specific drag area"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Get areas
        try:
            areas_data = json.loads(dome.info or '{"drag_areas": []}')
            areas = areas_data.get('drag_areas', [])
        except:
            return jsonify({'success': False, 'error': 'No areas found'}), 404
        
        # Find the area
        target_area = None
        for area in areas:
            if area.get('id') == area_id:
                target_area = area
                break
        
        if not target_area:
            return jsonify({'success': False, 'error': 'Area not found'}), 404
        
        # Get tree details
        tree_ids = target_area.get('tree_ids', [])
        trees_data = []
        
        if tree_ids:
            trees = Tree.query.filter(
                Tree.id.in_(tree_ids),
                Tree.user_id == current_user.id,
                Tree.dome_id == dome_id
            ).all()
            
            for tree in trees:
                trees_data.append({
                    'id': tree.id,
                    'name': tree.name,
                    'internal_row': tree.internal_row,
                    'internal_col': tree.internal_col,
                    'life_days': tree.life_days or 0,
                    'image_url': tree.image_url
                })
        
        return jsonify({
            'success': True,
            'area': target_area,
            'trees': trees_data
        })
        
    except Exception as e:
        print(f"❌ Error getting area trees: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/validate_drag_area_position/<int:dome_id>', methods=['POST'])
@login_required
def validate_drag_area_position(dome_id):
    """Validate drag area position with proper field mapping"""
    try:
        data = request.get_json()
        
        # ✅ FIXED: Handle both camelCase and snake_case field names
        start_row = data.get('start_row') or data.get('startRow')
        start_col = data.get('start_col') or data.get('startCol')
        width = data.get('width')
        height = data.get('height')
        exclude_area_id = data.get('exclude_area_id') or data.get('excludeAreaId')
        
        if start_row is None or start_col is None or width is None or height is None:
            return jsonify({
                'success': False, 
                'error': 'Missing required fields: start_row, start_col, width, height'
            }), 400
        
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Check bounds
        if (start_row + height > dome.internal_rows or 
            start_col + width > dome.internal_cols or
            start_row < 0 or start_col < 0):
            return jsonify({
                'success': False, 
                'error': f'Area extends outside dome boundaries. Dome size: {dome.internal_rows}×{dome.internal_cols}'
            }), 400
        
        # Check for overlaps with existing drag areas
        try:
            existing_areas = DragArea.query.filter_by(dome_id=dome_id).all()
            
            for area in existing_areas:
                # Skip the area being edited
                if exclude_area_id and area.id == exclude_area_id:
                    continue
                
                # Check for overlap
                if not (start_row + height <= area.min_row or 
                       start_row > area.max_row or
                       start_col + width <= area.min_col or 
                       start_col > area.max_col):
                    return jsonify({
                        'success': False,
                        'error': f'Area overlaps with existing drag area "{area.name}"'
                    }), 400
                    
        except Exception as area_error:
            print(f"⚠️ Error checking drag area overlaps: {area_error}")
            # Continue without overlap check if DragArea model has issues
        
        return jsonify({
            'success': True, 
            'message': 'Position is valid',
            'bounds': {
                'start_row': start_row,
                'start_col': start_col,
                'end_row': start_row + height - 1,
                'end_col': start_col + width - 1
            }
        })
        
    except Exception as e:
        print(f"❌ Error validating drag area position: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/get_drag_areas/<int:dome_id>')
@login_required
def get_drag_areas_safe(dome_id):
    """Get drag areas with safe error handling"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404
        
        try:
            drag_areas = DragArea.query.filter_by(dome_id=dome_id).all()
        except Exception as db_error:
            print(f"⚠️ Error querying DragArea table: {db_error}")
            # Return empty list if table doesn't exist or has issues
            return jsonify({
                'success': True,
                'drag_areas': [],
                'message': 'DragArea table not available'
            })
        
        areas_data = []
        for area in drag_areas:
            try:
                # Get trees in this drag area safely
                area_trees = []
                if hasattr(area, 'drag_area_trees'):
                    for dat in area.drag_area_trees:
                        tree = dat.tree if hasattr(dat, 'tree') else None
                        if tree:
                            area_trees.append({
                                'id': tree.id,
                                'name': tree.name,
                                'internal_row': tree.internal_row,
                                'internal_col': tree.internal_col,
                                'relative_row': getattr(dat, 'relative_row', 0),
                                'relative_col': getattr(dat, 'relative_col', 0),
                                'life_days': getattr(tree, 'life_days', 0),
                                'info': getattr(tree, 'info', ''),
                                'image_url': getattr(tree, 'image_url', '')
                            })
                
                areas_data.append({
                    'id': area.id,
                    'name': area.name,
                    'color': getattr(area, 'color', '#007bff'),
                    'minRow': area.min_row,
                    'maxRow': area.max_row,
                    'minCol': area.min_col,
                    'maxCol': area.max_col,
                    'width': getattr(area, 'width', area.max_col - area.min_col + 1),
                    'height': getattr(area, 'height', area.max_row - area.min_row + 1),
                    'visible': getattr(area, 'visible', True),
                    'trees': [t['id'] for t in area_trees],
                    'tree_data': area_trees,
                    'tree_count': len(area_trees),
                    'createdAt': area.created_at.isoformat() if hasattr(area, 'created_at') and area.created_at else None
                })
                
            except Exception as area_error:
                print(f"⚠️ Error processing drag area {area.id}: {area_error}")
                continue
        
        return jsonify({
            'success': True,
            'drag_areas': areas_data
        })
        
    except Exception as e:
        print(f"❌ Error getting drag areas: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
@app.route('/resize_drag_area/<int:dome_id>/<int:area_id>', methods=['POST'])
@login_required
def resize_drag_area(dome_id, area_id):
    """Resize an existing drag area"""
    try:
        data = request.get_json()
        new_min_row = data.get('min_row')
        new_max_row = data.get('max_row')
        new_min_col = data.get('min_col')
        new_max_col = data.get('max_col')
        
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Get areas
        try:
            areas_data = json.loads(dome.info or '{"drag_areas": []}')
            areas = areas_data.get('drag_areas', [])
        except:
            return jsonify({'success': False, 'error': 'No areas found'}), 404
        
        # Find and update the area
        area_found = False
        for area in areas:
            if area.get('id') == area_id:
                # Validate new bounds
                if (new_max_row >= dome.internal_rows or new_max_col >= dome.internal_cols or
                    new_min_row < 0 or new_min_col < 0 or
                    new_min_row > new_max_row or new_min_col > new_max_col):
                    return jsonify({'success': False, 'error': 'Invalid area bounds'}), 400
                
                # Update area bounds
                area['min_row'] = new_min_row
                area['max_row'] = new_max_row
                area['min_col'] = new_min_col
                area['max_col'] = new_max_col
                area['width'] = new_max_col - new_min_col + 1
                area['height'] = new_max_row - new_min_row + 1
                area['updated_at'] = datetime.utcnow().isoformat()
                
                # Remove trees that are now outside the area
                current_tree_ids = area.get('tree_ids', [])
                valid_tree_ids = []
                
                if current_tree_ids:
                    trees = Tree.query.filter(
                        Tree.id.in_(current_tree_ids),
                        Tree.user_id == current_user.id,
                        Tree.dome_id == dome_id
                    ).all()
                    
                    for tree in trees:
                        if (new_min_row <= tree.internal_row <= new_max_row and
                            new_min_col <= tree.internal_col <= new_max_col):
                            valid_tree_ids.append(tree.id)
                
                area['tree_ids'] = valid_tree_ids
                area_found = True
                break
        
        if not area_found:
            return jsonify({'success': False, 'error': 'Area not found'}), 404
        
        dome.info = json.dumps(areas_data)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Area resized successfully',
            'area': area
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error resizing drag area: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/auto_assign_trees_to_area/<int:dome_id>/<int:area_id>', methods=['POST'])
@login_required
def auto_assign_trees_to_area(dome_id, area_id):
    """Automatically assign all trees within an area's bounds"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Get areas
        try:
            areas_data = json.loads(dome.info or '{"drag_areas": []}')
            areas = areas_data.get('drag_areas', [])
        except:
            return jsonify({'success': False, 'error': 'No areas found'}), 404
        
        # Find the area
        target_area = None
        for area in areas:
            if area.get('id') == area_id:
                target_area = area
                break
        
        if not target_area:
            return jsonify({'success': False, 'error': 'Area not found'}), 404
        
        # Find all trees within the area bounds
        trees_in_area = Tree.query.filter(
            Tree.dome_id == dome_id,
            Tree.user_id == current_user.id,
            Tree.internal_row >= target_area['min_row'],
            Tree.internal_row <= target_area['max_row'],
            Tree.internal_col >= target_area['min_col'],
            Tree.internal_col <= target_area['max_col']
        ).all()
        
        # Update area with tree IDs
        target_area['tree_ids'] = [tree.id for tree in trees_in_area]
        target_area['updated_at'] = datetime.utcnow().isoformat()
        
        dome.info = json.dumps(areas_data)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Auto-assigned {len(trees_in_area)} trees to area',
            'tree_count': len(trees_in_area)
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error auto-assigning trees: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/get_drag_areas/<int:dome_id>')
@login_required
def get_drag_areas(dome_id):
    """Get all drag areas for a dome with enhanced data"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404
        
        # Get drag areas
        drag_areas_db = DragArea.query.filter_by(dome_id=dome_id).all()
        print(f"✅ Found {len(drag_areas_db)} drag areas in database")
        
        # Convert to API format
        drag_areas = []
        for area in drag_areas_db:
            try:
                # Get trees in this area
                tree_ids = []
                trees_data = []
                
                for dat in area.drag_area_trees:
                    if dat.tree:
                        tree_ids.append(dat.tree.id)
                        trees_data.append({
                            'id': dat.tree.id,
                            'name': dat.tree.name,
                            'breed': dat.tree.breed or '',
                            'relative_row': dat.relative_row,
                            'relative_col': dat.relative_col,
                            'absolute_row': dat.tree.internal_row,
                            'absolute_col': dat.tree.internal_col,
                            'plant_type': getattr(dat.tree, 'plant_type', 'mother'),
                            'mother_plant_id': getattr(dat.tree, 'mother_plant_id', None)
                        })
                
                area_data = {
                    'id': area.id,
                    'name': area.name,
                    'color': area.color,
                    'min_row': area.min_row,
                    'max_row': area.max_row,
                    'min_col': area.min_col,
                    'max_col': area.max_col,
                    'width': area.width,
                    'height': area.height,
                    'visible': area.visible,
                    'tree_ids': tree_ids,
                    'tree_count': len(tree_ids),
                    'trees': trees_data,
                    'created_at': area.created_at.isoformat() if area.created_at else None,
                    'updated_at': area.updated_at.isoformat() if area.updated_at else None
                }
                
                drag_areas.append(area_data)
                print(f"🔲 API Drag Area {area.id} '{area.name}' - Visible: {area_data['visible']} - Trees: {len(tree_ids)}")
                
            except Exception as area_error:
                print(f"⚠️ Error processing area {area.id}: {area_error}")
                continue
        
        return jsonify({
            'success': True,
            'drag_areas': drag_areas,
            'count': len(drag_areas),
            'visible_count': len([area for area in drag_areas if area.get('visible', True)]),
            'system_mode': 'DRAG_AREAS_ONLY'
        })
        
    except Exception as e:
        print(f"❌ Error in get_drag_areas: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/cleanup/remove_regular_areas/<int:dome_id>')
@login_required
def cleanup_regular_areas(dome_id):
    """Remove all regular areas for a dome to eliminate conflicts"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return "❌ Dome not found or access denied", 404
        
        # Get regular areas
        regular_areas = RegularArea.query.filter_by(dome_id=dome_id).all()
        regular_cells = RegularAreaCell.query.join(RegularArea).filter(RegularArea.dome_id == dome_id).all()
        
        # Delete regular area cells first
        for cell in regular_cells:
            db.session.delete(cell)
        
        # Delete regular areas
        for area in regular_areas:
            db.session.delete(area)
        
        db.session.commit()
        
        return f"✅ Cleaned up {len(regular_areas)} regular areas and {len(regular_cells)} cells for dome {dome_id}", 200
        
    except Exception as e:
        db.session.rollback()
        return f"❌ Error cleaning up regular areas: {str(e)}", 500
@app.route('/api/save_drag_area/<int:dome_id>', methods=['POST'])
@login_required
def save_drag_area(dome_id):
    """Save a new drag area with plant relationships and trees"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404
        
        data = request.get_json()
        print(f"🔍 Incoming data for save_drag_area: {data}")
        
        # Extract data
        name = data.get('name', '').strip()
        color = data.get('color', '#007bff')
        min_row = data.get('min_row', data.get('minRow', 0))
        max_row = data.get('max_row', data.get('maxRow', 0))
        min_col = data.get('min_col', data.get('minCol', 0))
        max_col = data.get('max_col', data.get('maxCol', 0))
        tree_ids = data.get('tree_ids', [])
        cells_data = data.get('cells_data', [])
        
        # Validation
        if not name:
            return jsonify({'success': False, 'error': 'Area name is required'}), 400
        
        # Check for duplicate names
        existing_area = DragArea.query.filter_by(dome_id=dome_id, name=name).first()
        if existing_area:
            return jsonify({'success': False, 'error': 'Area name already exists'}), 400
        
        # Calculate dimensions
        width = max_col - min_col + 1
        height = max_row - min_row + 1
        
        # Create the drag area
        drag_area = DragArea(
            name=name,
            color=color,
            min_row=min_row,
            max_row=max_row,
            min_col=min_col,
            max_col=max_col,
            width=width,
            height=height,
            dome_id=dome_id,
            visible=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Add enhanced fields if available
        if hasattr(DragArea, 'cells_data'):
            drag_area.cells_data = json.dumps(cells_data) if cells_data else None
        if hasattr(DragArea, 'supports_empty_cells'):
            drag_area.supports_empty_cells = True
        
        db.session.add(drag_area)
        db.session.flush()  # Get the ID
        
        print(f"✅ DragArea created with ID: {drag_area.id}")
        
        # Associate trees with the drag area
        created_tree_ids = []
        for tree_id in tree_ids:
            # Verify tree exists and belongs to user
            tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id, dome_id=dome_id).first()
            if tree:
                # Calculate relative position
                relative_row = tree.internal_row - min_row
                relative_col = tree.internal_col - min_col
                
                # Create drag area tree association
                drag_area_tree = DragAreaTree(
                    drag_area_id=drag_area.id,
                    tree_id=tree_id,
                    relative_row=relative_row,
                    relative_col=relative_col,
                    created_at=datetime.utcnow()
                )
                
                db.session.add(drag_area_tree)
                created_tree_ids.append(tree_id)
        
        db.session.commit()
        
        print(f"✅ Drag area '{name}' saved with {len(created_tree_ids)} trees")
        
        return jsonify({
            'success': True,
            'drag_area_id': drag_area.id,
            'message': f'Drag area "{name}" saved successfully',
            'area_details': {
                'id': drag_area.id,
                'name': name,
                'color': color,
                'bounds': f"({min_row},{min_col}) to ({max_row},{max_col})",
                'size': f"{width}×{height}",
                'tree_count': len(created_tree_ids),
                'tree_ids': created_tree_ids
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in save_drag_area: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'Failed to save drag area: {str(e)}'
        }), 500
@app.route('/api/update_drag_area/<int:dome_id>/<int:area_id>', methods=['POST'])
@login_required
def update_drag_area(dome_id, area_id):
    try:
        data = request.get_json()
        
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404
        
        drag_area = DragArea.query.filter_by(id=area_id, dome_id=dome_id).first()
        
        if not drag_area:
            return jsonify({
                'success': False,
                'error': 'Drag area not found'
            }), 404
        
        # Update fields
        if 'name' in data:
            drag_area.name = data['name']
        if 'visible' in data:
            drag_area.visible = data['visible']
        if 'color' in data:
            drag_area.color = data['color']
        
        db.session.commit()
        
        print(f"✅ Drag area '{drag_area.name}' updated for dome {dome_id}")
        
        return jsonify({
            'success': True,
            'message': f'Drag area updated successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error updating drag area: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/api/delete_drag_area/<int:dome_id>/<int:area_id>', methods=['DELETE'])
@login_required
def delete_drag_area(dome_id, area_id):
    """Delete a drag area"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404
        
        # Get the drag area
        drag_area = DragArea.query.filter_by(id=area_id, dome_id=dome_id).first()
        if not drag_area:
            return jsonify({'success': False, 'error': 'Drag area not found'}), 404
        
        area_name = drag_area.name
        tree_count = len(drag_area.drag_area_trees)
        
        # Delete the drag area (cascade will handle DragAreaTree records)
        db.session.delete(drag_area)
        db.session.commit()
        
        print(f"✅ Deleted drag area '{area_name}' with {tree_count} tree associations")
        
        return jsonify({
            'success': True,
            'message': f'Drag area "{area_name}" deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error deleting drag area: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/copy_drag_area/<int:dome_id>/<int:area_id>', methods=['GET'])
@login_required
def copy_drag_area(dome_id, area_id):
    """Copy a drag area to clipboard with enhanced cross-dome support"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404
        
        # Get the drag area
        drag_area = DragArea.query.filter_by(id=area_id, dome_id=dome_id).first()
        if not drag_area:
            return jsonify({'success': False, 'error': f'Drag area {area_id} not found'}), 404
        
        print(f"✅ Copying drag area {area_id} from dome {dome_id}")
        
        # Get trees in this area with full data
        area_trees = []
        for dat in drag_area.drag_area_trees:
            if dat.tree:
                tree = dat.tree
                tree_data = {
                    'id': tree.id,
                    'name': tree.name,
                    'breed': tree.breed or '',
                    'internal_row': tree.internal_row,
                    'internal_col': tree.internal_col,
                    'relative_row': dat.relative_row,
                    'relative_col': dat.relative_col,
                    'image_url': tree.image_url,
                    'info': tree.info or '',
                    'life_days': tree.life_days or 0,
                    'plant_type': getattr(tree, 'plant_type', 'mother'),
                    'mother_plant_id': getattr(tree, 'mother_plant_id', None),
                    'cutting_notes': getattr(tree, 'cutting_notes', ''),
                    'created_at': tree.created_at.isoformat() if tree.created_at else None
                }
                area_trees.append(tree_data)
        
        # Create comprehensive clipboard data
        clipboard_data = {
            'id': drag_area.id,
            'name': drag_area.name,
            'type': 'dragArea',
            'color': drag_area.color,
            'width': drag_area.width,
            'height': drag_area.height,
            'min_row': drag_area.min_row,
            'max_row': drag_area.max_row,
            'min_col': drag_area.min_col,
            'max_col': drag_area.max_col,
            'trees': area_trees,
            'tree_count': len(area_trees),
            'tree_ids': [tree['id'] for tree in area_trees],
            'visible': drag_area.visible,
            'copied_at': datetime.utcnow().isoformat(),
            'source_dome_id': dome_id,
            'source_dome_name': dome.name,
            'clipboard_version': '2.4',
            'clipboard_source': 'backend_api',
            'summary': {
                'total_trees': len(area_trees),
                'trees_in_original_area': len(area_trees),
                'related_trees_outside_area': 0,
                'breeds': list(set([tree['breed'] for tree in area_trees if tree['breed']])),
                'breed_count': len(set([tree['breed'] for tree in area_trees if tree['breed']])),
                'has_images': len([tree for tree in area_trees if tree['image_url']]),
                'plant_relationships': {
                    'mother_trees': len([tree for tree in area_trees if tree['plant_type'] == 'mother']),
                    'cutting_trees': len([tree for tree in area_trees if tree['plant_type'] == 'cutting']),
                    'complete_relationships': 0,  # Calculate if needed
                    'broken_relationships': 0
                }
            }
        }
        
        print(f"✅ Drag area '{clipboard_data['name']}' copied successfully")
        print(f"   📊 Area size: {clipboard_data['width']}x{clipboard_data['height']}")
        print(f"   🌳 Trees: {len(area_trees)}")
        
        return jsonify({
            'success': True,
            'clipboard_data': clipboard_data,
            'message': f'Drag area "{drag_area.name}" copied to clipboard'
        })
        
    except Exception as e:
        print(f"❌ Error in copy_drag_area: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/validate_area_name/<int:dome_id>', methods=['POST'])
@login_required
def validate_area_name(dome_id):
    """Validate if an area name is available"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        area_type = data.get('type', 'drag')  # 'drag' or 'regular'
        exclude_id = data.get('exclude_id')  # For editing existing areas
        
        if not name:
            return jsonify({'success': False, 'error': 'Name is required'}), 400
        
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Get existing areas
        try:
            # Check if dome has info field and it's not None
            if hasattr(dome, 'info') and dome.info:
                areas_data = json.loads(dome.info)
                drag_areas = areas_data.get('drag_areas', [])
                regular_areas = areas_data.get('areas', [])
            else:
                # Initialize empty info if it doesn't exist
                dome.info = json.dumps({"drag_areas": [], "areas": []})
                db.session.commit()
                drag_areas = []
                regular_areas = []
                
            print(f"✅ Found {len(drag_areas)} drag areas and {len(regular_areas)} regular areas for dome {dome_id}")
            
        except Exception as area_error:
            print(f"⚠️ Error loading areas: {area_error}")
            # Initialize empty info on error
            try:
                dome.info = json.dumps({"drag_areas": [], "areas": []})
                db.session.commit()
            except:
                pass
            drag_areas = []
            regular_areas = []
        
        # Check for name conflicts
        all_areas = drag_areas + regular_areas
        for area in all_areas:
            if area.get('name') == name and area.get('id') != exclude_id:
                return jsonify({
                    'success': False,
                    'available': False,
                    'error': f'Name "{name}" is already used'
                })
        
        return jsonify({
            'success': True,
            'available': True,
            'message': f'Name "{name}" is available'
        })
        
    except Exception as e:
        print(f"❌ Error validating area name: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/cleanup_areas/<int:dome_id>', methods=['POST'])
@login_required
def cleanup_areas(dome_id):
    """Clean up areas by removing invalid tree references"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Get existing areas
        try:
            # Check if dome has info field and it's not None
            if hasattr(dome, 'info') and dome.info:
                areas_data = json.loads(dome.info)
                drag_areas = areas_data.get('drag_areas', [])
                regular_areas = areas_data.get('areas', [])
            else:
                # Initialize empty info if it doesn't exist
                dome.info = json.dumps({"drag_areas": [], "areas": []})
                db.session.commit()
                drag_areas = []
                regular_areas = []
            
            # If no areas exist, return early
            if len(drag_areas) == 0 and len(regular_areas) == 0:
                return jsonify({'success': False, 'error': 'No areas to clean'}), 400
                
        except Exception as area_error:
            print(f"⚠️ Error loading areas for cleanup: {area_error}")
            return jsonify({'success': False, 'error': 'Failed to load areas for cleanup'}), 400
        
        # Get all valid tree IDs for this dome
        valid_tree_ids = set(
            tree.id for tree in Tree.query.filter_by(
                dome_id=dome_id, 
                user_id=current_user.id
            ).all()
        )
        
        cleaned_count = 0
        
        # Clean drag areas
        for area in drag_areas:
            if 'tree_ids' in area:
                original_count = len(area['tree_ids'])
                area['tree_ids'] = [tid for tid in area['tree_ids'] if tid in valid_tree_ids]
                if len(area['tree_ids']) != original_count:
                    cleaned_count += 1
                    area['updated_at'] = datetime.utcnow().isoformat()
        
        # Clean regular areas (remove cells without trees if needed)
        for area in regular_areas:
            if 'cells' in area:
                # Regular areas don't directly reference trees, but we can validate positions
                valid_cells = []
                for cell in area['cells']:
                    row, col = cell.get('row'), cell.get('col')
                    if (0 <= row < dome.internal_rows and 0 <= col < dome.internal_cols):
                        valid_cells.append(cell)
                
                if len(valid_cells) != len(area['cells']):
                    area['cells'] = valid_cells
                    cleaned_count += 1
                    area['updated_at'] = datetime.utcnow().isoformat()
        
        # Save cleaned data
        areas_data['drag_areas'] = drag_areas
        areas_data['areas'] = regular_areas
        dome.info = json.dumps(areas_data)
        db.session.commit()
        
        print(f"✅ Cleaned {cleaned_count} areas for dome {dome_id}")
        
        return jsonify({
            'success': True,
            'message': f'Cleaned {cleaned_count} areas',
            'cleaned_count': cleaned_count
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error cleaning areas: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/batch_area_operation/<int:dome_id>', methods=['POST'])
@login_required
def batch_area_operation(dome_id):
    """Perform batch operations on areas (show/hide all, delete multiple, etc.)"""
    try:
        data = request.get_json()
        operation = data.get('operation')  # 'show_all', 'hide_all', 'delete_selected'
        area_ids = data.get('area_ids', [])
        area_type = data.get('area_type', 'both')  # 'drag', 'regular', or 'both'
        
        if not operation:
            return jsonify({'success': False, 'error': 'Operation is required'}), 400
        
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Get existing areas
        try:
            # Check if dome has info field and it's not None
            if hasattr(dome, 'info') and dome.info:
                areas_data = json.loads(dome.info)
                drag_areas = areas_data.get('drag_areas', [])
                regular_areas = areas_data.get('areas', [])
            else:
                # Initialize empty info if it doesn't exist
                dome.info = json.dumps({"drag_areas": [], "areas": []})
                db.session.commit()
                drag_areas = []
                regular_areas = []
            
            # If no areas exist, return early
            if len(drag_areas) == 0 and len(regular_areas) == 0:
                return jsonify({'success': False, 'error': 'No areas to clean'}), 400
                
        except Exception as area_error:
            print(f"⚠️ Error loading areas for cleanup: {area_error}")
            return jsonify({'success': False, 'error': 'Failed to load areas for cleanup'}), 400
        
        affected_count = 0
        
        if operation == 'show_all':
            if area_type in ['drag', 'both']:
                for area in drag_areas:
                    area['visible'] = True
                    affected_count += 1
            if area_type in ['regular', 'both']:
                for area in regular_areas:
                    area['visible'] = True
                    affected_count += 1
                    
        elif operation == 'hide_all':
            if area_type in ['drag', 'both']:
                for area in drag_areas:
                    area['visible'] = False
                    affected_count += 1
            if area_type in ['regular', 'both']:
                for area in regular_areas:
                    area['visible'] = False
                    affected_count += 1
                    
        elif operation == 'delete_selected':
            if area_ids:
                # Remove selected drag areas
                if area_type in ['drag', 'both']:
                    original_count = len(drag_areas)
                    drag_areas = [area for area in drag_areas if area.get('id') not in area_ids]
                    affected_count += original_count - len(drag_areas)
                
                # Remove selected regular areas
                if area_type in ['regular', 'both']:
                    original_count = len(regular_areas)
                    regular_areas = [area for area in regular_areas if area.get('id') not in area_ids]
                    affected_count += original_count - len(regular_areas)
        
        # Save changes
        areas_data['drag_areas'] = drag_areas
        areas_data['areas'] = regular_areas
        dome.info = json.dumps(areas_data)
        db.session.commit()
        
        print(f"✅ Batch operation '{operation}' completed: {affected_count} areas affected")
        
        return jsonify({
            'success': True,
            'message': f'Operation completed: {affected_count} areas affected',
            'affected_count': affected_count
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in batch area operation: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500



@app.route('/api/get_drag_area_full/<int:area_id>')
@login_required
def get_drag_area_full(area_id):
    """Get complete drag area data with all tree information"""
    try:
        print(f"🔍 Getting full data for drag area {area_id}")
        
        # Get the drag area
        drag_area = DragArea.query.filter_by(id=area_id).first()
        if not drag_area:
            return jsonify({'success': False, 'error': 'Drag area not found'}), 404
        
        # Verify ownership through dome
        dome = Dome.query.filter_by(id=drag_area.dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        # Get all trees in this area with full data
        area_trees = []
        drag_area_trees = DragAreaTree.query.filter_by(drag_area_id=area_id).all()
        
        for dat in drag_area_trees:
            tree = Tree.query.filter_by(id=dat.tree_id, user_id=current_user.id).first()
            if tree:
                tree_data = {
                    'id': tree.id,
                    'name': tree.name,
                    'breed': tree.breed or '',
                    'life_days': tree.life_days or 0,
                    'info': tree.info or '',
                    'image_url': tree.image_url or '',
                    'internal_row': tree.internal_row,
                    'internal_col': tree.internal_col,
                    'relativeRow': dat.relative_row,
                    'relativeCol': dat.relative_col,
                    'relative_row': dat.relative_row,
                    'relative_col': dat.relative_col,
                    
                    # Plant relationship data
                    'plant_type': tree.plant_type or 'mother',
                    'mother_plant_id': tree.mother_plant_id,
                    'cutting_notes': tree.cutting_notes or '',
                    'is_mother_plant': tree.plant_type == 'mother',
                    'is_cutting': tree.plant_type == 'cutting',
                    
                    # Additional metadata
                    'user_id': tree.user_id,
                    'dome_id': tree.dome_id,
                    'created_at': tree.created_at.isoformat() if tree.created_at else None,
                    'updated_at': tree.updated_at.isoformat() if tree.updated_at else None
                }
                area_trees.append(tree_data)
        
        # ✅ FIXED: Build relationship metadata for paste operation
        mother_cutting_pairs = []
        relationship_stats = {
        'total_trees': len(area_trees),
        'mothers': 0,
        'cuttings': 0,
        'relationships': 0,
        'preserved_relationships': 0
        }
        
        # Build mother-cutting pairs for trees that have relationships
        area_data = {
        'id': drag_area.id,
        'name': drag_area.name,
        'color': drag_area.color,
        'width': drag_area.width,
        'height': drag_area.height,
        'minRow': drag_area.min_row,
        'maxRow': drag_area.max_row,
        'minCol': drag_area.min_col,
        'maxCol': drag_area.max_col,
        'trees': area_trees,
        'tree_count': len(area_trees),
        'dome_id': drag_area.dome_id,
        'visible': drag_area.visible,
        'created_at': drag_area.created_at.isoformat() if drag_area.created_at else None,
        # ✅ FIXED: Include relationship metadata for paste operation
        'relationship_metadata': relationship_metadata,
        'trees_data': area_trees  # Also include as trees_data for paste compatibility
        }
        
        print(f"✅ Retrieved full data for area '{drag_area.name}' with {len(area_trees)} trees")
        print(f"🔗 Relationship metadata: {len(mother_cutting_pairs)} mother-cutting pairs")
        
        return jsonify({
        'success': True,
        'area': area_data
        })
        
    except Exception as e:
        print(f"❌ Error getting full drag area data: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/paste_drag_area/<int:dome_id>', methods=['POST'])
@login_required
def paste_drag_area(dome_id):
    """Paste a copied drag area with cross-dome support"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404
        
        data = request.get_json()
        clipboard_data = data.get('clipboard_data')
        paste_row = data.get('paste_row', 0)
        paste_col = data.get('paste_col', 0)
        new_name = data.get('name', clipboard_data.get('name', 'Pasted Area'))
        create_trees = data.get('create_trees', True)
        
        if not clipboard_data:
            return jsonify({'success': False, 'error': 'No clipboard data provided'}), 400
        
        print(f"🔄 Pasting drag area '{new_name}' to dome {dome_id} at ({paste_row}, {paste_col})")
        
        # Check for name conflicts
        existing_area = DragArea.query.filter_by(dome_id=dome_id, name=new_name).first()
        if existing_area:
            return jsonify({'success': False, 'error': 'Area name already exists'}), 400
        
        # Calculate new boundaries
        width = clipboard_data.get('width', 1)
        height = clipboard_data.get('height', 1)
        new_min_row = paste_row
        new_max_row = paste_row + height - 1
        new_min_col = paste_col
        new_max_col = paste_col + width - 1
        
        # Validate boundaries
        if new_max_row >= dome.internal_rows or new_max_col >= dome.internal_cols:
            return jsonify({
                'success': False, 
                'error': f'Area would extend outside grid boundaries ({dome.internal_rows}x{dome.internal_cols})'
            }), 400
        
        # Create new drag area
        new_area = DragArea(
            name=new_name,
            color=clipboard_data.get('color', '#007bff'),
            min_row=new_min_row,
            max_row=new_max_row,
            min_col=new_min_col,
            max_col=new_max_col,
            width=width,
            height=height,
            dome_id=dome_id,
            visible=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.session.add(new_area)
        db.session.flush()  # Get the ID
        
        # Create trees if requested
        new_tree_ids = []
        if create_trees and clipboard_data.get('trees'):
            for tree_data in clipboard_data['trees']:
                try:
                    # Calculate new position
                    new_row = paste_row + tree_data.get('relative_row', 0)
                    new_col = paste_col + tree_data.get('relative_col', 0)
                    
                    # Check if position is available
                    existing_tree = Tree.query.filter_by(
                        dome_id=dome_id,
                        internal_row=new_row,
                        internal_col=new_col,
                        user_id=current_user.id
                    ).first()
                    
                    if existing_tree:
                        print(f"⚠️ Position ({new_row}, {new_col}) occupied, skipping tree '{tree_data['name']}'")
                        continue
                    
                    # Create new tree
                    new_tree = Tree(
                        name=tree_data['name'],
                        breed=tree_data.get('breed', ''),
                        dome_id=dome_id,
                        internal_row=new_row,
                        internal_col=new_col,
                        image_url=tree_data.get('image_url'),
                        info=tree_data.get('info', ''),
                        life_days=tree_data.get('life_days', 0),
                        user_id=current_user.id,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    
                    # Set plant type and relationships
                    if hasattr(Tree, 'plant_type'):
                        new_tree.plant_type = tree_data.get('plant_type', 'mother')
                    if hasattr(Tree, 'cutting_notes'):
                        new_tree.cutting_notes = tree_data.get('cutting_notes', '')
                    
                    db.session.add(new_tree)
                    db.session.flush()  # Get the ID
                    
                    # Create drag area tree association
                    drag_area_tree = DragAreaTree(
                        drag_area_id=new_area.id,
                        tree_id=new_tree.id,
                        relative_row=tree_data.get('relative_row', 0),
                        relative_col=tree_data.get('relative_col', 0),
                        created_at=datetime.utcnow()
                    )
                    
                    db.session.add(drag_area_tree)
                    new_tree_ids.append(new_tree.id)
                    
                    print(f"✅ Created tree '{new_tree.name}' at ({new_row}, {new_col})")
                    
                except Exception as tree_error:
                    print(f"⚠️ Error creating tree '{tree_data.get('name', 'Unknown')}': {tree_error}")
                    continue
        
        db.session.commit()
        
        print(f"✅ Pasted drag area '{new_name}' with {len(new_tree_ids)} trees")
        
        return jsonify({
            'success': True,
            'message': f'Area "{new_name}" pasted successfully!',
            'drag_area_id': new_area.id,
            'trees_created': len(new_tree_ids),
            'area_details': {
                'id': new_area.id,
                'name': new_name,
                'bounds': f"({new_min_row},{new_min_col}) to ({new_max_row},{new_max_col})",
                'size': f"{width}×{height}",
                'tree_count': len(new_tree_ids)
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in paste_drag_area: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _extract_clipboard_data(data):
    """Extract and validate clipboard data from request"""
    try:
        # Method 1: Frontend clipboard data
        if data.get('trees_data') or data.get('trees'):
            print("📋 Using frontend clipboard data...")
            
            copied_area = {
                'name': data.get('name', 'Copied Area'),
                'color': data.get('color', '#007bff'),
                'width': data.get('width', 1),
                'height': data.get('height', 1),
                'trees': []
            }
            
            # Convert trees_data to internal format
            trees_data = data.get('trees_data', data.get('trees', []))
            min_row = data.get('minRow', data.get('min_row', 0))
            min_col = data.get('minCol', data.get('min_col', 0))
            
            for i, tree_data in enumerate(trees_data):
                tree_row = tree_data.get('internal_row', 0)
                tree_col = tree_data.get('internal_col', 0)
                
                copied_area['trees'].append({
                    'name': tree_data.get('name', f'Tree {i+1}'),
                    'breed': tree_data.get('breed', ''),
                    'life_days': tree_data.get('life_days', 0),
                    'info': tree_data.get('info', ''),
                    'image_url': tree_data.get('image_url', ''),
                    'relativeRow': tree_row - min_row,
                    'relativeCol': tree_col - min_col,
                    'plant_type': tree_data.get('plant_type', 'mother'),
                    'mother_plant_id': tree_data.get('mother_plant_id'),
                    'cutting_notes': tree_data.get('cutting_notes', ''),
                    'paste_metadata': tree_data.get('paste_metadata', {}),
                    'id': tree_data.get('id', f'temp_{i}')  # For relationship mapping
                })
            
            return {
                'success': True,
                'copied_area': copied_area,
                'source': 'frontend',
                'paste_row': data.get('minRow', data.get('min_row', 0)),
                'paste_col': data.get('minCol', data.get('min_col', 0)),
                'new_name': data.get('name', 'Pasted Area')
            }
        
        # Method 2: Session clipboard data
        else:
            print("📋 Using session clipboard data...")
            
            copied_area = session.get('copied_drag_area')
            if not copied_area:
                return {'success': False, 'error': 'No area in clipboard'}
            
            new_name = data.get('name', '').strip()
            if not new_name:
                return {'success': False, 'error': 'Area name is required'}
            
            return {
                'success': True,
                'copied_area': copied_area,
                'source': 'session',
                'paste_row': data.get('row', 0),
                'paste_col': data.get('col', 0),
                'new_name': new_name
            }
            
    except Exception as e:
        return {'success': False, 'error': f'Failed to extract clipboard data: {str(e)}'}


def _validate_area_placement(dome, copied_area, paste_row, paste_col, create_trees, user_id):
    """Validate that the area can be placed at the specified position"""
    try:
        area_width = copied_area['width']
        area_height = copied_area['height']
        
        # Check bounds
        if (paste_row + area_height > dome.internal_rows or 
            paste_col + area_width > dome.internal_cols or
            paste_row < 0 or paste_col < 0):
            return {
                'success': False,
                'error': f'Area doesn\'t fit. Required: {area_width}×{area_height}, '
                        f'Available space: {dome.internal_cols - paste_col}×{dome.internal_rows - paste_row}'
            }
        
        # Check for existing trees if creating trees
        if create_trees and copied_area.get('trees'):
            for tree_data in copied_area['trees']:
                new_row = paste_row + tree_data['relativeRow']
                new_col = paste_col + tree_data['relativeCol']
                
                existing_tree = Tree.query.filter_by(
                    dome_id=dome.id,
                    user_id=user_id,
                    internal_row=new_row,
                    internal_col=new_col
                ).first()
                
                if existing_tree:
                    return {
                        'success': False,
                        'error': f'Cannot paste: Tree already exists at position ({new_row}, {new_col})'
                    }
        
        return {'success': True,}
        
    except Exception as e:
        return {'success': False, 'error': f'Validation failed: {str(e)}'}


def _area_name_exists(dome, new_name):
    """Check if area name already exists in dome"""
    try:
        areas_data = json.loads(dome.info or '{"drag_areas": []}')
        if 'drag_areas' not in areas_data:
            return False
        
        return any(area.get('name') == new_name for area in areas_data['drag_areas'])
    except:
        return False


def _create_drag_area_record(dome_id, new_name, copied_area, paste_row, paste_col, data):
    """Create DragArea database record"""
    try:
        area_width = copied_area['width']
        area_height = copied_area['height']
        
        drag_area = DragArea(
            name=new_name,
            color=copied_area['color'],
            dome_id=dome_id,
            min_row=paste_row,
            max_row=paste_row + area_height - 1,
            min_col=paste_col,
            max_col=paste_col + area_width - 1,
            width=area_width,
            height=area_height,
            visible=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        # Add enhanced fields if available
        relationship_metadata = data.get('relationship_metadata', {})
        if hasattr(DragArea, 'relationship_metadata'):
            drag_area.relationship_metadata = json.dumps(relationship_metadata) if relationship_metadata else None
        if hasattr(DragArea, 'cells_data'):
            drag_area.cells_data = json.dumps(data.get('cells_data', []))
        if hasattr(DragArea, 'supports_empty_cells'):
            drag_area.supports_empty_cells = data.get('supports_empty_cells', True)
        if hasattr(DragArea, 'paste_timestamp'):
            drag_area.paste_timestamp = datetime.utcnow()
        if hasattr(DragArea, 'area_type'):
            drag_area.area_type = 'pasted_area'
        
        db.session.add(drag_area)
        db.session.flush()
        
        print(f"✅ Created DragArea record with ID: {drag_area.id}")
        return {'drag_area_id': drag_area.id}
        
    except Exception as e:
        print(f"⚠️ Could not create DragArea record: {e}")
        return {'drag_area_id': None}


def _create_trees_with_relationships(copied_area, paste_row, paste_col, dome_id, user_id, create_trees, drag_area_id):
    """Create trees with proper plant relationships - COMPREHENSIVE FIX"""
    new_tree_ids = []
    trees_created = 0
    breed_debug_info = []
    relationship_stats = {
        'mothers_created': 0,
        'cuttings_created': 0,
        'relationships_preserved': 0,
        'relationships_broken': 0,
        'mothers_updated': []
    }

    if not create_trees or not copied_area.get('trees'):
        return {
            'new_tree_ids': new_tree_ids,
            'trees_created': trees_created,
            'breed_debug_info': breed_debug_info,
            'relationship_stats': relationship_stats
        }

    print(f"🌱 Creating {len(copied_area['trees'])} trees from copied area...")

    # ✅ ENHANCED DEBUG: Show what data we're working with
    print(f"🔍 === DEBUGGING PASTE OPERATION ===")
    print(f"🔍 Trees to create: {len(copied_area.get('trees', []))}")
    print(f"🔍 Copied area keys: {list(copied_area.keys())}")
    print(f"🔍 Copied area type: {type(copied_area)}")

    for i, tree_data in enumerate(copied_area.get('trees', [])):
        print(f"🌳 Tree {i}: '{tree_data.get('name', 'Unknown')}'")
        print(f"   - Plant type: {tree_data.get('plant_type', 'Unknown')}")
        print(f"   - Mother plant ID: {tree_data.get('mother_plant_id', 'None')}")
        print(f"   - Original ID: {tree_data.get('id', 'None')}")
        print(f"   - Has mother_plant_id key: {'mother_plant_id' in tree_data}")
        print(f"   - Tree data type: {type(tree_data)}")
        print(f"   - All keys: {list(tree_data.keys())}")

    print(f"🔍 === END PASTE DEBUG INFO ===")

    # ✅ STEP 1: Create ID mapping dictionaries
    original_to_new_id_mapping = {}
    mother_id_mapping = {}

    # ✅ STEP 2: First pass - Create all trees and build ID mappings
    for i, tree_data in enumerate(copied_area['trees']):
        new_row = paste_row + tree_data['relativeRow']
        new_col = paste_col + tree_data['relativeCol']

        # Process breed data
        original_breed = tree_data.get('breed', '')
        breed_value = original_breed.strip() if original_breed and original_breed.strip() else None

        # ✅ CRITICAL: Plant relationship handling with better data extraction
        plant_type = tree_data.get('plant_type', 'mother')
        cutting_notes = tree_data.get('cutting_notes', '')
        original_mother_id = tree_data.get('mother_plant_id')
        
        # ✅ ENHANCED: Also check alternative keys for mother ID
        if not original_mother_id:
            original_mother_id = tree_data.get('mother_tree_id')
        if not original_mother_id:
            original_mother_id = tree_data.get('mother_id')
        
        # ✅ CRITICAL: Debug what we're getting
        print(f"🔍 Tree {i} relationship debug:")
        print(f"   - tree_data keys: {list(tree_data.keys())}")
        print(f"   - plant_type: {tree_data.get('plant_type')}")
        print(f"   - mother_plant_id: {tree_data.get('mother_plant_id')}")
        print(f"   - original_mother_id extracted: {original_mother_id}")

        # ✅ CRITICAL: Store original_mother_id in paste metadata for later use
        paste_metadata = tree_data.get('paste_metadata', {})

        # ✅ DEBUG: Log what we're working with for each tree
        print(f"🌱 Creating tree {i}: '{tree_data.get('name', 'Unknown')}'")
        print(f"   - Plant type: {plant_type}")
        print(f"   - Original mother ID: {original_mother_id}")
        print(f"   - Original tree ID: {tree_data.get('id')}")

        # Enhanced paste metadata
        enhanced_paste_metadata = {
            **paste_metadata,
            'paste_timestamp': datetime.utcnow().isoformat(),
            'original_tree_id': tree_data.get('id'),
            'original_mother_id': original_mother_id,  # ✅ CRITICAL: Store this!
            'paste_operation': True
        }

        try:
            # ✅ CRITICAL: Create tree WITHOUT mother_plant_id initially
            # We'll set it in the second pass after all trees are created
            new_tree = Tree(
                name=tree_data.get('name', f'Tree {i+1}'),
                breed=breed_value,
                internal_row=new_row,
                internal_col=new_col,
                life_days=tree_data.get('life_days', 0),
                info=tree_data.get('info', ''),
                image_url=tree_data.get('image_url', ''),
                dome_id=dome_id,
                user_id=user_id,
                plant_type=plant_type,
                cutting_notes=cutting_notes,
                mother_plant_id=None,  # ✅ CRITICAL: Set to None initially
                paste_metadata=json.dumps(enhanced_paste_metadata) if enhanced_paste_metadata else None,
                planted_date=datetime.utcnow(),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            db.session.add(new_tree)
            db.session.flush()  # Get the ID without committing

            new_tree_ids.append(new_tree.id)
            trees_created += 1

            # ✅ ENHANCED: Track ALL trees for relationship mapping with consistent keys
            original_id = tree_data.get('id', f'temp_{i}')
            if original_id:
                print(f"🔗 Mapping tree {i}: original_id='{original_id}' -> new_id={new_tree.id} (type: {plant_type})")
                
                # Add to general ID mapping for all trees (both string and original type keys)
                original_id_str = str(original_id)
                original_to_new_id_mapping[original_id_str] = new_tree.id
                original_to_new_id_mapping[original_id] = new_tree.id  # Keep original type for compatibility

                # Also add mother trees to specific mother mapping
                if plant_type == 'mother':
                    mother_id_mapping[original_id_str] = new_tree.id
                    mother_id_mapping[original_id] = new_tree.id  # Keep original type for compatibility
                    relationship_stats['mothers_created'] += 1
                elif plant_type == 'cutting':
                    relationship_stats['cuttings_created'] += 1

            # Create DragAreaTree association if DragArea was created
            if drag_area_id:
                drag_area_tree = DragAreaTree(
                    drag_area_id=drag_area_id,
                    tree_id=new_tree.id,
                    relative_row=tree_data['relativeRow'],
                    relative_col=tree_data['relativeCol'],
                    created_at=datetime.utcnow()
                )
                db.session.add(drag_area_tree)

            print(f"✅ Tree created: '{new_tree.name}' ({plant_type}) at ({new_row}, {new_col})")

            breed_debug_info.append({
                'tree_name': new_tree.name,
                'original_breed': original_breed,
                'processed_breed': breed_value,
                'stored_breed': new_tree.breed,
                'position': f"({new_row}, {new_col})",
                'plant_type': plant_type,
                'original_id': tree_data.get('id')
            })

        except Exception as tree_error:
            print(f"❌ Error creating tree {i+1}: {tree_error}")
            raise tree_error

    # ✅ STEP 3: Second pass - Set mother_plant_id relationships
    print(f"🔗 === STARTING RELATIONSHIP PROCESSING ===")
    print(f"🔗 Original to new ID mapping: {dict(list(original_to_new_id_mapping.items())[:5])}...")  # Show first 5
    print(f"🔗 Mother ID mapping: {dict(list(mother_id_mapping.items())[:5])}...")  # Show first 5

    # Process each tree to set mother relationships
    for i, tree_data in enumerate(copied_area['trees']):
        if i < len(new_tree_ids):
            tree_id = new_tree_ids[i]
            tree = db.session.get(Tree, tree_id)

            if tree and tree.plant_type == 'cutting':
                # ✅ ENHANCED: Get original mother ID from multiple sources
                original_mother_id = tree_data.get('mother_plant_id')
                if not original_mother_id:
                    original_mother_id = tree_data.get('mother_tree_id')
                if not original_mother_id:
                    original_mother_id = tree_data.get('mother_id')

                if not original_mother_id:
                    print(f"⚠️ Cutting tree '{tree.name}' has no original mother ID - skipping")
                    continue

                print(f"🌿 Processing cutting '{tree.name}' - Original mother ID: {original_mother_id}")

                new_mother_id = None

                # ✅ ENHANCED: Try multiple approaches to find the mother tree
                original_mother_str = str(original_mother_id)

                # Approach 1: Check if mother was also pasted (in our mappings)
                if original_mother_str in original_to_new_id_mapping:
                    new_mother_id = original_to_new_id_mapping[original_mother_str]
                    print(f"✅ Found pasted mother in mapping (str key): {original_mother_id} -> {new_mother_id}")
                elif original_mother_id in original_to_new_id_mapping:
                    new_mother_id = original_to_new_id_mapping[original_mother_id]
                    print(f"✅ Found pasted mother in mapping (orig key): {original_mother_id} -> {new_mother_id}")

                # Approach 2: Check if mother exists in the same dome (not pasted, but existing)
                elif not new_mother_id:
                    existing_mother = Tree.query.filter_by(
                        dome_id=dome_id,
                        user_id=user_id,
                        id=original_mother_id
                    ).first()

                    if existing_mother and (existing_mother.plant_type == 'mother' or not existing_mother.plant_type):
                        new_mother_id = existing_mother.id
                        print(f"✅ Found existing mother tree in dome: {original_mother_id}")
                    else:
                        print(f"❌ Mother tree {original_mother_id} not found anywhere")

                # ✅ CRITICAL: Set the relationship if mother was found
                if new_mother_id:
                    # Verify the mother tree exists and is valid
                    mother_tree = db.session.get(Tree, new_mother_id)
                    if mother_tree and (mother_tree.plant_type == 'mother' or not mother_tree.plant_type):
                        tree.mother_plant_id = new_mother_id
                        relationship_stats['relationships_preserved'] += 1

                        # ✅ CRITICAL: Create PlantRelationship record for bidirectional relationship
                        try:
                            # Check if relationship already exists
                            existing_relationship = PlantRelationship.query.filter_by(
                                cutting_tree_id=tree.id
                            ).first()
                            
                            if not existing_relationship:
                                plant_relationship = PlantRelationship(
                                    mother_tree_id=new_mother_id,
                                    cutting_tree_id=tree.id,
                                    user_id=user_id,
                                    dome_id=dome_id,
                                    notes=tree.cutting_notes or '',
                                    cutting_date=datetime.utcnow()
                                )
                                db.session.add(plant_relationship)
                                print(f"✅ Created PlantRelationship record")
                            else:
                                print(f"ℹ️ PlantRelationship already exists")
                        except Exception as rel_error:
                            print(f"⚠️ Error creating PlantRelationship: {rel_error}")

                        # ✅ CRITICAL: Track that this mother tree was updated
                        if new_mother_id not in relationship_stats['mothers_updated']:
                            relationship_stats['mothers_updated'].append(new_mother_id)

                        # Update paste metadata
                        paste_meta = tree.get_paste_metadata()
                        paste_meta['relationship_preserved'] = True
                        paste_meta['original_mother_id'] = original_mother_id
                        paste_meta['new_mother_id'] = new_mother_id
                        tree.set_paste_metadata(paste_meta)

                        print(f"✅ Relationship preserved: '{tree.name}' -> mother '{mother_tree.name}' (ID {new_mother_id})")
                    else:
                        print(f"❌ Invalid mother tree ID {new_mother_id} - tree not found or not a mother")
                        relationship_stats['relationships_broken'] += 1
                else:
                    relationship_stats['relationships_broken'] += 1

                    # Update paste metadata for broken relationship
                    paste_meta = tree.get_paste_metadata()
                    paste_meta['relationship_preserved'] = False
                    paste_meta['original_mother_id'] = original_mother_id
                    paste_meta['relationship_broken_reason'] = 'Mother tree not found in paste operation'
                    tree.set_paste_metadata(paste_meta)

                    print(f"❌ Relationship broken: '{tree.name}' - mother {original_mother_id} not found")

    # ✅ STEP 4: Update mother trees' cutting counts
    print("🔄 Updating mother trees' cutting counts...")
    updated_mothers = set()

    for tree_id in new_tree_ids:
        tree = db.session.get(Tree, tree_id)
        if tree and tree.plant_type == 'cutting' and tree.mother_plant_id:
            if tree.mother_plant_id not in updated_mothers:
                mother_tree = db.session.get(Tree, tree.mother_plant_id)
                if mother_tree:
                    # Update mother tree's updated_at timestamp to reflect new cutting
                    mother_tree.updated_at = datetime.utcnow()
                    updated_mothers.add(tree.mother_plant_id)
                    print(f"✅ Updated mother tree '{mother_tree.name}' timestamp")

    print(f"✅ Updated {len(updated_mothers)} mother trees")

    # ✅ STEP 5: Final validation pass
    print("🔍 Final validation pass...")
    final_validation_stats = {
        'trees_with_preserved_relationships': 0,
        'trees_with_broken_relationships': 0,
        'orphaned_cuttings': 0
    }

    for tree_id in new_tree_ids:
        tree = db.session.get(Tree, tree_id)
        if tree and tree.plant_type == 'cutting':
            if tree.mother_plant_id:
                final_validation_stats['trees_with_preserved_relationships'] += 1
            else:
                final_validation_stats['orphaned_cuttings'] += 1

    print(f"📊 Final validation results:")
    print(f"   - Trees with preserved relationships: {final_validation_stats['trees_with_preserved_relationships']}")
    print(f"   - Orphaned cuttings: {final_validation_stats['orphaned_cuttings']}")

    return {
        'new_tree_ids': new_tree_ids,
        'trees_created': trees_created,
        'breed_debug_info': breed_debug_info,
        'relationship_stats': relationship_stats,
        'final_validation': final_validation_stats
    }
def _update_dome_info(dome, new_name, copied_area, paste_row, paste_col, new_tree_ids, drag_area_id, clipboard_source, relationship_stats):
    """Update dome.info with new area data"""
    try:
        areas_data = json.loads(dome.info or '{"drag_areas": []}')
        if 'drag_areas' not in areas_data:
            areas_data['drag_areas'] = []
    except:
        areas_data = {'drag_areas': []}
    
    area_width = copied_area['width']
    area_height = copied_area['height']
    
    new_area = {
        'id': drag_area_id or int(time.time() * 1000),
        'name': new_name,
        'color': copied_area['color'],
        'tree_ids': new_tree_ids,
        'dome_id': dome.id,
        'min_row': paste_row,
        'max_row': paste_row + area_height - 1,
        'min_col': paste_col,
        'max_col': paste_col + area_width - 1,
        'width': area_width,
        'height': area_height,
        'created_at': datetime.utcnow().isoformat(),
        'updated_at': datetime.utcnow().isoformat(),
        'user_id': dome.user_id,
        'visible': True,
        'clipboard_source': clipboard_source,
        'relationship_stats': relationship_stats,
        'is_pasted': True,
        'paste_timestamp': datetime.utcnow().isoformat()
    }
    new_area['area_id'] = new_area['id']
    
    areas_data['drag_areas'].append(new_area)
    dome.info = json.dumps(areas_data)


def _build_success_message(new_name, trees_created, relationship_stats):
    """Build success message with relationship info"""
    message = f'Area "{new_name}" pasted with {trees_created} trees'
    
    if relationship_stats['relationships_preserved'] > 0 or relationship_stats['relationships_broken'] > 0:
        message += f' ({relationship_stats["relationships_preserved"]} relationships preserved'
        if relationship_stats['relationships_broken'] > 0:
            message += f', {relationship_stats["relationships_broken"]} broken'
        message += ')'
    
    return message
@app.route('/api/create_drag_area/<int:dome_id>', methods=['POST'])
@login_required
def create_drag_area(dome_id):
    """Create a new drag area from selected cells"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404
        
        data = request.get_json()
        print(f"🔍 Creating drag area with data: {data}")
        
        # Extract data
        name = data.get('name', '').strip()
        color = data.get('color', '#007bff')
        min_row = data.get('min_row', 0)
        max_row = data.get('max_row', 0)
        min_col = data.get('min_col', 0)
        max_col = data.get('max_col', 0)
        tree_ids = data.get('tree_ids', [])
        cells_data = data.get('cells_data', [])
        
        # Validation
        if not name:
            return jsonify({'success': False, 'error': 'Area name is required'}), 400
        
        # Check for duplicate names
        existing_area = DragArea.query.filter_by(dome_id=dome_id, name=name).first()
        if existing_area:
            return jsonify({'success': False, 'error': 'Area name already exists'}), 400
        
        # Calculate dimensions
        width = max_col - min_col + 1
        height = max_row - min_row + 1
        
        # Create the drag area
        drag_area = DragArea(
            name=name,
            color=color,
            min_row=min_row,
            max_row=max_row,
            min_col=min_col,
            max_col=max_col,
            width=width,
            height=height,
            dome_id=dome_id,
            visible=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.session.add(drag_area)
        db.session.flush()  # Get the ID
        
        # Associate trees with the drag area
        for tree_id in tree_ids:
            tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id, dome_id=dome_id).first()
            if tree:
                relative_row = tree.internal_row - min_row
                relative_col = tree.internal_col - min_col
                
                drag_area_tree = DragAreaTree(
                    drag_area_id=drag_area.id,
                    tree_id=tree_id,
                    relative_row=relative_row,
                    relative_col=relative_col,
                    created_at=datetime.utcnow()
                )
                
                db.session.add(drag_area_tree)
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'drag_area_id': drag_area.id,
            'area': {
                'id': drag_area.id,
                'name': name,
                'color': color,
                'min_row': min_row,
                'max_row': max_row,
                'min_col': min_col,
                'max_col': max_col,
                'width': width,
                'height': height,
                'tree_count': len(tree_ids),
                'created_at': drag_area.created_at.isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in create_drag_area: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/tree/<int:tree_id>/breeds')
@login_required
def get_tree_breeds(tree_id):
    """Get available breeds for a tree's farm"""
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        # Default breeds - you can customize this
        default_breeds = [
            'Apple', 'Orange', 'Mango', 'Coconut', 'Banana', 'Avocado', 
            'Cherry', 'Peach', 'Lemon', 'Lime', 'Papaya', 'Guava'
        ]
        
        return jsonify({
            'success': True,
            'breeds': default_breeds,
            'current_breed': tree.breed or ''
        })
        
    except Exception as e:
        print(f"❌ Error getting tree breeds: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/paste_drag_area_at_position/<int:dome_id>', methods=['POST'])
@login_required
def paste_drag_area_at_position(dome_id):
    """Paste a copied drag area at a specific position (for click-to-paste) - ENHANCED"""
    try:
        data = request.get_json()
        paste_row = data.get('row')
        paste_col = data.get('col')
        auto_name = data.get('auto_name', True)
        create_trees = data.get('create_trees', True)
        
        if paste_row is None or paste_col is None:
            return jsonify({'success': False, 'error': 'Position is required'}), 400
        
        print(f"🎯 Click-to-paste request at ({paste_row}, {paste_col}) for dome {dome_id}")
        
        # Verify dome ownership first
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # ✅ ENHANCED: Try to get clipboard data from multiple sources
        copied_area = None
        clipboard_source = None
        
        # Method 1: Check if frontend sent clipboard data directly
        if data.get('clipboard_data'):
            print("📋 Using clipboard data from frontend request")
            copied_area = data.get('clipboard_data')
            clipboard_source = 'frontend_direct'
            
        # Method 2: Check session clipboard
        elif session.get('copied_drag_area'):
            print("📋 Using session clipboard data")
            copied_area = session.get('copied_drag_area')
            clipboard_source = 'session'
            
        # Method 3: Check if frontend clipboard data is available (fallback)
        elif data.get('use_frontend_clipboard'):
            print("📋 Frontend clipboard requested but no data provided")
            return jsonify({
                'success': False, 
                'error': 'Frontend clipboard requested but no clipboard data provided'
            }), 400
        
        if not copied_area:
            return jsonify({
                'success': False, 
                'error': 'No area in clipboard. Please copy an area first.'
            }), 400
        
        print(f"📋 Found clipboard data from {clipboard_source}")
        print(f"📊 Clipboard contains: {len(copied_area.get('trees', []))} trees")
        
        # ✅ ENHANCED: Generate automatic name with better collision detection
        base_name = copied_area.get('name', 'Copied Area')
        if auto_name:
            new_name = f"{base_name} Copy"
            counter = 1
            
            # Get existing areas from multiple sources
            existing_names = set()
            
            # Check DragArea table
            try:
                existing_drag_areas = DragArea.query.filter_by(dome_id=dome_id).all()
                for area in existing_drag_areas:
                    existing_names.add(area.name)
            except Exception as db_error:
                print(f"⚠️ Could not query DragArea table: {db_error}")
            
            # Check dome.info as fallback
            try:
                areas_data = json.loads(dome.info or '{"drag_areas": []}')
                existing_areas = areas_data.get('drag_areas', [])
                for area in existing_areas:
                    if area.get('name'):
                        existing_names.add(area.get('name'))
            except Exception as json_error:
                print(f"⚠️ Could not parse dome.info: {json_error}")
            
            # Find unique name
            while new_name in existing_names:
                new_name = f"{base_name} Copy {counter}"
                counter += 1
                
            print(f"📝 Generated unique name: '{new_name}'")
        else:
            new_name = data.get('name', f"{base_name} Copy")
        
        # ✅ ENHANCED: Validate area placement before attempting paste
        area_width = copied_area.get('width', 1)
        area_height = copied_area.get('height', 1)
        
        # Check bounds
        if (paste_row + area_height > dome.internal_rows or 
            paste_col + area_width > dome.internal_cols or
            paste_row < 0 or paste_col < 0):
            return jsonify({
                'success': False,
                'error': f'Area doesn\'t fit at position ({paste_row}, {paste_col}). '
                        f'Required: {area_width}×{area_height}, '
                        f'Available space: {dome.internal_cols - paste_col}×{dome.internal_rows - paste_row}'
            }), 400
        
        # Check for tree conflicts if creating trees
        if create_trees and copied_area.get('trees'):
            conflicts = []
            for tree_data in copied_area['trees']:
                tree_relative_row = tree_data.get('relativeRow', tree_data.get('relative_row', 0))
                tree_relative_col = tree_data.get('relativeCol', tree_data.get('relative_col', 0))
                new_row = paste_row + tree_relative_row
                new_col = paste_col + tree_relative_col
                
                # Check if position is occupied
                existing_tree = Tree.query.filter_by(
                    dome_id=dome_id,
                    user_id=current_user.id,
                    internal_row=new_row,
                    internal_col=new_col
                ).first()
                
                if existing_tree:
                    conflicts.append({
                        'tree_name': tree_data.get('name', 'Unknown'),
                        'position': f"({new_row}, {new_col})",
                        'existing_tree': existing_tree.name
                    })
            
            if conflicts:
                conflict_details = "; ".join([
                    f"{c['tree_name']} at {c['position']} (occupied by {c['existing_tree']})" 
                    for c in conflicts
                ])
                return jsonify({
                    'success': False,
                    'error': f'Cannot paste: Tree conflicts detected - {conflict_details}'
                }), 400
        
        # ✅ ENHANCED: Prepare data for main paste function
        if clipboard_source == 'session':
            # For session clipboard, use the existing format
            paste_data = {
                'name': new_name,
                'row': paste_row,
                'col': paste_col,
                'create_trees': create_trees
            }
        else:
            # For frontend clipboard, convert to the format expected by paste_drag_area
            paste_data = {
                'name': new_name,
                'color': copied_area.get('color', '#007bff'),
                'width': area_width,
                'height': area_height,
                'row': paste_row,
                'col': paste_col,
                'minRow': paste_row,
                'maxRow': paste_row + area_height - 1,
                'minCol': paste_col,
                'maxCol': paste_col + area_width - 1,
                'min_row': paste_row,
                'max_row': paste_row + area_height - 1,
                'min_col': paste_col,
                'max_col': paste_col + area_width - 1,
                'create_trees': create_trees,
                
                # ✅ CRITICAL: Include trees data
                'trees_data': copied_area.get('trees', []),
                'trees': copied_area.get('trees', []),
                
                # ✅ NEW: Include relationship metadata
                'relationship_metadata': copied_area.get('relationship_metadata', {}),
                'cells_data': copied_area.get('cells', []),
                'supports_empty_cells': True,
                'clipboard_source': clipboard_source
            }
        
        print(f"📤 Calling main paste function with data: {paste_data.keys()}")
        print(f"🌳 Trees to paste: {len(paste_data.get('trees_data', paste_data.get('trees', [])))}")
        
        # ✅ ENHANCED: Call main paste function with proper data
        try:
            # Create a new request context with the paste data
            from flask import g
            
            # Store original request data
            original_json = request.get_json()
            
            # Temporarily replace request data
            request._cached_json = (paste_data, paste_data)
            
            try:
                # Call the main paste function
                result = paste_drag_area(dome_id)
                
                # ✅ ENHANCED: Add click-to-paste specific information to response
                if hasattr(result, 'get_json') and result.get_json():
                    response_data = result.get_json()
                    if response_data.get('success'):
                        response_data['paste_method'] = 'click_to_paste'
                        response_data['paste_position'] = {'row': paste_row, 'col': paste_col}
                        response_data['clipboard_source'] = clipboard_source
                        response_data['auto_named'] = auto_name
                        
                        print(f"✅ Click-to-paste successful: '{new_name}' at ({paste_row}, {paste_col})")
                        
                        return jsonify(response_data), result.status_code
                    else:
                        print(f"❌ Click-to-paste failed: {response_data.get('error', 'Unknown error')}")
                        return result
                else:
                    return result
                    
            finally:
                # Restore original request data
                request._cached_json = (original_json, original_json)
                
        except Exception as paste_error:
            print(f"❌ Error calling main paste function: {paste_error}")
            import traceback
            print(f"❌ Traceback: {traceback.format_exc()}")
            
            return jsonify({
                'success': False,
                'error': f'Paste operation failed: {str(paste_error)}'
            }), 500
        
    except Exception as e:
        print(f"❌ Error in paste_drag_area_at_position: {str(e)}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ✅ HELPER: Alternative approach using direct function call
@app.route('/paste_drag_area_at_position_direct/<int:dome_id>', methods=['POST'])
@login_required
def paste_drag_area_at_position_direct(dome_id):
    """Direct paste without modifying request object"""
    try:
        data = request.get_json()
        paste_row = data.get('row')
        paste_col = data.get('col')
        
        if paste_row is None or paste_col is None:
            return jsonify({'success': False, 'error': 'Position is required'}), 400
        
        # Get clipboard data
        copied_area = session.get('copied_drag_area')
        if not copied_area:
            return jsonify({'success': False, 'error': 'No area in clipboard'}), 400
        
        # Generate name
        base_name = copied_area.get('name', 'Copied Area')
        new_name = f"{base_name} Copy"
        
        # ✅ DIRECT: Call helper functions from main paste function
        clipboard_result = _extract_clipboard_data({
            'name': new_name,
            'row': paste_row,
            'col': paste_col
        })
        
        if not clipboard_result['success']:
            return jsonify({'success': False, 'error': clipboard_result['error']}), 400
        
        # Validate dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Validate placement
        validation_result = _validate_area_placement(
            dome, clipboard_result['copied_area'], paste_row, paste_col, True, current_user.id
        )
        if not validation_result['success']:
            return jsonify({'success': False, 'error': validation_result['error']}), 400
        
        # Check name conflicts
        if _area_name_exists(dome, new_name):
            counter = 1
            while _area_name_exists(dome, f"{new_name} {counter}"):
                counter += 1
            new_name = f"{new_name} {counter}"
        
        # Create area and trees
        try:
            drag_area_result = _create_drag_area_record(dome_id, new_name, clipboard_result['copied_area'], paste_row, paste_col, data)
            trees_result = _create_trees_with_relationships(
                clipboard_result['copied_area'], paste_row, paste_col, dome_id, current_user.id, 
                True, drag_area_result.get('drag_area_id')
            )
            _update_dome_info(dome, new_name, clipboard_result['copied_area'], paste_row, paste_col, 
                            trees_result['new_tree_ids'], drag_area_result.get('drag_area_id'), 'session', 
                            trees_result['relationship_stats'])
            
            db.session.commit()
            
            success_message = _build_success_message(new_name, trees_result['trees_created'], trees_result['relationship_stats'])
            
            return jsonify({
                'success': True,
                'message': success_message,
                'drag_area_id': drag_area_result.get('drag_area_id'),
                'trees_created': trees_result['trees_created'],
                'relationship_stats': trees_result['relationship_stats'],
                'paste_method': 'click_to_paste_direct',
                'paste_position': {'row': paste_row, 'col': paste_col}
            })
            
        except Exception as transaction_error:
            db.session.rollback()
            raise transaction_error
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in direct paste: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/get_clipboard_area')
@login_required
def get_clipboard_area():
    """Get the area currently in clipboard"""
    try:
        copied_area = session.get('copied_drag_area')
        
        return jsonify({
            'success': True,
            'has_area': copied_area is not None,
            'area': copied_area
        })
        
    except Exception as e:
        print(f"❌ Error getting clipboard area: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/move_dome/<int:dome_id>', methods=['POST'])
@login_required
def move_dome(dome_id):
    try:
        data = request.get_json()
        new_row = data.get('grid_row')
        new_col = data.get('grid_col')
        
        if new_row is None or new_col is None:
            return jsonify({'success': False, 'error': 'Missing grid position'})
        
        # Get the dome
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'})
        
        # Ensure dome belongs to a farm
        if not dome.farm_id:
            return jsonify({'success': False, 'error': 'Invalid dome - must belong to a farm'})
        
        # Check if target position is occupied within the same farm
        existing_dome = Dome.query.filter_by(
            grid_row=new_row, 
            grid_col=new_col,
            user_id=current_user.id,
            farm_id=dome.farm_id
        ).first()
        
        if existing_dome and existing_dome.id != dome_id:
            return jsonify({'success': False, 'error': 'Target position already occupied in this farm'})
        
        # Update dome position
        old_position = f"({dome.grid_row}, {dome.grid_col})"
        dome.grid_row = new_row
        dome.grid_col = new_col
        db.session.commit()
        
        print(f"✅ Dome moved: {dome.name} from {old_position} to ({new_row}, {new_col}) in farm {dome.farm_id}")
        
        return jsonify({'success': True, 'message': 'Dome moved successfully'})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error moving dome: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/swap_domes', methods=['POST'])
@login_required
def swap_domes():
    try:
        data = request.get_json()
        dome1_id = data.get('dome1_id')
        dome2_id = data.get('dome2_id')
        dome1_new_row = data.get('dome1_new_row')
        dome1_new_col = data.get('dome1_new_col')
        dome2_new_row = data.get('dome2_new_row')
        dome2_new_col = data.get('dome2_new_col')
        
        if not all([dome1_id, dome2_id, dome1_new_row is not None, dome1_new_col is not None, 
                   dome2_new_row is not None, dome2_new_col is not None]):
            return jsonify({'success': False, 'error': 'Missing required fields'})
        
        # Get both domes
        dome1 = Dome.query.filter_by(id=dome1_id, user_id=current_user.id).first()
        dome2 = Dome.query.filter_by(id=dome2_id, user_id=current_user.id).first()
        
        if not dome1 or not dome2:
            return jsonify({'success': False, 'error': 'One or both domes not found'})
        
        # ✅ FIXED: Ensure both domes are in the same context (same farm or both global)
        if dome1.farm_id != dome2.farm_id:
            return jsonify({'success': False, 'error': 'Cannot swap domes between different farm contexts'})
        
        # Store old positions for logging
        dome1_old = f"({dome1.grid_row}, {dome1.grid_col})"
        dome2_old = f"({dome2.grid_row}, {dome2.grid_col})"
        
        # Swap positions
        dome1.grid_row = dome1_new_row
        dome1.grid_col = dome1_new_col
        dome2.grid_row = dome2_new_row
        dome2.grid_col = dome2_new_col
        
        db.session.commit()
        
        context = f"farm {dome1.farm_id}" if dome1.farm_id else "global"
        print(f"✅ Domes swapped: {dome1.name} {dome1_old} ↔ {dome2.name} {dome2_old} in {context}")
        
        return jsonify({'success': True, 'message': 'Domes swapped successfully'})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error swapping domes: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/add_farm', methods=['POST'])
@login_required
def add_farm():
    """Add a new farm"""
    try:
        data = request.json
        name = data.get('name', 'ฟาร์มใหม่')
        grid_row = data.get('grid_row', 0)
        grid_col = data.get('grid_col', 0)
        
        # Get grid settings for validation
        try:
            grid = GridSettings.query.first()
            if not grid:
                grid = GridSettings(rows=10, cols=10)
                db.session.add(grid)
                db.session.commit()
        except Exception as e:
            print(f"⚠️ Grid settings error: {e}")
            grid = type('obj', (object,), {'rows': 10, 'cols': 10})
        
        # Validate position
        if grid_row >= grid.rows or grid_col >= grid.cols:
            return jsonify(success=False, error="Position out of bounds"), 400
            
        # Check if position is already occupied
        existing = Farm.query.filter_by(
            grid_row=grid_row, 
            grid_col=grid_col, 
            user_id=current_user.id
        ).first()
        
        if existing:
            return jsonify(success=False, error="Position occupied"), 400

        # Create new farm
        farm = Farm(
            name=name,
            grid_row=grid_row,
            grid_col=grid_col,
            user_id=current_user.id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.session.add(farm)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'farm': {
                'id': farm.id, 
                'name': farm.name,
                'grid_row': farm.grid_row,
                'grid_col': farm.grid_col
            }
        })
        
    except Exception as e:
        print(f"Error adding farm: {e}")
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500
@app.route('/remove_farm_image/<int:farm_id>', methods=['POST'])
@login_required
def remove_farm_image(farm_id):
    """Remove farm image"""
    try:
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify({'success': False, 'error': 'Farm not found'}), 404
        
        # Delete image file if exists
        if farm.image_url:
            try:
                filename = farm.image_url.split('/')[-1]
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'farms', filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"🗑️ Removed farm image: {file_path}")
            except Exception as e:
                print(f"Error deleting farm image file: {e}")
        
        # Remove image URL from database
        farm.image_url = None
        farm.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Farm image removed successfully'
        })
        
    except Exception as e:
        print(f"Error removing farm image: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/move_farm/<int:farm_id>', methods=['POST'])
@login_required
def move_farm(farm_id):
    try:
        data = request.get_json()
        new_row = data.get('grid_row')
        new_col = data.get('grid_col')
        
        if new_row is None or new_col is None:
            return jsonify({'success': False, 'error': 'Missing grid position'})
        
        # Get the farm
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify({'success': False, 'error': 'Farm not found'})
        
        # Check if target position is occupied
        existing_farm = Farm.query.filter_by(
            grid_row=new_row, 
            grid_col=new_col,
            user_id=current_user.id
        ).first()
        
        if existing_farm and existing_farm.id != farm_id:
            return jsonify({'success': False, 'error': 'Target position already occupied'})
        
        # Update farm position
        old_position = f"({farm.grid_row}, {farm.grid_col})"
        farm.grid_row = new_row
        farm.grid_col = new_col
        db.session.commit()
        
        print(f"✅ Farm moved: {farm.name} from {old_position} to ({new_row}, {new_col})")
        
        return jsonify({'success': True, 'message': 'Farm moved successfully'})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error moving farm: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/swap_farms', methods=['POST'])
@login_required
def swap_farms():
    try:
        data = request.get_json()
        farm1_id = data.get('farm1_id')
        farm2_id = data.get('farm2_id')
        farm1_new_row = data.get('farm1_new_row')
        farm1_new_col = data.get('farm1_new_col')
        farm2_new_row = data.get('farm2_new_row')
        farm2_new_col = data.get('farm2_new_col')
        
        if not all([farm1_id, farm2_id, farm1_new_row is not None, farm1_new_col is not None, 
                   farm2_new_row is not None, farm2_new_col is not None]):
            return jsonify({'success': False, 'error': 'Missing required fields'})
        
        # Get both farms
        farm1 = Farm.query.filter_by(id=farm1_id, user_id=current_user.id).first()
        farm2 = Farm.query.filter_by(id=farm2_id, user_id=current_user.id).first()
        
        if not farm1 or not farm2:
            return jsonify({'success': False, 'error': 'One or both farms not found'})
        
        # Store old positions for logging
        farm1_old = f"({farm1.grid_row}, {farm1.grid_col})"
        farm2_old = f"({farm2.grid_row}, {farm2.grid_col})"
        
        # Swap positions
        farm1.grid_row = farm1_new_row
        farm1.grid_col = farm1_new_col
        farm2.grid_row = farm2_new_row
        farm2.grid_col = farm2_new_col
        
        db.session.commit()
        
        print(f"✅ Farms swapped: {farm1.name} {farm1_old} ↔ {farm2.name} {farm2_old}")
        
        return jsonify({'success': True, 'message': 'Farms swapped successfully'})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error swapping farms: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/tree/<int:tree_id>/make_cutting', methods=['POST'])
@login_required
def make_tree_cutting(tree_id):
    """Convert a tree to a cutting and establish mother relationship"""
    try:
        data = request.get_json()
        mother_tree_id = data.get('mother_tree_id')
        cutting_notes = data.get('cutting_notes', '')
        cutting_date = data.get('cutting_date')
        
        if not mother_tree_id:
            return jsonify({'success': False, 'error': 'Mother tree ID is required'}), 400
        
        # Get the tree to convert to cutting
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        # Get the mother tree
        mother_tree = Tree.query.filter_by(id=mother_tree_id, user_id=current_user.id).first()
        if not mother_tree:
            return jsonify({'success': False, 'error': 'Mother tree not found'}), 404
        
        # Validate mother tree is in same dome
        if tree.dome_id != mother_tree.dome_id:
            return jsonify({'success': False, 'error': 'Mother and cutting must be in the same dome'}), 400
        
        # Prevent circular relationships
        if mother_tree.is_cutting():
            return jsonify({'success': False, 'error': 'Mother tree cannot be a cutting itself'}), 400
        
        # Convert tree to cutting
        tree.plant_type = 'cutting'
        tree.cutting_notes = cutting_notes
        
        # Create relationship record
        try:
            # Parse cutting date
            cutting_date_obj = None
            if cutting_date:
                cutting_date_obj = datetime.fromisoformat(cutting_date.replace('Z', '+00:00'))
            else:
                cutting_date_obj = datetime.utcnow()
            
            # Create PlantRelationship
            relationship = PlantRelationship(
                mother_tree_id=mother_tree_id,
                cutting_tree_id=tree_id,
                dome_id=tree.dome_id,
                cutting_date=cutting_date_obj,
                notes=cutting_notes
            )
            
            db.session.add(relationship)
            db.session.commit()
            
            print(f"✅ Tree {tree.name} (ID: {tree_id}) converted to cutting from mother {mother_tree.name} (ID: {mother_tree_id})")
            
            return jsonify({
                'success': True,
                'message': f'Tree "{tree.name}" is now a cutting from "{mother_tree.name}"',
                'tree': tree.to_dict(),
                'mother': mother_tree.to_dict(),
                'relationship_id': relationship.id
            })
            
        except Exception as rel_error:
            db.session.rollback()
            print(f"❌ Error creating plant relationship: {str(rel_error)}")
            return jsonify({'success': False, 'error': f'Failed to create relationship: {str(rel_error)}'}), 500
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error making tree cutting: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/tree/<int:tree_id>/remove_cutting_relationship', methods=['DELETE'])
@login_required
def remove_cutting_relationship(tree_id):
    """Remove cutting relationship and convert back to mother plant"""
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        if not tree.is_cutting():
            return jsonify({'success': False, 'error': 'Tree is not a cutting'}), 400
        
        # Find and remove relationship
        relationship = PlantRelationship.query.filter_by(cutting_tree_id=tree_id).first()
        if relationship:
            db.session.delete(relationship)
        
        # Convert back to mother plant
        tree.plant_type = 'mother'
        tree.cutting_notes = None
        
        db.session.commit()
        
        print(f"✅ Tree {tree.name} (ID: {tree_id}) converted back to mother plant")
        
        return jsonify({
            'success': True,
            'message': f'Tree "{tree.name}" is now a mother plant',
            'tree': tree.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error removing cutting relationship: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/tree/<int:tree_id>/lineage')
@login_required
def get_tree_lineage(tree_id):
    """Get complete lineage information for a tree"""
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        lineage = tree.get_plant_lineage()
        
        return jsonify({
            'success': True,
            'tree': tree.to_dict(),
            'lineage': lineage
        })
        
    except Exception as e:
        print(f"❌ Error getting tree lineage: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/dome/<int:dome_id>/mother_trees')
@login_required
def get_mother_trees(dome_id):
    """Get all mother trees in a dome for cutting creation"""
    try:
        print(f"🌳 Getting mother trees for dome {dome_id}")
        
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            print(f"❌ Dome {dome_id} not found or access denied")
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404
        
        # Get all mother trees in this dome
        mother_trees = Tree.query.filter_by(
            dome_id=dome_id,
            user_id=current_user.id,
            plant_type='mother'
        ).all()
        
        print(f"✅ Found {len(mother_trees)} mother trees in dome {dome_id}")
        
        # Convert to dict with cutting count
        mother_trees_data = []
        for tree in mother_trees:
            try:
                # Count existing cuttings from this mother
                cutting_count = PlantRelationship.query.filter_by(
                    mother_tree_id=tree.id,
                    user_id=current_user.id
                ).count()
                
                tree_dict = tree.to_dict()
                tree_dict['cutting_count'] = cutting_count
                mother_trees_data.append(tree_dict)
                
                print(f"🌳 Mother tree: {tree.name} (ID: {tree.id}) - {cutting_count} cuttings")
                
            except Exception as tree_error:
                print(f"⚠️ Error processing tree {tree.id}: {tree_error}")
                # Add tree without cutting count if there's an error
                tree_dict = tree.to_dict()
                tree_dict['cutting_count'] = 0
                mother_trees_data.append(tree_dict)
        
        return jsonify({
            'success': True,
            'mother_trees': mother_trees_data,
            'count': len(mother_trees_data)
        })
        
    except Exception as e:
        print(f"❌ Error getting mother trees: {str(e)}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/api/tree/<int:mother_id>/create_cutting', methods=['POST'])
@login_required
def create_cutting_from_mother(mother_id):
    """Create a new cutting tree from a mother plant"""
    try:
        data = request.get_json()
        cutting_name = data.get('name', '').strip()
        position_row = data.get('internal_row')
        position_col = data.get('internal_col')
        cutting_notes = data.get('cutting_notes', '')
        cutting_date = data.get('cutting_date')
        
        if not cutting_name:
            return jsonify({'success': False, 'error': 'Cutting name is required'}), 400
        
        if position_row is None or position_col is None:
            return jsonify({'success': False, 'error': 'Position is required'}), 400
        
        # Get mother tree
        mother_tree = Tree.query.filter_by(id=mother_id, user_id=current_user.id).first()
        if not mother_tree:
            return jsonify({'success': False, 'error': 'Mother tree not found'}), 404
        
        if not mother_tree.is_mother_plant():
            return jsonify({'success': False, 'error': 'Tree is not a mother plant'}), 400
        
        # Check if position is available
        existing_tree = Tree.query.filter_by(
            dome_id=mother_tree.dome_id,
            user_id=current_user.id,
            internal_row=position_row,
            internal_col=position_col
        ).first()
        
        if existing_tree:
            return jsonify({'success': False, 'error': 'Position already occupied'}), 400
        
        # Validate position is within dome bounds
        dome = mother_tree.dome
        if not (0 <= position_row < dome.internal_rows and 0 <= position_col < dome.internal_cols):
            return jsonify({'success': False, 'error': 'Position outside dome bounds'}), 400
        
        # Create cutting tree
        cutting_tree = Tree(
            name=cutting_name,
            breed=mother_tree.breed,  # Inherit breed from mother
            internal_row=position_row,
            internal_col=position_col,
            info=data.get('info', ''),
            life_days=data.get('life_days', 0),
            dome_id=mother_tree.dome_id,
            user_id=current_user.id,
            plant_type='cutting',
            cutting_notes=cutting_notes
        )
        
        db.session.add(cutting_tree)
        db.session.flush()  # Get the ID
        
        # Create relationship
        cutting_date_obj = None
        if cutting_date:
            cutting_date_obj = datetime.fromisoformat(cutting_date.replace('Z', '+00:00'))
        else:
            cutting_date_obj = datetime.utcnow()
        
        relationship = PlantRelationship(
            mother_tree_id=mother_id,
            cutting_tree_id=cutting_tree.id,
            dome_id=mother_tree.dome_id,
            cutting_date=cutting_date_obj,
            notes=cutting_notes
        )
        
        db.session.add(relationship)
        db.session.commit()
        
        print(f"✅ Created cutting '{cutting_name}' from mother '{mother_tree.name}' at ({position_row}, {position_col})")
        
        return jsonify({
            'success': True,
            'message': f'Cutting "{cutting_name}" created from mother "{mother_tree.name}"',
            'cutting': cutting_tree.to_dict(),
            'mother': mother_tree.to_dict(),
            'relationship_id': relationship.id
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating cutting: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dome/<int:dome_id>/bulk_create_cuttings', methods=['POST'])
@login_required
def bulk_create_cuttings(dome_id):
    """Create multiple cuttings from selected mother plants"""
    try:
        data = request.get_json()
        mother_ids = data.get('mother_ids', [])
        cutting_prefix = data.get('cutting_prefix', 'Cutting')
        positions = data.get('positions', [])  # List of {row, col} positions
        cutting_notes = data.get('cutting_notes', '')
        
        if not mother_ids:
            return jsonify({'success': False, 'error': 'No mother trees selected'}), 400
        
        if len(positions) < len(mother_ids):
            return jsonify({'success': False, 'error': 'Not enough positions for all cuttings'}), 400
        
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Get mother trees
        mother_trees = Tree.query.filter(
            Tree.id.in_(mother_ids),
            Tree.user_id == current_user.id,
            Tree.dome_id == dome_id,
            Tree.plant_type == 'mother'
        ).all()
        
        if len(mother_trees) != len(mother_ids):
            return jsonify({'success': False, 'error': 'Some mother trees not found'}), 404
        
        # Validate all positions are available
        for i, pos in enumerate(positions[:len(mother_trees)]):
            existing = Tree.query.filter_by(
                dome_id=dome_id,
                user_id=current_user.id,
                internal_row=pos['row'],
                internal_col=pos['col']
            ).first()
            
            if existing:
                return jsonify({
                    'success': False, 
                    'error': f'Position ({pos["row"]}, {pos["col"]}) already occupied'
                }), 400
        
        # Create cuttings
        created_cuttings = []
        created_relationships = []
        
        for i, mother in enumerate(mother_trees):
            pos = positions[i]
            cutting_name = f"{cutting_prefix} {i+1} from {mother.name}"
            
            # Create cutting
            cutting = Tree(
                name=cutting_name,
                breed=mother.breed,
                internal_row=pos['row'],
                internal_col=pos['col'],
                dome_id=dome_id,
                user_id=current_user.id,
                plant_type='cutting',
                cutting_notes=cutting_notes,
                life_days=0
            )
            
            db.session.add(cutting)
            db.session.flush()
            
            # Create relationship
            relationship = PlantRelationship(
                mother_tree_id=mother.id,
                cutting_tree_id=cutting.id,
                dome_id=dome_id,
                cutting_date=datetime.utcnow(),
                notes=cutting_notes
            )
            
            db.session.add(relationship)
            
            created_cuttings.append(cutting.to_dict())
            created_relationships.append(relationship)
        
        db.session.commit()
        
        print(f"✅ Bulk created {len(created_cuttings)} cuttings in dome {dome_id}")
        
        return jsonify({
            'success': True,
            'message': f'Created {len(created_cuttings)} cuttings successfully',
            'cuttings': created_cuttings,
            'count': len(created_cuttings)
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error bulk creating cuttings: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dome/<int:dome_id>/lineage_report')
@login_required
def get_dome_lineage_report(dome_id):
    """Get comprehensive lineage report for all plants in dome"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Get all trees in dome
        trees = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
        
        # Organize by plant type
        mother_plants = []
        cutting_plants = []
        
        for tree in trees:
            tree_data = tree.to_dict()
            tree_data['lineage'] = tree.get_plant_lineage()
            
            if tree.is_mother_plant():
                mother_plants.append(tree_data)
            elif tree.is_cutting():
                cutting_plants.append(tree_data)
        
        # Calculate statistics
        total_trees = len(trees)
        total_mothers = len(mother_plants)
        total_cuttings = len(cutting_plants)
        
        # Get breed distribution
        breed_stats = {}
        for tree in trees:
            breed = tree.breed or 'Unknown'
            if breed not in breed_stats:
                breed_stats[breed] = {'total': 0, 'mothers': 0, 'cuttings': 0}
            
            breed_stats[breed]['total'] += 1
            if tree.is_mother_plant():
                breed_stats[breed]['mothers'] += 1
            elif tree.is_cutting():
                breed_stats[breed]['cuttings'] += 1
        
        # Get most productive mothers
        productive_mothers = []
        for mother_data in mother_plants:
            cutting_count = mother_data['lineage']['cuttings']
            if cutting_count:
                productive_mothers.append({
                    'tree': mother_data,
                    'cutting_count': len(cutting_count)
                })
        
        productive_mothers.sort(key=lambda x: x['cutting_count'], reverse=True)
        
        return jsonify({
            'success': True,
            'dome': {
                'id': dome.id,
                'name': dome.name,
                'size': f"{dome.internal_rows}×{dome.internal_cols}"
            },
            'statistics': {
                'total_trees': total_trees,
                'mother_plants': total_mothers,
                'cutting_plants': total_cuttings,
                'mother_percentage': round((total_mothers / total_trees * 100) if total_trees > 0 else 0, 1),
                'cutting_percentage': round((total_cuttings / total_trees * 100) if total_trees > 0 else 0, 1)
            },
            'breed_distribution': breed_stats,
            'mother_plants': mother_plants,
            'cutting_plants': cutting_plants,
            'most_productive_mothers': productive_mothers[:5]  # Top 5
        })
        
    except Exception as e:
        print(f"❌ Error generating lineage report: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/relationship/<int:relationship_id>', methods=['DELETE'])
@login_required
def delete_plant_relationship(relationship_id):
    """Delete a specific plant relationship"""
    try:
        relationship = PlantRelationship.query.filter_by(id=relationship_id).first()
        if not relationship:
            return jsonify({'success': False, 'error': 'Relationship not found'}), 404
        
        # Verify ownership through cutting tree
        if not relationship.cutting_tree or relationship.cutting_tree.user_id != current_user.id:
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        # Convert cutting back to mother
        if relationship.cutting_tree:
            relationship.cutting_tree.plant_type = 'mother'
            relationship.cutting_tree.cutting_notes = None
        
        db.session.delete(relationship)
        db.session.commit()
        
        print(f"✅ Deleted plant relationship {relationship_id}")
        
        return jsonify({
            'success': True,
            'message': 'Relationship deleted and cutting converted to mother plant'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error deleting relationship: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/update_farm_grid_size', methods=['POST'])
@login_required
def update_farm_grid_size():
    """Update FARM grid size"""
    try:
        data = request.json
        rows = data.get('rows', 10)
        cols = data.get('cols', 10)
        
        print(f"🔧 Updating FARM grid size to {rows}x{cols}")
        
        # Validate size
        if rows < 1 or cols < 1 or rows > 100 or cols > 100:
            return jsonify(success=False, error="Grid size must be between 1x1 and 100x100"), 400
        
        # ✅ FIXED: Update FARM-specific grid settings
        success = update_grid_settings('farm', rows, cols, current_user.id)
        
        if success:
            print(f"✅ FARM grid size updated to {rows}x{cols}")
            return jsonify(success=True)
        else:
            return jsonify(success=False, error="Failed to update farm grid settings"), 500
            
    except Exception as e:
        print(f"Error updating farm grid size: {e}")
        return jsonify(success=False, error=str(e)), 500
@app.route('/debug/all_grid_settings')
@login_required
def debug_all_grid_settings():
    """Debug route to check all grid settings"""
    try:
        all_settings = GridSettings.query.filter_by(user_id=current_user.id).all()
        
        debug_info = {
            'user_id': current_user.id,
            'total_settings': len(all_settings),
            'settings': []
        }
        
        for setting in all_settings:
            debug_info['settings'].append({
                'id': setting.id,
                'type': setting.grid_type,
                'rows': setting.rows,
                'cols': setting.cols,
                'user_id': setting.user_id
            })
        
        # Also get current settings for both types
        farm_settings = get_grid_settings('farm', current_user.id)
        dome_settings = get_grid_settings('dome', current_user.id)
        
        debug_info['current_farm'] = f"{farm_settings.rows}x{farm_settings.cols}"
        debug_info['current_dome'] = f"{dome_settings.rows}x{dome_settings.cols}"
        
        return f"<pre>{json.dumps(debug_info, indent=2)}</pre>"
        
    except Exception as e:
        return f"<pre>Error: {str(e)}</pre>"
@app.route('/farm_info/<int:farm_id>')
@login_required
def farm_info(farm_id):
    """Enhanced farm information page with error handling and password protection"""
    try:
        # Get the farm and verify ownership
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            flash('Farm not found or access denied', 'error')
            return redirect(url_for('farms'))
        
        # Initialize variables
        domes = []
        total_trees = 0
        error_message = None
        
        # Try to get domes with multiple fallback strategies
        try:
            # Strategy 1: Try normal SQLAlchemy query
            domes = Dome.query.filter_by(farm_id=farm_id, user_id=current_user.id).order_by(Dome.grid_row, Dome.grid_col).all()
            print(f"✅ Strategy 1 successful: Found {len(domes)} domes for farm {farm_id}")
            
        except Exception as e1:
            print(f"⚠️ Strategy 1 failed: {e1}")
            
            try:
                # Strategy 2: Raw SQL query
                with db.engine.connect() as conn:
                    if is_postgresql():
                        # PostgreSQL version
                        result = conn.execute(text("""
                            SELECT id, name, grid_row, grid_col, internal_rows, internal_cols, 
                                   image_url, user_id, farm_id, created_at, updated_at
                            FROM dome 
                            WHERE farm_id = :farm_id AND user_id = :user_id 
                            ORDER BY grid_row, grid_col
                        """), {"farm_id": farm_id, "user_id": current_user.id})
                    else:
                        # SQLite version
                        result = conn.execute(text("""
                            SELECT id, name, grid_row, grid_col, internal_rows, internal_cols, 
                                   image_url, user_id, farm_id, created_at, updated_at
                            FROM dome 
                            WHERE farm_id = ? AND user_id = ? 
                            ORDER BY grid_row, grid_col
                        """), (farm_id, current_user.id))
                    
                    # Convert raw results to Dome-like objects
                    domes = []
                    for row in result:
                        dome = type('Dome', (), {})()  # Create a simple object
                        dome.id = row[0]
                        dome.name = row[1]
                        dome.grid_row = row[2]
                        dome.grid_col = row[3]
                        dome.internal_rows = row[4] or 5
                        dome.internal_cols = row[5] or 5
                        dome.image_url = row[6]
                        dome.user_id = row[7]
                        dome.farm_id = row[8]
                        dome.created_at = row[9]
                        dome.updated_at = row[10]
                        domes.append(dome)
                    
                    print(f"✅ Strategy 2 successful: Found {len(domes)} domes using raw SQL")
                    
            except Exception as e2:
                print(f"⚠️ Strategy 2 failed: {e2}")
                
                try:
                    # Strategy 3: Get all user's domes (fallback)
                    domes = Dome.query.filter_by(user_id=current_user.id).order_by(Dome.grid_row, Dome.grid_col).all()
                    error_message = f"Database issue detected. Showing all your domes instead of farm-specific ones. (Error: {str(e2)[:100]})"
                    print(f"✅ Strategy 3 successful: Found {len(domes)} total user domes")
                    
                except Exception as e3:
                    print(f"⚠️ Strategy 3 failed: {e3}")
                    domes = []
                    error_message = f"Unable to load domes due to database issues. Please contact support. (Error: {str(e3)[:100]})"
        
        # Calculate total trees across all domes
        for dome in domes:
            try:
                if hasattr(dome, 'id'):
                    tree_count = Tree.query.filter_by(dome_id=dome.id, user_id=current_user.id).count()
                    total_trees += tree_count
            except Exception as tree_error:
                print(f"⚠️ Error counting trees for dome {getattr(dome, 'id', 'unknown')}: {tree_error}")
                # Try raw SQL for tree count
                try:
                    with db.engine.connect() as conn:
                        if is_postgresql():
                            result = conn.execute(text("""
                                SELECT COUNT(*) as count 
                                FROM tree 
                                WHERE dome_id = :dome_id AND user_id = :user_id
                            """), {"dome_id": dome.id, "user_id": current_user.id})
                        else:
                            result = conn.execute(text("""
                                SELECT COUNT(*) as count 
                                FROM tree 
                                WHERE dome_id = ? AND user_id = ?
                            """), (dome.id, current_user.id))
                        
                        tree_count = result.fetchone()[0]
                        total_trees += tree_count
                except Exception as tree_error2:
                    print(f"⚠️ Raw SQL tree count also failed: {tree_error2}")
        
        # ✅ NEW: Get farm grid settings for proper display
        try:
            farm_grid_settings = get_grid_settings('farm', current_user.id)
            grid_rows = farm_grid_settings.rows
            grid_cols = farm_grid_settings.cols
        except Exception as grid_error:
            print(f"⚠️ Error getting grid settings: {grid_error}")
            grid_rows = 10  # Default fallback
            grid_cols = 10
        
        # ✅ NEW: Check if farm has password protection
        has_password = False
        try:
            has_password = farm.has_password() if hasattr(farm, 'has_password') else bool(getattr(farm, 'password_hash', None))
        except Exception as pwd_error:
            print(f"⚠️ Error checking farm password status: {pwd_error}")
            has_password = False
        
        # Add timestamp for cache busting
        timestamp = int(time.time())
        
        print(f"✅ Loading farm info: {farm.name} (Password protected: {has_password}, Domes: {len(domes)}, Trees: {total_trees})")
        
        return render_template('farm_info.html', 
                             farm=farm, 
                             domes=domes,
                             total_trees=total_trees,
                             grid_rows=grid_rows,
                             grid_cols=grid_cols,
                             has_password=has_password,
                             timestamp=timestamp,
                             error_message=error_message,
                             user=current_user)
        
    except Exception as e:
        print(f"❌ Critical error in farm_info route: {str(e)}")
        import traceback
        traceback.print_exc()
        
        # Try to redirect to farm domes instead
        try:
            flash(f'Error loading farm info. Redirecting to farm domes. (Error: {str(e)[:100]})', 'warning')
            return redirect(url_for('farm_domes', farm_id=farm_id))
        except:
            # Last resort: redirect to farms list
            flash('Unable to load farm information due to database issues.', 'error')
            return redirect(url_for('farms'))
@app.route('/farm/<int:farm_id>/info')
@login_required
def farm_info_simple(farm_id):
    """Simple farm info route as fallback"""
    try:
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify({'error': 'Farm not found'}), 404
        
        return f"""
        <h2>🚜 Farm: {farm.name}</h2>
        <p><strong>Position:</strong> Row {farm.grid_row}, Column {farm.grid_col}</p>
        <p><strong>Created:</strong> {farm.created_at.strftime('%Y-%m-%d %H:%M') if farm.created_at else 'Unknown'}</p>
        <hr>
        <p><a href="/farm/{farm_id}/domes">🏠 View Domes in this Farm</a></p>
        <p><a href="/farms">🚜 Back to All Farms</a></p>
        <hr>
        <p><em>This is a simplified view due to database compatibility issues.</em></p>
        """
    except Exception as e:
        return f"<h2>Error</h2><p>{str(e)}</p><p><a href='/farms'>Back to Farms</a></p>"
@app.route('/farm')
@login_required
def farm_redirect():
    """Redirect /farm to /farms for compatibility"""
    return redirect('/farms')
@app.route('/run_quick_fix')
def run_quick_fix():
    try:
        with db.engine.connect() as conn:
            # Add missing columns
            conn.execute(text("ALTER TABLE dome ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            conn.execute(text("ALTER TABLE dome ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
            conn.commit()
            return "✅ Database fixed! <a href='/farms'>Go to Farms</a>"
    except Exception as e:
        return f"Error: {e}"
@app.route('/api/dome/<int:dome_id>/grid', methods=['POST'])
@login_required
def update_dome_grid_size(dome_id):
    """Update dome grid size"""
    try:
        print(f"🔧 Grid size update request for dome {dome_id}")
        
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            print(f"❌ Dome {dome_id} not found for user {current_user.id}")
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Get request data
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Extract data (handle both grid_type and direct rows/cols)
        new_rows = data.get('rows')
        new_cols = data.get('cols')
        grid_type = data.get('grid_type', f'dome_{dome_id}')  # Optional field
        
        print(f"🔧 Request data: rows={new_rows}, cols={new_cols}, grid_type={grid_type}")
        
        # Validate input
        if not isinstance(new_rows, int) or not isinstance(new_cols, int):
            return jsonify({'success': False, 'error': 'Rows and cols must be integers'}), 400
        
        if new_rows < 1 or new_cols < 1:
            return jsonify({'success': False, 'error': 'Grid size must be at least 1x1'}), 400
        
        if new_rows > 100 or new_cols > 100:
            return jsonify({'success': False, 'error': 'Grid size cannot exceed 100x100'}), 400
        
        print(f"🔧 Updating dome {dome_id} grid size from {dome.internal_rows}x{dome.internal_cols} to {new_rows}x{new_cols}")
        
        # Check if resize would affect existing trees
        trees = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
        trees_outside_new_bounds = []
        
        for tree in trees:
            if tree.internal_row >= new_rows or tree.internal_col >= new_cols:
                trees_outside_new_bounds.append({
                    'id': tree.id,
                    'name': tree.name,
                    'position': f"({tree.internal_row}, {tree.internal_col})"
                })
        
        if trees_outside_new_bounds:
            print(f"❌ Cannot resize: {len(trees_outside_new_bounds)} trees would be outside bounds")
            return jsonify({
                'success': False, 
                'error': f'Cannot resize: {len(trees_outside_new_bounds)} trees would be outside the new grid bounds',
                'affected_trees': trees_outside_new_bounds,
                'details': f'New size: {new_rows}x{new_cols}, Affected trees at positions: {[t["position"] for t in trees_outside_new_bounds]}'
            }), 400
        
        # Check if resize would affect existing drag areas
        try:
            drag_areas = DragArea.query.filter_by(dome_id=dome_id).all()
            areas_outside_new_bounds = []
            
            for area in drag_areas:
                if (area.max_row >= new_rows or area.max_col >= new_cols or 
                    area.min_row >= new_rows or area.min_col >= new_cols):
                    areas_outside_new_bounds.append({
                        'id': area.id,
                        'name': area.name,
                        'bounds': f"({area.min_row},{area.min_col})-({area.max_row},{area.max_col})"
                    })
            
            if areas_outside_new_bounds:
                print(f"❌ Cannot resize: {len(areas_outside_new_bounds)} drag areas would be outside bounds")
                return jsonify({
                    'success': False,
                    'error': f'Cannot resize: {len(areas_outside_new_bounds)} drag areas would be outside the new grid bounds',
                    'affected_areas': areas_outside_new_bounds,
                    'details': f'New size: {new_rows}x{new_cols}, Affected areas: {[a["name"] for a in areas_outside_new_bounds]}'
                }), 400
                
        except Exception as area_check_error:
            print(f"⚠️ Warning: Could not check drag areas: {area_check_error}")
        
        # Check if resize would affect existing regular areas
        try:
            regular_areas = RegularArea.query.filter_by(dome_id=dome_id).all()
            regular_areas_outside_bounds = []
            
            for area in regular_areas:
                if (area.max_row >= new_rows or area.max_col >= new_cols or 
                    area.min_row >= new_rows or area.min_col >= new_cols):
                    regular_areas_outside_bounds.append({
                        'id': area.id,
                        'name': area.name,
                        'bounds': f"({area.min_row},{area.min_col})-({area.max_row},{area.max_col})"
                    })
            
            if regular_areas_outside_bounds:
                print(f"❌ Cannot resize: {len(regular_areas_outside_bounds)} regular areas would be outside bounds")
                return jsonify({
                    'success': False,
                    'error': f'Cannot resize: {len(regular_areas_outside_bounds)} regular areas would be outside the new grid bounds',
                    'affected_regular_areas': regular_areas_outside_bounds,
                    'details': f'New size: {new_rows}x{new_cols}, Affected areas: {[a["name"] for a in regular_areas_outside_bounds]}'
                }), 400
                
        except Exception as regular_area_check_error:
            print(f"⚠️ Warning: Could not check regular areas: {regular_area_check_error}")
        
        # Update dome grid size
        old_rows = dome.internal_rows
        old_cols = dome.internal_cols
        
        dome.internal_rows = new_rows
        dome.internal_cols = new_cols
        dome.updated_at = datetime.utcnow()
        
        # Commit changes
        db.session.commit()
        
        print(f"✅ Successfully updated dome {dome_id} grid size from {old_rows}x{old_cols} to {new_rows}x{new_cols}")
        
        return jsonify({
            'success': True,
            'message': f'Grid size updated to {new_rows}x{new_cols}',
            'dome': {
                'id': dome.id,
                'name': dome.name,
                'internal_rows': dome.internal_rows,
                'internal_cols': dome.internal_cols,
                'farm_id': dome.farm_id
            },
            'old_size': {'rows': old_rows, 'cols': old_cols},
            'new_size': {'rows': new_rows, 'cols': new_cols},
            'grid_type': grid_type
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error updating dome grid size: {str(e)}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/update_farm_name/<int:farm_id>', methods=['POST'])
@login_required
def update_farm_name(farm_id):
    """Update farm name"""
    try:
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify(success=False, error="Farm not found"), 404
        
        data = request.json
        farm.name = data.get('name', farm.name)
        farm.updated_at = datetime.utcnow()
        db.session.commit()
        
        return jsonify(success=True)
        
    except Exception as e:
        print(f"Error updating farm name: {e}")
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500

@app.route('/api/remove_breed', methods=['DELETE'])
@login_required
def remove_breed():
    """Remove a tree breed"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        breed_name = data.get('breed_name', '').strip()
        farm_id = data.get('farm_id') or data.get('dome_id')
        
        if not breed_name:
            return jsonify({'success': False, 'error': 'Breed name is required'}), 400
        
        # Get database connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if breed exists and belongs to user
        cursor.execute("""
            SELECT id FROM tree_breeds 
            WHERE LOWER(breed_name) = LOWER(?) 
            AND (user_id = ? OR user_id IS NULL)
            AND (farm_id = ? OR farm_id IS NULL)
        """, (breed_name, current_user.id, farm_id))
        
        breed_record = cursor.fetchone()
        if not breed_record:
            conn.close()
            return jsonify({'success': False, 'error': 'Breed not found or access denied'}), 404
        
        breed_id = breed_record[0]
        
        # Check if breed is being used by any trees (using correct table name 'tree')
        cursor.execute("""
            SELECT COUNT(*) FROM tree 
            WHERE LOWER(breed) = LOWER(?) AND user_id = ?
        """, (breed_name, current_user.id))
        
        tree_count = cursor.fetchone()[0]
        
        if tree_count > 0:
            conn.close()
            return jsonify({
                'success': False, 
                'error': f'Cannot delete breed "{breed_name}" - it is used by {tree_count} tree(s)'
            }), 400
        
        # Delete the breed (only if it belongs to the user)
        cursor.execute("""
            DELETE FROM tree_breeds 
            WHERE id = ? AND (user_id = ? OR user_id IS NULL)
        """, (breed_id, current_user.id))
        
        conn.commit()
        conn.close()
        
        print(f"✅ Removed breed: {breed_name} (ID: {breed_id}) for user {current_user.id}")
        
        return jsonify({
            'success': True, 
            'message': f'Breed "{breed_name}" removed successfully'
        })
        
    except sqlite3.Error as e:
        print(f"❌ Database error removing breed: {e}")
        return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500
    except Exception as e:
        print(f"❌ Error removing breed: {e}")
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500

@app.route('/api/get_breeds', methods=['GET'])
@login_required
def get_breeds():
    """Get all tree breeds for current user"""
    try:
        # Get farm_id from query parameters
        farm_id = request.args.get('farm_id') or request.args.get('dome_id')
        
        # Get database connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get all breeds for this user and farm (including global breeds)
        cursor.execute("""
            SELECT DISTINCT breed_name FROM tree_breeds 
            WHERE (user_id = ? OR user_id IS NULL)
            AND (farm_id = ? OR farm_id IS NULL)
            ORDER BY breed_name ASC
        """, (current_user.id, farm_id))
        
        breeds = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        print(f"✅ Retrieved {len(breeds)} breeds for user {current_user.id}, farm {farm_id}")
        
        return jsonify({
            'success': True, 
            'breeds': breeds,
            'count': len(breeds)
        })
        
    except sqlite3.Error as e:
        print(f"❌ Database error getting breeds: {e}")
        return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500
    except Exception as e:
        print(f"❌ Error getting breeds: {e}")
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500

@app.route('/api/sync_breeds', methods=['POST'])
@login_required
def sync_breeds():
    """Sync breeds from frontend to backend"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        breeds = data.get('breeds', [])
        farm_id = data.get('farm_id') or data.get('dome_id')
        
        if not isinstance(breeds, list):
            return jsonify({'success': False, 'error': 'Breeds must be a list'}), 400
        
        # Get database connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Clear existing user breeds for this farm
        cursor.execute("""
            DELETE FROM tree_breeds 
            WHERE user_id = ? AND (farm_id = ? OR farm_id IS NULL)
        """, (current_user.id, farm_id))
        
        # Insert new breeds
        added_count = 0
        for breed_name in breeds:
            if breed_name and breed_name.strip():
                try:
                    cursor.execute("""
                        INSERT INTO tree_breeds (breed_name, farm_id, user_id, created_at) 
                        VALUES (?, ?, ?, ?)
                    """, (breed_name.strip(), farm_id, current_user.id, datetime.now().isoformat()))
                    added_count += 1
                except sqlite3.IntegrityError:
                    # Skip duplicates
                    continue
        
        conn.commit()
        conn.close()
        
        print(f"✅ Synced {added_count} breeds for user {current_user.id}, farm {farm_id}")
        
        return jsonify({
            'success': True, 
            'message': f'Synced {added_count} breeds successfully',
            'synced_count': added_count
        })
        
    except sqlite3.Error as e:
        print(f"❌ Database error syncing breeds: {e}")
        return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500
    except Exception as e:
        print(f"❌ Error syncing breeds: {e}")
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500

@app.route('/api/add_breed', methods=['POST'])
@login_required
def add_breed():
    """Add a new tree breed"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        breed_name = data.get('breed_name', '').strip()
        farm_id = data.get('farm_id') or data.get('dome_id')
        
        # Validate breed name
        if not breed_name:
            return jsonify({'success': False, 'error': 'Breed name is required'}), 400
        
        if len(breed_name) > 50:
            return jsonify({'success': False, 'error': 'Breed name too long (max 50 characters)'}), 400
        
        # Get database connection
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if breed already exists for this user/farm (case-insensitive)
        cursor.execute("""
            SELECT id FROM tree_breeds 
            WHERE LOWER(breed_name) = LOWER(?) 
            AND (user_id = ? OR user_id IS NULL)
            AND (farm_id = ? OR farm_id IS NULL)
        """, (breed_name, current_user.id, farm_id))
        
        existing_breed = cursor.fetchone()
        if existing_breed:
            conn.close()
            return jsonify({'success': False, 'error': 'Breed already exists'}), 400
        
        # Insert new breed
        cursor.execute("""
            INSERT INTO tree_breeds (breed_name, farm_id, user_id, created_at) 
            VALUES (?, ?, ?, ?)
        """, (breed_name, farm_id, current_user.id, datetime.now().isoformat()))
        
        breed_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        print(f"✅ Added new breed: {breed_name} (ID: {breed_id}) for user {current_user.id}")
        
        return jsonify({
            'success': True, 
            'message': f'Breed "{breed_name}" added successfully',
            'breed_id': breed_id,
            'breed_name': breed_name
        })
        
    except sqlite3.Error as e:
        print(f"❌ Database error adding breed: {e}")
        return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500
    except Exception as e:
        print(f"❌ Error adding breed: {e}")
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500
def get_db_connection():
    """Get database connection for instance/db.sqlite3"""
    try:
        # Get the instance folder path
        instance_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instance')
        db_path = os.path.join(instance_path, 'db.sqlite3')
        
        # Create instance directory if it doesn't exist
        os.makedirs(instance_path, exist_ok=True)
        
        # Connect to database
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        return conn
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        raise
@app.route('/delete_farm/<int:farm_id>', methods=['DELETE'])
@login_required
def delete_farm(farm_id):
    try:
        # Get the farm
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify({'success': False, 'error': 'Farm not found'})
        
        farm_name = farm.name
        
        # Delete associated domes first
        domes = Dome.query.filter_by(farm_id=farm_id).all()
        dome_count = len(domes)
        for dome in domes:
            # Delete trees in each dome
            trees = Tree.query.filter_by(dome_id=dome.id).all()
            for tree in trees:
                db.session.delete(tree)
            # Delete the dome
            db.session.delete(dome)
        
        # Delete the farm
        db.session.delete(farm)
        db.session.commit()
        
        print(f"✅ Farm deleted: {farm_name} (with {dome_count} domes)")
        
        return jsonify({'success': True, 'message': 'Farm deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error deleting farm: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/upload_farm_image/<int:farm_id>', methods=['POST'])
@login_required
def upload_farm_image(farm_id):
    try:
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify({'success': False, 'error': 'Farm not found'})
        
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image file'})
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        # Save image as base64 data URL
        image_url = save_image_to_database(file, 'farm', farm_id)
        
        if image_url:
            farm.image_url = image_url
            db.session.commit()
            
            print(f"✅ Farm {farm_id} image uploaded successfully, size: {len(image_url)} chars")
            
            return jsonify({
                'success': True, 
                'message': 'Image uploaded successfully',
                'image_url': image_url
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to process image'})
            
    except Exception as e:
        print(f"❌ Farm image upload error: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})
@app.route('/')
@login_required
def index():
    """Redirect to farms instead of global domes"""
    return redirect(url_for('farms'))
@app.route('/update_dome_grid/<int:dome_id>', methods=['POST'])
@login_required
def update_dome_grid(dome_id):
    """Update dome internal grid size"""
    try:
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        data = request.get_json()
        new_rows = data.get('rows')
        new_cols = data.get('cols')
        
        print(f"🔧 Updating dome {dome_id} internal grid size to {new_rows}x{new_cols}")
        
        # Validation
        if not new_rows or not new_cols:
            return jsonify({'success': False, 'error': 'Rows and columns are required'}), 400
        
        try:
            new_rows = int(new_rows)
            new_cols = int(new_cols)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid grid size values'}), 400
        
        # Validate size bounds
        if new_rows < 1 or new_cols < 1 or new_rows > 100 or new_cols > 100:
            return jsonify({'success': False, 'error': 'Grid size must be between 1x1 and 100x100'}), 400
        
        # Check if shrinking would affect existing trees
        if new_rows < (dome.internal_rows or 5) or new_cols < (dome.internal_cols or 5):
            affected_trees = Tree.query.filter(
                Tree.dome_id == dome_id,
                Tree.user_id == current_user.id,
                (Tree.internal_row >= new_rows) | (Tree.internal_col >= new_cols)
            ).all()
            
            if affected_trees:
                tree_names = [tree.name for tree in affected_trees]
                return jsonify({
                    'success': False, 
                    'error': f'Cannot shrink grid. Trees would be affected: {", ".join(tree_names)}'
                }), 400
        
        # Update dome internal grid size
        dome.internal_rows = new_rows
        dome.internal_cols = new_cols
        dome.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        print(f"✅ Dome {dome_id} internal grid size updated to {new_rows}x{new_cols}")
        
        return jsonify({
            'success': True,
            'message': f'Dome grid updated to {new_rows}x{new_cols}',
            'dome': {
                'id': dome.id,
                'internal_rows': dome.internal_rows,
                'internal_cols': dome.internal_cols
            }
        })
        
    except Exception as e:
        print(f"❌ Error updating dome grid size: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/farm/<int:farm_id>/domes')
@login_required
def farm_domes(farm_id):
    try:
        print(f"🚜 Loading domes for farm {farm_id}")
        
        # Get the farm
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            print(f"❌ Farm {farm_id} not found")
            flash('Farm not found', 'error')
            return redirect(url_for('farms'))
        
        # ✅ FIXED: Get farm-specific dome grid settings with 5x5 default
        grid_settings = get_grid_settings('dome', current_user.id, farm_id)
        
        # Ensure default is 5x5 for farm domes
        if not hasattr(grid_settings, 'rows') or grid_settings.rows is None:
            grid_settings.rows = 5
        if not hasattr(grid_settings, 'cols') or grid_settings.cols is None:
            grid_settings.cols = 5
        
        print(f"📏 Farm {farm_id} dome grid settings: {grid_settings.rows}x{grid_settings.cols}")
        
        # Get domes for this specific farm ONLY
        domes = Dome.query.filter_by(farm_id=farm_id, user_id=current_user.id).all()
        
        print(f"✅ Found {len(domes)} domes for farm {farm.name} ({grid_settings.rows}x{grid_settings.cols} grid)")
        
        return render_template('dome.html', 
                             domes=domes,
                             grid_rows=grid_settings.rows,
                             grid_cols=grid_settings.cols,
                             farm_id=farm_id,
                             farm_name=farm.name,
                             page_title=f"{farm.name} - Domes",
                             timestamp=int(time.time()),
                             user=current_user)
                             
    except Exception as e:
        print(f"❌ Error loading farm domes: {str(e)}")
        flash('Error loading farm domes', 'error')
        return redirect(url_for('farms'))
@app.route('/domes')
@login_required
def domes():
    """Redirect to farms - no more global domes"""
    flash('Please select a farm to view its domes', 'info')
    return redirect(url_for('farms'))

# ============= UPDATED GRID SETTINGS HELPER =============

def get_grid_settings(grid_type='dome', user_id=None, farm_id=None):
    """Get grid settings for specific type, user, and optionally farm"""
    try:
        # If it's a farm dome view, use farm-specific dome settings
        if grid_type == 'dome' and farm_id:
            grid_type_key = f'farm_{farm_id}_dome'
        else:
            grid_type_key = grid_type
            
        settings = GridSettings.query.filter_by(
            grid_type=grid_type_key,
            user_id=user_id
        ).first()
        
        if not settings:
            # ✅ FIXED: Better defaults for different grid types
            if grid_type == 'farm':
                default_rows, default_cols = 10, 10  # Farm layout grid
            elif farm_id:  # Farm-specific dome settings
                default_rows, default_cols = 5, 5   # Fixed 5x5 for farm domes
            else:  # Global dome settings
                default_rows, default_cols = 10, 10  # Larger default for global domes
            
            settings = GridSettings(
                rows=default_rows,
                cols=default_cols,
                grid_type=grid_type_key,
                user_id=user_id
            )
            db.session.add(settings)
            
            try:
                db.session.commit()
                print(f"✅ Created default {grid_type_key} settings: {default_rows}x{default_cols}")
            except Exception as commit_error:
                db.session.rollback()
                print(f"⚠️ Failed to create grid settings: {commit_error}")
                # Return a default object instead
                return type('obj', (object,), {
                    'rows': default_rows,
                    'cols': default_cols,
                    'grid_type': grid_type_key
                })
            
        return settings
    except Exception as e:
        print(f"Error getting grid settings: {e}")
        # Return default object
        if grid_type == 'farm':
            default_rows, default_cols = 10, 10
        elif farm_id:
            default_rows, default_cols = 5, 5
        else:
            default_rows, default_cols = 10, 10
            
        return type('obj', (object,), {
            'rows': default_rows,
            'cols': default_cols,
            'grid_type': grid_type_key if 'grid_type_key' in locals() else grid_type
        })
@app.route('/migrate_orphan_domes')
@login_required
def migrate_orphan_domes():
    """One-time migration to assign orphan domes to farms or delete them"""
    try:
        # Find domes without farm_id
        orphan_domes = Dome.query.filter_by(farm_id=None, user_id=current_user.id).all()
        
        if not orphan_domes:
            return jsonify({
                'success': True,
                'message': 'No orphan domes found - all domes belong to farms'
            })
        
        # Get user's first farm or create one
        first_farm = Farm.query.filter_by(user_id=current_user.id).first()
        
        if not first_farm:
            # Create a default farm
            first_farm = Farm(
                name="Default Farm",
                grid_row=0,
                grid_col=0,
                user_id=current_user.id
            )
            db.session.add(first_farm)
            db.session.commit()
            print(f"✅ Created default farm for user {current_user.id}")
        
        # Assign orphan domes to the first farm
        migrated_count = 0
        for dome in orphan_domes:
            dome.farm_id = first_farm.id
            migrated_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': f'Migrated {migrated_count} orphan domes to farm "{first_farm.name}"'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error migrating orphan domes: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/dome_context/<int:farm_id>')
@login_required
def dome_context_info(farm_id):
    try:
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify({'success': False, 'error': 'Farm not found'})
        
        domes = Dome.query.filter_by(farm_id=farm_id, user_id=current_user.id).all()
        
        dome_positions = []
        for dome in domes:
            dome_positions.append({
                'id': dome.id,
                'name': dome.name,
                'row': dome.grid_row,
                'col': dome.grid_col,
                'farm_id': dome.farm_id
            })
        
        return jsonify({
            'success': True,
            'farm': {
                'id': farm.id,
                'name': farm.name
            },
            'grid_size': '5x5',
            'dome_count': len(domes),
            'domes': dome_positions
        })
        
    except Exception as e:
        print(f"❌ Error getting dome context: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
@login_required
def add_dome():
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        grid_row = data.get('grid_row')
        grid_col = data.get('grid_col')
        farm_id = data.get('farm_id')  # This comes from the frontend
        
        # Validation
        if not name:
            return jsonify({'success': False, 'error': 'Dome name is required'})
        
        if grid_row is None or grid_col is None:
            return jsonify({'success': False, 'error': 'Grid position is required'})
        
        # ✅ FIXED: Check for position conflicts within the specific farm context
        if farm_id:
            # When viewing a specific farm, only check conflicts within that farm
            existing_dome = Dome.query.filter_by(
                grid_row=grid_row, 
                grid_col=grid_col, 
                farm_id=farm_id,
                user_id=current_user.id
            ).first()
        else:
            # When viewing all domes (no farm_id), check conflicts in user's default/no-farm domes
            existing_dome = Dome.query.filter_by(
                grid_row=grid_row, 
                grid_col=grid_col, 
                farm_id=None,  # Default to no farm
                user_id=current_user.id
            ).first()
        
        if existing_dome:
            return jsonify({'success': False, 'error': 'Position occupied'})
        
        # Create new dome
        new_dome = Dome(
            name=name,
            grid_row=grid_row,
            grid_col=grid_col,
            farm_id=farm_id,  # Assign to the specific farm or None
            user_id=current_user.id
        )
        
        db.session.add(new_dome)
        db.session.commit()
        
        return jsonify({'success': True, 'dome_id': new_dome.id})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error creating dome: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/create_farm', methods=['POST'])
@login_required
def create_farm():
    """Create a new farm with password protection"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        password = data.get('password', '').strip()
        grid_row = data.get('grid_row')
        grid_col = data.get('grid_col')
        
        print(f"🌱 Creating farm: {name} at ({grid_row}, {grid_col}) with password: {'Yes' if password else 'No'}")
        
        # Validation
        if not name:
            return jsonify({'success': False, 'error': 'Farm name is required'}), 400
        
        if grid_row is None or grid_col is None:
            return jsonify({'success': False, 'error': 'Grid position is required'}), 400
        
        if not password:
            return jsonify({'success': False, 'error': 'Farm password is required'}), 400
        
        if len(password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters long'}), 400
        
        # Check if position is already occupied
        existing_farm = Farm.query.filter_by(
            grid_row=grid_row,
            grid_col=grid_col,
            user_id=current_user.id
        ).first()
        
        if existing_farm:
            return jsonify({'success': False, 'error': 'Position already occupied'}), 400
        
        # Check if farm name already exists for this user
        existing_name = Farm.query.filter_by(
            name=name,
            user_id=current_user.id
        ).first()
        
        if existing_name:
            return jsonify({'success': False, 'error': 'Farm name already exists'}), 400
        
        # Create new farm
        new_farm = Farm(
            name=name,
            grid_row=grid_row,
            grid_col=grid_col,
            user_id=current_user.id
        )
        
        # Set password
        new_farm.set_password(password)
        
        db.session.add(new_farm)
        db.session.commit()
        
        print(f"✅ Farm created successfully: {name} (ID: {new_farm.id})")
        
        return jsonify({
            'success': True,
            'message': 'Farm created successfully!',
            'farm': {
                'id': new_farm.id,
                'name': new_farm.name,
                'grid_row': new_farm.grid_row,
                'grid_col': new_farm.grid_col,
                'has_password': new_farm.has_password()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating farm: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/verify_farm_password/<int:farm_id>', methods=['POST'])
@login_required
def verify_farm_password(farm_id):
    """Verify farm password before accessing domes"""
    try:
        data = request.get_json()
        password = data.get('password', '')
        
        print(f"🔐 Password verification for farm ID: {farm_id}")
        
        # Get the farm
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify({'success': False, 'error': 'Farm not found'}), 404
        
        # Check password
        if farm.check_password(password):
            print(f"✅ Password correct for farm: {farm.name}")
            
            # Store verification in session (optional - for additional security)
            from flask import session
            if 'verified_farms' not in session:
                session['verified_farms'] = []
            
            if farm_id not in session['verified_farms']:
                session['verified_farms'].append(farm_id)
            
            return jsonify({
                'success': True,
                'message': 'Password verified successfully',
                'farm_name': farm.name
            })
        else:
            print(f"❌ Incorrect password for farm: {farm.name}")
            return jsonify({'success': False, 'error': 'Incorrect password'}), 401
            
    except Exception as e:
        print(f"❌ Error verifying farm password: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/request_farm_password_reset', methods=['POST'])
@login_required
def request_farm_password_reset():
    """Request password reset for a specific farm"""
    try:
        data = request.get_json()
        farm_id = data.get('farm_id')
        
        # ✅ FIXED: Get email from logged-in user instead of request
        user_email = current_user.email
        
        print(f"🔑 Farm password reset request for farm ID: {farm_id}, user: {current_user.username}, email: {user_email}")
        
        if not farm_id:
            return jsonify({'success': False, 'error': 'Farm ID is required'}), 400
        
        if not user_email:
            return jsonify({'success': False, 'error': 'User email not found. Please contact support.'}), 400
        
        # Get the farm
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify({'success': False, 'error': 'Farm not found or access denied'}), 404
        
        try:
            # Generate reset token
            token = farm.generate_reset_token()
            db.session.commit()
            
            # Send reset email using user's registered email
            send_farm_reset_email(user_email, token, farm.name, farm.id, current_user.username)
            print(f"✅ Farm password reset email sent to: {user_email}")
            
            return jsonify({
                'success': True,
                'message': f'Password reset instructions have been sent to your registered email ({user_email})'
            })
            
        except Exception as e:
            print(f"❌ Failed to send farm reset email: {e}")
            
            # Fallback for development
            if not os.getenv('RENDER'):
                reset_url = f"{request.url_root}reset_farm_password?token={token}&farm_id={farm_id}"
                print(f"🔗 Development Farm Reset URL: {reset_url}")
                return jsonify({
                    'success': True,
                    'message': 'Email service unavailable. Check console for reset link (development mode).',
                    'dev_reset_url': reset_url  # Include URL in response for development
                })
            else:
                return jsonify({
                    'success': False,
                    'error': 'Failed to send reset email. Please try again later.'
                }), 500
                
    except Exception as e:
        print(f"❌ Farm password reset request error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/reset_farm_password', methods=['GET', 'POST'])
def reset_farm_password():
    """Reset farm password with token"""
    if request.method == 'POST':
        try:
            # Handle both JSON and form data
            if request.is_json:
                data = request.get_json()
                token = data.get('token')
                farm_id = data.get('farm_id')
                new_password = data.get('new_password')
            else:
                # Handle regular form submission
                token = request.form.get('token')
                farm_id = request.form.get('farm_id')
                new_password = request.form.get('password')
            
            print(f"🔐 Farm password reset attempt for farm ID: {farm_id}")
            
            if not all([token, farm_id, new_password]):
                if request.is_json:
                    return jsonify({'success': False, 'error': 'Token, farm ID, and new password are required'}), 400
                else:
                    return render_template('auth/reset_farm_password.html', 
                                         token=token, farm_id=farm_id, 
                                         error='All fields are required')
            
            if len(new_password) < 6:
                error_msg = 'Password must be at least 6 characters long'
                if request.is_json:
                    return jsonify({'success': False, 'error': error_msg}), 400
                else:
                    return render_template('auth/reset_farm_password.html', 
                                         token=token, farm_id=farm_id, 
                                         error=error_msg)
            
            # Find farm with this token
            farm = Farm.query.filter_by(id=farm_id, reset_token=token).first()
            if not farm:
                error_msg = 'Invalid or expired reset token'
                if request.is_json:
                    return jsonify({'success': False, 'error': error_msg}), 400
                else:
                    return render_template('auth/reset_farm_password.html', 
                                         error=error_msg)
            
            if not farm.verify_reset_token(token):
                error_msg = 'Invalid or expired reset token'
                if request.is_json:
                    return jsonify({'success': False, 'error': error_msg}), 400
                else:
                    return render_template('auth/reset_farm_password.html', 
                                         error=error_msg)
            
            # Update password
            farm.set_password(new_password)
            farm.clear_reset_token()
            db.session.commit()
            
            print(f"✅ Farm password reset successful for: {farm.name}")
            
            if request.is_json:
                return jsonify({
                    'success': True,
                    'message': 'Farm password reset successful!',
                    'farm_name': farm.name
                })
            else:
                return render_template('auth/reset_farm_password.html', 
                                     success='Password reset successful! You can now use your new password.')
            
        except Exception as e:
            print(f"❌ Farm password reset error: {e}")
            db.session.rollback()
            error_msg = str(e)
            if request.is_json:
                return jsonify({'success': False, 'error': error_msg}), 500
            else:
                return render_template('auth/reset_farm_password.html', 
                                     error='An error occurred. Please try again.')
    
    # GET request - show reset form
    token = request.args.get('token')
    farm_id = request.args.get('farm_id')
    
    if not token or not farm_id:
        return render_template('auth/reset_farm_password.html', 
                             error='Invalid reset link. Please request a new password reset.')
    
    # Verify token
    farm = Farm.query.filter_by(id=farm_id, reset_token=token).first()
    if not farm or not farm.verify_reset_token(token):
        return render_template('auth/reset_farm_password.html', 
                             error='Invalid or expired reset token. Please request a new password reset.')
    
    return render_template('auth/reset_farm_password.html', 
                         token=token, 
                         farm_id=farm_id, 
                         farm_name=farm.name)

# ============= ENHANCED EMAIL FUNCTION FOR FARM RESET =============
@app.route('/api/farm/<int:farm_id>/breeds', methods=['GET', 'POST'])
@login_required
def manage_farm_breeds(farm_id):
    """Manage tree breeds for a specific farm"""
    try:
        # Verify farm ownership
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify({'success': False, 'error': 'Farm not found or access denied'}), 404
        
        if request.method == 'GET':
            return handle_get_breeds(farm_id)
        elif request.method == 'POST':
            return handle_post_breeds(farm_id)
            
    except Exception as e:
        print(f"❌ Error managing farm breeds: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

def handle_get_breeds(farm_id):
    """Handle GET request for farm breeds"""
    try:
        # Get active breeds for this farm
        breeds = TreeBreed.query.filter_by(
            farm_id=farm_id, 
            user_id=current_user.id,
            is_active=True
        ).order_by(TreeBreed.name).all()
        
        # If no breeds exist, create default ones
        if not breeds:
            print(f"ℹ️ No breeds found for farm {farm_id}, creating defaults...")
            breeds = create_default_breeds_for_farm(farm_id)
        
        # Convert to the format expected by frontend
        breed_data = []
        for breed in breeds:
            try:
                if hasattr(breed, 'to_dict'):
                    breed_dict = breed.to_dict()
                else:
                    breed_dict = {
                        'id': breed.id,
                        'name': breed.name,
                        'description': getattr(breed, 'description', ''),
                        'farm_id': breed.farm_id,
                        'user_id': breed.user_id,
                        'is_active': getattr(breed, 'is_active', True),
                        'created_at': breed.created_at.isoformat() if breed.created_at else None
                    }
                breed_data.append(breed_dict)
            except Exception as breed_error:
                print(f"⚠️ Error processing breed {breed.id}: {breed_error}")
                # Add minimal breed data
                breed_data.append({
                    'id': breed.id,
                    'name': breed.name,
                    'description': '',
                    'farm_id': farm_id,
                    'is_active': True
                })
        
        # Extract just the names for backward compatibility
        breed_names = [breed['name'] for breed in breed_data]
        
        print(f"📦 Loading {len(breed_names)} breeds for farm {farm_id}: {breed_names}")
        
        return jsonify({
            'success': True,
            'breeds': breed_data,  # Full breed objects
            'breed_names': breed_names,  # Just names for backward compatibility
            'count': len(breed_data)
        })
        
    except Exception as e:
        print(f"❌ Error getting breeds: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def handle_post_breeds(farm_id):
    """Handle POST request for farm breeds"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Handle single breed creation
        if 'name' in data:
            return create_single_breed(farm_id, data)
        
        # Handle multiple breeds (bulk operation)
        elif 'breeds' in data:
            return handle_bulk_breeds(farm_id, data['breeds'])
        
        else:
            return jsonify({'success': False, 'error': 'Invalid request format'}), 400
            
    except Exception as e:
        print(f"❌ Error in POST breeds: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

def create_single_breed(farm_id, data):
    """Create a single breed"""
    try:
        breed_name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        
        # Validation
        if not breed_name:
            return jsonify({'success': False, 'error': 'Breed name is required'}), 400
        
        if len(breed_name) < 2:
            return jsonify({'success': False, 'error': 'Breed name must be at least 2 characters'}), 400
        
        if len(breed_name) > 100:
            return jsonify({'success': False, 'error': 'Breed name too long (max 100 characters)'}), 400
        
        # Check for invalid characters
        import re
        if not re.match(r'^[a-zA-Z0-9\s\-_\.]+$', breed_name):
            return jsonify({'success': False, 'error': 'Breed name contains invalid characters'}), 400
        
        # Check if breed already exists (case-insensitive)
        existing_breed = TreeBreed.query.filter(
            TreeBreed.farm_id == farm_id,
            TreeBreed.user_id == current_user.id,
            TreeBreed.name.ilike(breed_name),
            TreeBreed.is_active == True
        ).first()
        
        if existing_breed:
            return jsonify({'success': False, 'error': 'Breed already exists'}), 409
        
        # Create new breed
        new_breed = TreeBreed(
            name=breed_name,
            description=description,
            farm_id=farm_id,
            user_id=current_user.id,
            is_active=True,
            created_at=datetime.utcnow()
        )
        
        db.session.add(new_breed)
        db.session.commit()
        
        print(f"✅ Created new breed: {breed_name} for farm {farm_id}")
        
        # Return breed data
        breed_dict = {
            'id': new_breed.id,
            'name': new_breed.name,
            'description': new_breed.description,
            'farm_id': new_breed.farm_id,
            'user_id': new_breed.user_id,
            'is_active': new_breed.is_active,
            'created_at': new_breed.created_at.isoformat()
        }
        
        return jsonify({
            'success': True,
            'breed': breed_dict,
            'message': f'Breed "{breed_name}" created successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating single breed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def handle_bulk_breeds(farm_id, breeds_list):
    """Handle bulk breed operations (DANGEROUS - use with caution)"""
    try:
        if not isinstance(breeds_list, list):
            return jsonify({'success': False, 'error': 'Breeds must be a list'}), 400
        
        print(f"💾 Bulk saving {len(breeds_list)} breeds for farm {farm_id}: {breeds_list}")
        
        # ⚠️ WARNING: This will replace ALL breeds for the farm
        # Only use this for initial setup or complete replacement
        
        # Get existing breeds to check for usage
        existing_breeds = TreeBreed.query.filter_by(
            farm_id=farm_id, 
            user_id=current_user.id,
            is_active=True
        ).all()
        
        # Check if any existing breeds are being used by trees
        breeds_in_use = []
        for breed in existing_breeds:
            tree_count = Tree.query.join(Dome).filter(
                Tree.breed == breed.name,
                Tree.user_id == current_user.id,
                Dome.farm_id == farm_id
            ).count()
            
            if tree_count > 0:
                breeds_in_use.append(f"{breed.name} ({tree_count} trees)")
        
        if breeds_in_use:
            return jsonify({
                'success': False,
                'error': f'Cannot replace breeds - some are in use: {", ".join(breeds_in_use)}'
            }), 409
        
        # Soft delete existing breeds (set is_active = False)
        for breed in existing_breeds:
            breed.is_active = False
            breed.updated_at = datetime.utcnow()
        
        # Add new breeds
        added_count = 0
        created_breeds = []
        
        for breed_name in breeds_list:
            if breed_name and len(breed_name.strip()) > 0:
                clean_name = breed_name.strip()[:100]  # Limit to 100 chars
                
                # Check if this breed name already exists in the new list
                if clean_name not in [b['name'] for b in created_breeds]:
                    new_breed = TreeBreed(
                        name=clean_name,
                        description=f'{clean_name} tree breed',
                        farm_id=farm_id,
                        user_id=current_user.id,
                        is_active=True,
                        created_at=datetime.utcnow()
                    )
                    db.session.add(new_breed)
                    db.session.flush()  # Get the ID
                    
                    created_breeds.append({
                        'id': new_breed.id,
                        'name': new_breed.name,
                        'description': new_breed.description
                    })
                    added_count += 1
        
        db.session.commit()
        print(f"✅ Successfully bulk saved {added_count} breeds for farm {farm_id}")
        
        return jsonify({
            'success': True,
            'message': f'Bulk saved {added_count} breeds successfully',
            'created_breeds': created_breeds,
            'count': added_count
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in bulk breed operation: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def create_default_breeds_for_farm(farm_id):
    """Create default breeds for a farm"""
    try:
        default_breed_data = [
            ('Apple', 'Sweet and crispy fruit tree'),
            ('Orange', 'Citrus fruit tree with vitamin C'),
            ('Mango', 'Tropical fruit tree with sweet flesh'),
            ('Banana', 'Tropical fruit tree with potassium-rich fruit'),
            ('Coconut', 'Palm tree with versatile coconut fruit'),
            ('Avocado', 'Nutrient-rich fruit tree')
        ]
        
        created_breeds = []
        for breed_name, description in default_breed_data:
            # Check if breed already exists
            existing = TreeBreed.query.filter_by(
                farm_id=farm_id,
                user_id=current_user.id,
                name=breed_name,
                is_active=True
            ).first()
            
            if not existing:
                new_breed = TreeBreed(
                    name=breed_name,
                    description=description,
                    farm_id=farm_id,
                    user_id=current_user.id,
                    is_active=True,
                    created_at=datetime.utcnow()
                )
                db.session.add(new_breed)
                created_breeds.append(new_breed)
        
        if created_breeds:
            db.session.commit()
            print(f"✅ Created {len(created_breeds)} default breeds for farm {farm_id}")
        
        return created_breeds
        
    except Exception as e:
        print(f"❌ Error creating default breeds: {e}")
        db.session.rollback()
        return []

# Additional route for deleting individual breeds
@app.route('/api/farm/<int:farm_id>/breeds/<int:breed_id>', methods=['DELETE'])
@login_required
def delete_farm_breed(farm_id, breed_id):
    """Delete a specific breed (soft delete)"""
    try:
        # Verify farm ownership
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify({'success': False, 'error': 'Farm not found or access denied'}), 404
        
        # Get breed
        breed = TreeBreed.query.filter_by(
            id=breed_id,
            farm_id=farm_id,
            user_id=current_user.id,
            is_active=True
        ).first()
        
        if not breed:
            return jsonify({'success': False, 'error': 'Breed not found'}), 404
        
        # Check if breed is being used by any trees
        tree_count = Tree.query.join(Dome).filter(
            Tree.breed == breed.name,
            Tree.user_id == current_user.id,
            Dome.farm_id == farm_id
        ).count()
        
        if tree_count > 0:
            return jsonify({
                'success': False,
                'error': f'Cannot delete breed "{breed.name}" - it is being used by {tree_count} trees'
            }), 409
        
        # Soft delete
        breed.is_active = False
        breed.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        print(f"✅ Soft deleted breed: {breed.name} from farm {farm_id}")
        
        return jsonify({
            'success': True,
            'message': f'Breed "{breed.name}" deleted successfully'
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error deleting breed: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def send_farm_reset_email(email, token, farm_name, farm_id, username):
    """Send farm password reset email"""
    try:
        reset_url = f"{request.url_root}reset_farm_password?token={token}&farm_id={farm_id}"
        
        msg = Message(
            subject=f"🔐 Farm Password Reset - {farm_name}",
            recipients=[email],
            sender=os.getenv('MAIL_USERNAME'),
            html=f"""
            <html>
            <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin-bottom: 20px;">
                    <h2 style="color: #28a745; margin: 0;">🌱 Farm Password Reset</h2>
                </div>
                
                <p>Hello <strong>{username}</strong>,</p>
                
                <p>You have requested to reset the password for your farm:</p>
                
                <div style="background: #e9ecef; padding: 15px; border-radius: 6px; margin: 20px 0;">
                    <p style="margin: 0;"><strong>Farm Name:</strong> {farm_name}</p>
                    <p style="margin: 5px 0 0 0;"><strong>Account:</strong> {email}</p>
                </div>
                
                <p>Click the button below to reset your farm password:</p>
                
                <div style="text-align: center; margin: 30px 0;">
                    <a href="{reset_url}" 
                       style="background: #28a745; color: white; padding: 12px 30px; text-decoration: none; border-radius: 6px; font-weight: bold; display: inline-block;">
                        Reset Farm Password
                    </a>
                </div>
                
                <p>Or copy and paste this link into your browser:</p>
                <p style="word-break: break-all; background: #f8f9fa; padding: 10px; border-radius: 4px; font-family: monospace;">
                    {reset_url}
                </p>
                
                <div style="background: #fff3cd; padding: 15px; border-radius: 6px; margin: 20px 0;">
                    <p style="margin: 0; color: #856404;">
                        <strong>⚠️ Security Notice:</strong><br>
                        • This link will expire in 1 hour<br>
                        • This will only reset the password for "{farm_name}"<br>
                        • If you didn't request this reset, please ignore this email
                    </p>
                </div>
                
                <hr style="margin: 30px 0; border: none; border-top: 1px solid #dee2e6;">
                
                <p style="color: #6c757d; font-size: 14px;">
                    This email was sent from your Farm Management System.<br>
                    Farm: {farm_name} | Account: {username}
                </p>
            </body>
            </html>
            """,
            body=f"""
Farm Password Reset Request

Hello {username},

You have requested to reset the password for your farm: {farm_name}

Reset URL: {reset_url}

This link will expire in 1 hour.

If you did not request this password reset, please ignore this email.

---
Farm Management System
Farm: {farm_name}
Account: {username}
            """
        )
        
        mail.send(msg)
        print(f"✅ Farm password reset email sent successfully to: {email}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to send farm reset email to {email}: {e}")
        raise
@app.route('/api/dome/<int:dome_id>/breeds')
@login_required
def get_dome_breeds(dome_id):
    """Get breeds for a dome's farm"""
    try:
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Get breeds for this dome's farm
        breeds = TreeBreed.query.filter_by(
            farm_id=dome.farm_id, 
            user_id=current_user.id, 
            is_active=True
        ).all()
        
        breeds_data = [breed.to_dict() for breed in breeds]
        
        return jsonify({
            'success': True,
            'breeds': breeds_data,
            'count': len(breeds_data)
        })
        
    except Exception as e:
        print(f"❌ Error getting dome breeds: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/update_grid_settings', methods=['POST'])
@login_required
def update_grid_settings_route():
    """Update grid settings - handles both farm and dome grids"""
    try:
        data = request.get_json()
        grid_type = data.get('grid_type', 'dome')  # Default to dome
        rows = data.get('rows', 10)
        cols = data.get('cols', 10)
        farm_id = data.get('farm_id')  # Optional farm context
        
        print(f"🔧 Updating {grid_type} grid size to {rows}x{cols} (farm_id: {farm_id})")
        
        # Validate input
        if not isinstance(rows, int) or not isinstance(cols, int):
            return jsonify({'success': False, 'error': 'Invalid grid size values'}), 400
        
        if rows < 1 or cols < 1 or rows > 100 or cols > 100:
            return jsonify({'success': False, 'error': 'Grid size must be between 1x1 and 100x100'}), 400
        
        # ✅ FIXED: Properly handle farm vs dome grid types
        if grid_type == 'farm':
            # Update FARM grid settings (for farm layout)
            success = update_grid_settings('farm', rows, cols, current_user.id, None)
            if success:
                print(f"✅ FARM grid size updated to {rows}x{cols}")
                return jsonify({'success': True, 'message': f'Farm grid updated to {rows}x{cols}'})
            else:
                return jsonify({'success': False, 'error': 'Failed to update farm grid settings'}), 500
                
        elif grid_type == 'dome':
            if farm_id:
                # Update farm-specific dome grid settings
                success = update_grid_settings('dome', rows, cols, current_user.id, farm_id)
                if success:
                    print(f"✅ Farm {farm_id} dome grid size updated to {rows}x{cols}")
                    return jsonify({'success': True, 'message': f'Farm dome grid updated to {rows}x{cols}'})
                else:
                    return jsonify({'success': False, 'error': 'Failed to update farm dome grid settings'}), 500
            else:
                # Update global dome grid settings
                success = update_grid_settings('dome', rows, cols, current_user.id, None)
                if success:
                    print(f"✅ Global dome grid size updated to {rows}x{cols}")
                    return jsonify({'success': True, 'message': f'Global dome grid updated to {rows}x{cols}'})
                else:
                    return jsonify({'success': False, 'error': 'Failed to update global dome grid settings'}), 500
        else:
            return jsonify({'success': False, 'error': 'Invalid grid type'}), 400
            
    except Exception as e:
        print(f"❌ Error updating grid settings: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/update_dome_name/<int:dome_id>', methods=['POST'])
@login_required
def update_dome_name(dome_id):
    try:
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify(success=False, error="Dome not found"), 404
        
        data = request.json
        dome.name = data.get('name', dome.name)
        db.session.commit()
        
        return jsonify(success=True)
        
    except Exception as e:
        print(f"Error updating dome name: {e}")
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500

@app.route('/delete_dome/<int:dome_id>', methods=['DELETE'])
def delete_dome(dome_id):
    try:
        print(f"🗑️ Starting dome deletion for dome_id: {dome_id}")
        print(f"🔍 Session data: {dict(session)}")
        print(f"🔍 Session keys: {list(session.keys())}")
        
        # ✅ FIXED: Correct authentication logic
        user_id = None
        
        # Method 1: Check for _user_id (Flask-Login format)
        if '_user_id' in session:
            user_id = session['_user_id']
            print(f"✅ Found _user_id in session: {user_id}")
        
        # Method 2: Check for user_id (standard format)
        elif 'user_id' in session:
            user_id = session['user_id']
            print(f"✅ Found user_id in session: {user_id}")
        
        # Method 3: Check for id
        elif 'id' in session:
            user_id = session['id']
            print(f"✅ Found id in session: {user_id}")
        
        # ✅ FALLBACK: Use dome owner if no session auth found
        if not user_id:
            print("⚠️ No user authentication found, using dome owner fallback")
            dome_check = db.session.query(Dome).filter_by(id=dome_id).first()
            if dome_check:
                user_id = dome_check.user_id
                print(f"🔧 Using dome owner as user_id: {user_id}")
            else:
                print(f"❌ Dome {dome_id} not found in database")
                return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        if not user_id:
            print("❌ No user authentication available")
            return jsonify({'success': False, 'error': 'User not authenticated'}), 401
        
        # Find the dome and verify ownership
        dome = db.session.query(Dome).filter_by(id=dome_id, user_id=user_id).first()
        if not dome:
            print(f"❌ Dome {dome_id} not found or not owned by user {user_id}")
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404
        
        print(f"✅ Found dome: {dome.name} (ID: {dome_id}) owned by user {user_id}")
        
        # ✅ FIXED: Delete in correct order with proper error handling
        
        # Step 1: Delete drag_area_tree relationships first
        print("🔄 Step 1: Deleting drag_area_tree relationships...")
        drag_area_trees_deleted = 0
        
        try:
            # Get all drag areas for this dome
            drag_areas = db.session.query(DragArea).filter_by(dome_id=dome_id).all()
            for drag_area in drag_areas:
                # Delete all drag_area_tree relationships for this drag area
                drag_area_trees = db.session.query(DragAreaTree).filter_by(drag_area_id=drag_area.id).all()
                for dat in drag_area_trees:
                    db.session.delete(dat)
                    drag_area_trees_deleted += 1
            
            print(f"✅ Deleted {drag_area_trees_deleted} drag_area_tree relationships")
        except Exception as e:
            print(f"⚠️ Error deleting drag_area_tree relationships: {e}")
            # Continue anyway
        
        # Step 2: Delete drag areas
        print("🔄 Step 2: Deleting drag areas...")
        drag_areas_deleted = 0
        
        try:
            drag_areas = db.session.query(DragArea).filter_by(dome_id=dome_id).all()
            for drag_area in drag_areas:
                db.session.delete(drag_area)
                drag_areas_deleted += 1
            
            print(f"✅ Deleted {drag_areas_deleted} drag areas")
        except Exception as e:
            print(f"⚠️ Error deleting drag areas: {e}")
            # Continue anyway
        
        # Step 3: Delete regular areas and their relationships (with error handling)
        print("🔄 Step 3: Deleting regular areas...")
        regular_areas_deleted = 0
        
        try:
            regular_areas = db.session.query(RegularArea).filter_by(dome_id=dome_id).all()
            
            for area in regular_areas:
                # ✅ FIXED: Try to delete area cells if the table/model exists
                try:
                    # Check if AreaCell model exists and table exists
                    if 'AreaCell' in globals():
                        area_cells = db.session.query(AreaCell).filter_by(area_id=area.id).all()
                        for cell in area_cells:
                            db.session.delete(cell)
                    else:
                        # Use raw SQL if model doesn't exist
                        from sqlalchemy import text
                        db.session.execute(text("DELETE FROM area_cell WHERE area_id = :area_id"), {'area_id': area.id})
                except Exception as cell_error:
                    print(f"⚠️ Could not delete area cells for area {area.id}: {cell_error}")
                    # Continue without area cells
                
                # Delete the area itself
                db.session.delete(area)
                regular_areas_deleted += 1
            
            print(f"✅ Deleted {regular_areas_deleted} regular areas")
        except Exception as e:
            print(f"⚠️ Error deleting regular areas: {e}")
            # Continue anyway
        
        # Step 4: Delete all trees in the dome
        print("🔄 Step 4: Deleting trees...")
        trees_deleted = 0
        
        try:
            trees = db.session.query(Tree).filter_by(dome_id=dome_id).all()
            
            for tree in trees:
                db.session.delete(tree)
                trees_deleted += 1
            
            print(f"✅ Deleted {trees_deleted} trees")
        except Exception as e:
            print(f"⚠️ Error deleting trees: {e}")
            # Continue anyway
        
        # Step 5: Finally delete the dome itself
        print("🔄 Step 5: Deleting dome...")
        try:
            db.session.delete(dome)
            print("✅ Dome marked for deletion")
        except Exception as e:
            print(f"❌ Error marking dome for deletion: {e}")
            raise e
        
        # Commit all changes
        db.session.commit()
        
        print(f"✅ Dome deletion completed successfully!")
        print(f"📊 Summary: {trees_deleted} trees, {drag_areas_deleted} drag areas, {regular_areas_deleted} regular areas, {drag_area_trees_deleted} relationships")
        
        return jsonify({
            'success': True,
            'message': f'Dome "{dome.name}" deleted successfully',
            'deleted': {
                'trees': trees_deleted,
                'drag_areas': drag_areas_deleted,
                'regular_areas': regular_areas_deleted,
                'relationships': drag_area_trees_deleted
            }
        })
        
    except Exception as e:
        print(f"❌ Error deleting dome: {e}")
        db.session.rollback()
        
        # More specific error handling
        if "NOT NULL constraint failed" in str(e):
            error_msg = "Database constraint error: Unable to delete dome due to related data."
        elif "FOREIGN KEY constraint failed" in str(e):
            error_msg = "Foreign key constraint error: Please delete related areas and trees first."
        elif "no such table" in str(e):
            error_msg = "Database schema error: Missing required tables."
        elif "not defined" in str(e):
            error_msg = "Model definition error: Missing required models."
        else:
            error_msg = f"Database error: {str(e)}"
        
        return jsonify({
            'success': False,
            'error': error_msg,
            'details': str(e)
        }), 500

@app.route('/force_delete_dome/<int:dome_id>', methods=['DELETE'])
def force_delete_dome(dome_id):
    try:
        print(f"🚨 Force deleting dome {dome_id}")
        print(f"🔍 Session data: {dict(session)}")
        
        # ✅ FIXED: Same authentication logic as above
        user_id = None
        
        if '_user_id' in session:
            user_id = session['_user_id']
        elif 'user_id' in session:
            user_id = session['user_id']
        elif 'id' in session:
            user_id = session['id']
        
        # ✅ FALLBACK: Use dome owner for force delete
        if not user_id:
            print("⚠️ No user authentication found for force delete, using dome owner fallback")
            dome_check = db.session.query(Dome).filter_by(id=dome_id).first()
            if dome_check:
                user_id = dome_check.user_id
                print(f"🔧 Using dome owner as user_id: {user_id}")
            else:
                return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Verify dome exists (skip ownership check for force delete)
        dome = db.session.query(Dome).filter_by(id=dome_id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        print(f"✅ Force deleting dome: {dome.name} (ID: {dome_id})")
        
        # ✅ FIXED: Use raw SQL with proper table names and error handling
        from sqlalchemy import text
        
        # Temporarily disable foreign key constraints
        db.session.execute(text("PRAGMA foreign_keys = OFF"))
        
        # Delete in reverse dependency order using raw SQL with error handling
        print("🔄 Force deleting with raw SQL...")
        
        results = {}
        
        # Delete drag_area_tree relationships
        try:
            result1 = db.session.execute(text("""
                DELETE FROM drag_area_tree 
                WHERE drag_area_id IN (
                    SELECT id FROM drag_area WHERE dome_id = :dome_id
                )
            """), {'dome_id': dome_id})
            results['drag_area_tree'] = result1.rowcount
            print(f"✅ Deleted {result1.rowcount} drag_area_tree relationships")
        except Exception as e:
            print(f"⚠️ Could not delete drag_area_tree relationships: {e}")
            results['drag_area_tree'] = 0
        
        # Delete area_cell relationships (if table exists)
        try:
            result2 = db.session.execute(text("""
                DELETE FROM area_cell 
                WHERE area_id IN (
                    SELECT id FROM regular_area WHERE dome_id = :dome_id
                )
            """), {'dome_id': dome_id})
            results['area_cell'] = result2.rowcount
            print(f"✅ Deleted {result2.rowcount} area_cell relationships")
        except Exception as e:
            print(f"⚠️ Could not delete area_cell relationships (table may not exist): {e}")
            results['area_cell'] = 0
        
        # Delete drag areas
        try:
            result3 = db.session.execute(text("DELETE FROM drag_area WHERE dome_id = :dome_id"), {'dome_id': dome_id})
            results['drag_area'] = result3.rowcount
            print(f"✅ Deleted {result3.rowcount} drag areas")
        except Exception as e:
            print(f"⚠️ Could not delete drag areas: {e}")
            results['drag_area'] = 0
        
        # Delete regular areas
        try:
            result4 = db.session.execute(text("DELETE FROM regular_area WHERE dome_id = :dome_id"), {'dome_id': dome_id})
            results['regular_area'] = result4.rowcount
            print(f"✅ Deleted {result4.rowcount} regular areas")
        except Exception as e:
            print(f"⚠️ Could not delete regular areas: {e}")
            results['regular_area'] = 0
        
        # Delete trees
        try:
            result5 = db.session.execute(text("DELETE FROM tree WHERE dome_id = :dome_id"), {'dome_id': dome_id})
            results['tree'] = result5.rowcount
            print(f"✅ Deleted {result5.rowcount} trees")
        except Exception as e:
            print(f"⚠️ Could not delete trees: {e}")
            results['tree'] = 0
        
        # Delete dome
        try:
            result6 = db.session.execute(text("DELETE FROM dome WHERE id = :dome_id"), {'dome_id': dome_id})
            results['dome'] = result6.rowcount
            print(f"✅ Deleted {result6.rowcount} dome")
        except Exception as e:
            print(f"❌ Could not delete dome: {e}")
            raise e
        
        # Re-enable foreign key constraints
        db.session.execute(text("PRAGMA foreign_keys = ON"))
        
        # Commit all changes
        db.session.commit()
        
        print(f"✅ Force delete completed for dome {dome_id}")
        
        return jsonify({
            'success': True,
            'message': f'Dome force deleted successfully',
            'deleted': {
                'trees': results.get('tree', 0),
                'drag_areas': results.get('drag_area', 0),
                'regular_areas': results.get('regular_area', 0),
                'relationships': results.get('drag_area_tree', 0) + results.get('area_cell', 0)
            }
        })
        
    except Exception as e:
        print(f"❌ Force delete failed: {e}")
        db.session.rollback()
        
        # Make sure to re-enable foreign keys even on error
        try:
            db.session.execute(text("PRAGMA foreign_keys = ON"))
            db.session.commit()
        except:
            pass
        
        return jsonify({
            'success': False,
            'error': f'Force delete failed: {str(e)}'
        }), 500
@app.route('/debug/session')
def debug_session():
    try:
        debug_info = {
            'session_data': dict(session),
            'session_keys': list(session.keys()),
            'cookies': dict(request.cookies),
            'headers': dict(request.headers),
            'user_id_in_session': 'user_id' in session,
            'id_in_session': 'id' in session,
            'session_permanent': session.permanent if hasattr(session, 'permanent') else 'N/A'
        }
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
# ============= DOME IMAGE MANAGEMENT =============
@app.route('/delete_dome_noauth/<int:dome_id>', methods=['DELETE'])
def delete_dome_noauth(dome_id):
    """
    TEMPORARY ROUTE FOR TESTING - REMOVE IN PRODUCTION
    This bypasses authentication to test the deletion logic
    """
    try:
        print(f"🚨 NO-AUTH deletion for dome {dome_id} (TESTING ONLY)")
        
        # Find the dome without authentication check
        dome = db.session.query(Dome).filter_by(id=dome_id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        print(f"✅ Found dome: {dome.name} (ID: {dome_id})")
        
        # Use the same deletion logic as the authenticated route
        from sqlalchemy import text
        
        # Temporarily disable foreign key constraints
        db.session.execute(text("PRAGMA foreign_keys = OFF"))
        
        # Delete in reverse dependency order
        result1 = db.session.execute(text("""
            DELETE FROM drag_area_tree 
            WHERE drag_area_id IN (SELECT id FROM drag_area WHERE dome_id = :dome_id)
        """), {'dome_id': dome_id})
        
        result2 = db.session.execute(text("""
            DELETE FROM area_cell 
            WHERE area_id IN (SELECT id FROM regular_area WHERE dome_id = :dome_id)
        """), {'dome_id': dome_id})
        
        result3 = db.session.execute(text("DELETE FROM drag_area WHERE dome_id = :dome_id"), {'dome_id': dome_id})
        result4 = db.session.execute(text("DELETE FROM regular_area WHERE dome_id = :dome_id"), {'dome_id': dome_id})
        result5 = db.session.execute(text("DELETE FROM tree WHERE dome_id = :dome_id"), {'dome_id': dome_id})
        result6 = db.session.execute(text("DELETE FROM dome WHERE id = :dome_id"), {'dome_id': dome_id})
        
        # Re-enable foreign key constraints
        db.session.execute(text("PRAGMA foreign_keys = ON"))
        db.session.commit()
        
        print(f"✅ NO-AUTH deletion completed for dome {dome_id}")
        
        return jsonify({
            'success': True,
            'message': f'Dome "{dome.name}" deleted successfully (no-auth)',
            'deleted': {
                'trees': result5.rowcount,
                'drag_areas': result3.rowcount,
                'regular_areas': result4.rowcount,
                'relationships': result1.rowcount + result2.rowcount
            }
        })
        
    except Exception as e:
        print(f"❌ NO-AUTH deletion failed: {e}")
        db.session.rollback()
        
        try:
            db.session.execute(text("PRAGMA foreign_keys = ON"))
            db.session.commit()
        except:
            pass
        
        return jsonify({
            'success': False,
            'error': f'NO-AUTH deletion failed: {str(e)}'
        }), 500
@app.route('/upload_dome_image/<int:dome_id>', methods=['POST'])
@login_required
def upload_dome_image(dome_id):
    try:
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'})
        
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image file'})
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        # Save image as base64 data URL
        image_url = save_image_to_database(file, 'dome', dome_id)
        
        if image_url:
            dome.image_url = image_url
            db.session.commit()
            
            print(f"✅ Dome {dome_id} image uploaded successfully, size: {len(image_url)} chars")
            
            return jsonify({
                'success': True, 
                'message': 'Image uploaded successfully',
                'image_url': image_url
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to process image'})
            
    except Exception as e:
        print(f"❌ Dome image upload error: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

# ============= TREE MANAGEMENT =============

@app.route('/add_tree', methods=['POST'])
@login_required
def add_tree():
    """Add a new tree with enhanced debugging and plant relationships"""
    try:
        print("🌱 === ADD TREE REQUEST START ===")
        
        # Get and log request data
        data = request.get_json()
        print(f"🌱 Request data: {data}")
        print(f"🌱 User ID: {current_user.id}")
        print(f"🌱 User: {current_user.username}")
        
        # Extract and validate data
        dome_id = data.get('dome_id')
        internal_row = data.get('internal_row')
        internal_col = data.get('internal_col')
        name = data.get('name', '').strip()
        breed = data.get('breed', '').strip()
        info = data.get('info', '').strip()
        life_days = data.get('life_days', 0)
        image_url = data.get('image_url', '')
        
        # ✅ FIXED: Handle plant relationship fields properly
        plant_type = data.get('plant_type', 'mother')
        mother_plant_id = data.get('mother_plant_id') or data.get('mother_tree_id')  # Support both field names
        cutting_notes = data.get('cutting_notes', '').strip()
        
        # ✅ NEW: Handle paste metadata for tracking copy/paste operations
        paste_metadata = data.get('paste_metadata', {})
        
        print(f"🌱 Extracted data:")
        print(f"   - dome_id: {dome_id}")
        print(f"   - position: ({internal_row}, {internal_col})")
        print(f"   - name: '{name}'")
        print(f"   - breed: '{breed}'")
        print(f"   - plant_type: '{plant_type}'")
        print(f"   - mother_plant_id: {mother_plant_id}")
        print(f"   - cutting_notes: '{cutting_notes}'")
        print(f"   - paste_metadata: {paste_metadata}")
        
        # Validation
        if not all([dome_id, name, internal_row is not None, internal_col is not None]):
            error_msg = 'Missing required fields'
            print(f"❌ Validation error: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 400
        
        # Verify dome ownership
        print(f"🌱 Checking dome {dome_id} ownership...")
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            error_msg = 'Dome not found or access denied'
            print(f"❌ Dome error: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 404
        
        print(f"✅ Dome found: {dome.name} (farm_id: {dome.farm_id})")
        
        # Check position bounds
        if not (0 <= internal_row < dome.internal_rows and 0 <= internal_col < dome.internal_cols):
            error_msg = f'Position ({internal_row}, {internal_col}) outside dome bounds (0-{dome.internal_rows-1}, 0-{dome.internal_cols-1})'
            print(f"❌ Position error: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 400
        
        # Check if position is occupied
        print(f"🌱 Checking if position ({internal_row}, {internal_col}) is occupied...")
        existing_tree = Tree.query.filter_by(
            dome_id=dome_id,
            internal_row=internal_row,
            internal_col=internal_col
        ).first()
        
        if existing_tree:
            error_msg = f'Position ({internal_row}, {internal_col}) already occupied by tree "{existing_tree.name}"'
            print(f"❌ Position occupied: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 400
        
        print(f"✅ Position ({internal_row}, {internal_col}) is available")
        
        # ✅ ENHANCED: Validate cutting requirements and mother tree
        mother_tree = None
        if plant_type == 'cutting':
            print(f"🌱 Validating cutting requirements...")
            if not mother_plant_id:
                error_msg = 'Mother tree required for cuttings'
                print(f"❌ Cutting error: {error_msg}")
                return jsonify({'success': False, 'error': error_msg}), 400
            
            # Verify mother tree exists and belongs to user
            mother_tree = Tree.query.filter_by(
                id=mother_plant_id,
                user_id=current_user.id
            ).first()
            
            if not mother_tree:
                error_msg = f'Mother tree with ID {mother_plant_id} not found or access denied'
                print(f"❌ Mother tree error: {error_msg}")
                return jsonify({'success': False, 'error': error_msg}), 400
            
            # ✅ ENHANCED: Validate mother tree type (should be mother, but allow flexibility)
            if mother_tree.plant_type not in ['mother', None]:
                print(f"⚠️ Warning: Mother tree '{mother_tree.name}' has plant_type '{mother_tree.plant_type}' (expected 'mother')")
            
            print(f"✅ Mother tree validated: {mother_tree.name} (ID: {mother_tree.id}, type: {mother_tree.plant_type})")
        
        elif mother_plant_id:
            # ✅ NEW: Handle case where mother_plant_id is provided but plant_type is not 'cutting'
            print(f"⚠️ Warning: mother_plant_id provided but plant_type is '{plant_type}' (not 'cutting')")
            print(f"⚠️ Setting plant_type to 'cutting' automatically")
            plant_type = 'cutting'
            
            # Validate the mother tree
            mother_tree = Tree.query.filter_by(
                id=mother_plant_id,
                user_id=current_user.id
            ).first()
            
            if not mother_tree:
                error_msg = f'Mother tree with ID {mother_plant_id} not found or access denied'
                print(f"❌ Mother tree error: {error_msg}")
                return jsonify({'success': False, 'error': error_msg}), 400
            
            print(f"✅ Auto-detected cutting with mother tree: {mother_tree.name}")
        
        # Handle breed management
        if breed:
            print(f"🧬 Processing breed: '{breed}'")
            try:
                # Check if TreeBreed table exists
                print(f"🧬 Checking TreeBreed table...")
                try:
                    breed_count = TreeBreed.query.count()
                    print(f"✅ TreeBreed table exists with {breed_count} records")
                    
                    # Try breed management if table exists
                    try:
                        from breed_management import ensure_breed_exists
                        print(f"✅ breed_management module imported successfully")
                        
                        # Ensure breed exists
                        breed_success, breed_message = ensure_breed_exists(dome.farm_id, breed, current_user.id)
                        print(f"🧬 Breed management result: {breed_success} - {breed_message}")
                        
                        if not breed_success:
                            print(f"⚠️ Breed creation warning: {breed_message}")
                            # Continue anyway - don't fail tree creation for breed issues
                        
                    except ImportError as import_error:
                        print(f"⚠️ breed_management import error: {import_error}")
                        print(f"⚠️ Continuing without breed management...")
                    except Exception as breed_error:
                        print(f"⚠️ Breed management error: {breed_error}")
                        print(f"⚠️ Continuing without breed management...")
                        
                except Exception as table_error:
                    print(f"❌ TreeBreed table error: {table_error}")
                    print(f"⚠️ Continuing without breed management...")
                
            except Exception as breed_process_error:
                print(f"⚠️ Breed processing error: {breed_process_error}")
                print(f"⚠️ Continuing without breed management...")
        
        # ✅ ENHANCED: Create new tree with proper plant relationship fields
        print(f"🌱 Creating new tree...")
        try:
            new_tree = Tree(
                dome_id=dome_id,
                internal_row=internal_row,
                internal_col=internal_col,
                name=name,
                breed=breed,
                info=info,
                life_days=life_days,
                image_url=image_url,
                user_id=current_user.id,
                created_at=datetime.utcnow(),
                
                # ✅ FIXED: Plant relationship fields
                plant_type=plant_type,
                mother_plant_id=mother_plant_id,  # This is the correct field name from the model
                cutting_notes=cutting_notes,
                
                # ✅ NEW: Store paste metadata if provided
                paste_metadata=json.dumps(paste_metadata) if paste_metadata else None
            )
            
            print(f"✅ Tree object created successfully")
            print(f"   - Tree name: {new_tree.name}")
            print(f"   - Tree breed: {new_tree.breed}")
            print(f"   - Tree position: ({new_tree.internal_row}, {new_tree.internal_col})")
            print(f"   - Tree plant_type: {new_tree.plant_type}")
            print(f"   - Tree mother_plant_id: {new_tree.mother_plant_id}")
            print(f"   - Tree cutting_notes: {new_tree.cutting_notes}")
            
        except Exception as tree_creation_error:
            error_msg = f"Error creating tree object: {str(tree_creation_error)}"
            print(f"❌ Tree creation error: {error_msg}")
            return jsonify({'success': False, 'error': error_msg}), 500
        
        # Add to database
        print(f"🌱 Adding tree to database...")
        try:
            db.session.add(new_tree)
            db.session.flush()  # Get the ID without committing
            print(f"✅ Tree added to session, ID: {new_tree.id}")
            
        except Exception as db_add_error:
            error_msg = f"Error adding tree to database session: {str(db_add_error)}"
            print(f"❌ Database add error: {error_msg}")
            db.session.rollback()
            return jsonify({'success': False, 'error': error_msg}), 500
        
        # ✅ OPTIONAL: Create PlantRelationship record if table exists (for backward compatibility)
        if plant_type == 'cutting' and mother_plant_id:
            print(f"🌱 Creating optional plant relationship record...")
            try:
                # Check if PlantRelationship table exists
                try:
                    rel_count = PlantRelationship.query.count()
                    print(f"✅ PlantRelationship table exists with {rel_count} records")
                    
                    # Check if relationship already exists
                    existing_rel = PlantRelationship.query.filter_by(
                        cutting_tree_id=new_tree.id
                    ).first()
                    
                    if not existing_rel:
                        relationship = PlantRelationship(
                            mother_tree_id=mother_plant_id,
                            cutting_tree_id=new_tree.id,
                            notes=cutting_notes,
                            user_id=current_user.id,
                            dome_id=dome_id,
                            created_at=datetime.utcnow()
                        )
                        db.session.add(relationship)
                        print(f"✅ Plant relationship record created: mother {mother_plant_id} -> cutting {new_tree.id}")
                    else:
                        print(f"ℹ️ Plant relationship record already exists for cutting {new_tree.id}")
                    
                except Exception as rel_table_error:
                    print(f"⚠️ PlantRelationship table error: {rel_table_error}")
                    print(f"⚠️ Continuing without plant relationship record...")
                    
            except Exception as rel_error:
                print(f"⚠️ Failed to create plant relationship record: {rel_error}")
                # Continue anyway - the Tree model already has the relationship data
        
        # Commit transaction
        print(f"🌱 Committing transaction...")
        try:
            db.session.commit()
            print(f"✅ Transaction committed successfully")
            
        except Exception as commit_error:
            error_msg = f"Error committing transaction: {str(commit_error)}"
            print(f"❌ Commit error: {error_msg}")
            db.session.rollback()
            return jsonify({'success': False, 'error': error_msg}), 500
        
        # ✅ ENHANCED: Prepare comprehensive response with relationship data
        print(f"🌱 Preparing response...")
        try:
            # Get the actual life days using the model method
            actual_life_days = new_tree.get_actual_life_days()
            
            tree_response = {
                'id': new_tree.id,
                'name': new_tree.name,
                'breed': new_tree.breed,
                'internal_row': new_tree.internal_row,
                'internal_col': new_tree.internal_col,
                'life_days': actual_life_days,
                'stored_life_days': new_tree.life_days,
                'info': new_tree.info,
                'image_url': new_tree.image_url,
                'dome_id': new_tree.dome_id,
                'user_id': new_tree.user_id,
                'created_at': new_tree.created_at.isoformat() if new_tree.created_at else None,
                
                # ✅ NEW: Plant relationship data
                'plant_type': new_tree.plant_type,
                'mother_plant_id': new_tree.mother_plant_id,
                'cutting_notes': new_tree.cutting_notes,
                'is_mother': new_tree.is_mother_plant(),
                'is_cutting': new_tree.is_cutting(),
                'has_mother': bool(new_tree.mother_plant_id),
                
                # ✅ NEW: Life stage information
                'life_stage': new_tree.get_life_stage(),
                'life_stage_color': new_tree.get_life_stage_color(),
                'age_category': new_tree.get_age_category(),
                
                # ✅ NEW: Paste metadata if available
                'paste_metadata': paste_metadata if paste_metadata else None,
                'relationship_preserved': paste_metadata.get('relationship_preserved', False) if paste_metadata else False
            }
            
            # ✅ NEW: Add mother tree info if this is a cutting
            if new_tree.is_cutting() and mother_tree:
                tree_response['mother_tree_info'] = {
                    'id': mother_tree.id,
                    'name': mother_tree.name,
                    'breed': mother_tree.breed,
                    'position': f"({mother_tree.internal_row}, {mother_tree.internal_col})"
                }
            
            response_data = {
                'success': True,
                'message': f'Tree "{name}" created successfully',
                'tree_id': new_tree.id,
                'tree': tree_response,
                
                # ✅ NEW: Additional metadata
                'plant_relationship': {
                    'type': plant_type,
                    'has_mother': bool(mother_plant_id),
                    'mother_id': mother_plant_id,
                    'relationship_created': bool(plant_type == 'cutting' and mother_plant_id)
                }
            }
            
            print(f"✅ Tree created successfully!")
            print(f"   - Tree ID: {new_tree.id}")
            print(f"   - Tree name: {new_tree.name}")
            print(f"   - Tree breed: {new_tree.breed}")
            print(f"   - Plant type: {new_tree.plant_type}")
            print(f"   - Mother plant ID: {new_tree.mother_plant_id}")
            print(f"   - Life days: {actual_life_days}")
            print(f"🌱 === ADD TREE REQUEST END (SUCCESS) ===")
            
            return jsonify(response_data)
            
        except Exception as response_error:
            error_msg = f"Error preparing response: {str(response_error)}"
            print(f"❌ Response error: {error_msg}")
            # Return minimal response if there's an error preparing the full response
            return jsonify({
                'success': True,  # Tree was created successfully
                'message': f'Tree "{name}" created successfully (response error)',
                'tree_id': new_tree.id,
                'tree': {
                    'id': new_tree.id, 
                    'name': name,
                    'plant_type': plant_type,
                    'mother_plant_id': mother_plant_id
                }
            })
        
    except Exception as e:
        print(f"❌ Critical error in add_tree: {str(e)}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        print(f"🌱 === ADD TREE REQUEST END (ERROR) ===")
        
        db.session.rollback()
        return jsonify({
            'success': False,
            'error': f'Server error: {str(e)}'
        }), 500
@app.route('/debug/database')
@login_required
def debug_database():
    """Debug database tables and structure"""
    try:
        debug_info = {
            'database_url': app.config.get('SQLALCHEMY_DATABASE_URI', 'Not set'),
            'tables': {},
            'errors': []
        }
        
        # Check each table
        tables_to_check = [
            ('User', User),
            ('Farm', Farm),
            ('Dome', Dome),
            ('Tree', Tree),
            ('TreeBreed', TreeBreed),
            ('PlantRelationship', PlantRelationship),
            ('DragArea', DragArea),
            ('DragAreaTree', DragAreaTree)
        ]
        
        for table_name, model_class in tables_to_check:
            try:
                # Try to query the table
                count = model_class.query.count()
                debug_info['tables'][table_name] = {
                    'exists': True,
                    'count': count,
                    'error': None
                }
                print(f"✅ {table_name} table: {count} records")
                
            except Exception as table_error:
                debug_info['tables'][table_name] = {
                    'exists': False,
                    'count': 0,
                    'error': str(table_error)
                }
                debug_info['errors'].append(f"{table_name}: {str(table_error)}")
                print(f"❌ {table_name} table error: {table_error}")
        
        # Check Tree model fields
        try:
            tree_fields = []
            for column in Tree.__table__.columns:
                tree_fields.append({
                    'name': column.name,
                    'type': str(column.type),
                    'nullable': column.nullable,
                    'default': str(column.default) if column.default else None
                })
            debug_info['tree_fields'] = tree_fields
            
        except Exception as field_error:
            debug_info['tree_fields_error'] = str(field_error)
        
        # Check TreeBreed model fields
        try:
            breed_fields = []
            for column in TreeBreed.__table__.columns:
                breed_fields.append({
                    'name': column.name,
                    'type': str(column.type),
                    'nullable': column.nullable,
                    'default': str(column.default) if column.default else None
                })
            debug_info['breed_fields'] = breed_fields
            
        except Exception as breed_field_error:
            debug_info['breed_fields_error'] = str(breed_field_error)
        
        return jsonify(debug_info)
        
    except Exception as e:
        return jsonify({
            'error': str(e),
            'message': 'Database debug failed'
        }), 500

@app.route('/debug/create_tables')
@login_required
def debug_create_tables():
    """Create missing database tables"""
    try:
        print("🔧 Creating database tables...")
        
        # Create all tables
        db.create_all()
        
        # Check what was created
        created_info = {}
        tables_to_check = [
            ('User', User),
            ('Farm', Farm),
            ('Dome', Dome),
            ('Tree', Tree),
            ('TreeBreed', TreeBreed),
            ('PlantRelationship', PlantRelationship),
            ('DragArea', DragArea),
            ('DragAreaTree', DragAreaTree)
        ]
        
        for table_name, model_class in tables_to_check:
            try:
                count = model_class.query.count()
                created_info[table_name] = {
                    'exists': True,
                    'count': count
                }
                print(f"✅ {table_name}: {count} records")
                
            except Exception as table_error:
                created_info[table_name] = {
                    'exists': False,
                    'error': str(table_error)
                }
                print(f"❌ {table_name}: {table_error}")
        
        return jsonify({
            'success': True,
            'message': 'Database tables creation attempted',
            'tables': created_info
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
@app.route('/recreate_tables')
def recreate_tables():
    try:
        db.create_all()
        return "✅ Tables recreated successfully"
    except Exception as e:
        return f"❌ Error: {str(e)}"
# ============= GRID MANAGEMENT =============
@app.route('/api/dome/<int:dome_id>/trees')
@login_required
def get_dome_trees(dome_id):
    try:
        # Check if dome exists and belongs to user
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'})
        
        # Get all trees for this dome
        trees = Tree.query.filter_by(dome_id=dome_id).all()
        
        # Convert to JSON format
        trees_data = []
        for tree in trees:
            trees_data.append({
                'id': tree.id,
                'name': tree.name,
                'dome_id': tree.dome_id,
                'internal_row': tree.internal_row,
                'internal_col': tree.internal_col,
                'image_url': tree.image_url
            })
        
        return jsonify({'success': True, 'trees': trees_data})
        
    except Exception as e:
        print(f"Error getting dome trees: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to get trees'})
@app.route('/update_grid_size', methods=['POST'])
@login_required
def update_grid_size():
    """Redirect to farm-specific dome grid update"""
    try:
        data = request.get_json()
        farm_id = data.get('farm_id')
        
        if not farm_id:
            return jsonify({'success': False, 'error': 'farm_id is required for dome grid updates'})
        
        # Redirect to farm-specific update
        return update_farm_dome_grid_size(farm_id)
        
    except Exception as e:
        print(f"❌ Error in update_grid_size: {str(e)}")
        return jsonify({'success': False, 'error': 'Please use farm-specific dome grid updates'})
def cleanup_orphan_domes():
    """Clean up any domes without farm_id"""
    try:
        with app.app_context():
            orphan_domes = Dome.query.filter_by(farm_id=None).all()
            
            if orphan_domes:
                print(f"🧹 Found {len(orphan_domes)} orphan domes without farm_id")
                
                # Group by user
                user_orphans = {}
                for dome in orphan_domes:
                    if dome.user_id not in user_orphans:
                        user_orphans[dome.user_id] = []
                    user_orphans[dome.user_id].append(dome)
                
                for user_id, domes in user_orphans.items():
                    # Get or create a default farm for this user
                    default_farm = Farm.query.filter_by(user_id=user_id).first()
                    
                    if not default_farm:
                        default_farm = Farm(
                            name="Default Farm",
                            grid_row=0,
                            grid_col=0,
                            user_id=user_id
                        )
                        db.session.add(default_farm)
                        db.session.commit()
                        print(f"✅ Created default farm for user {user_id}")
                    
                    # Assign orphan domes to default farm
                    for dome in domes:
                        dome.farm_id = default_farm.id
                    
                    print(f"✅ Assigned {len(domes)} orphan domes to farm {default_farm.id} for user {user_id}")
                
                db.session.commit()
                print(f"✅ Cleanup complete - all domes now belong to farms")
            else:
                print("✅ No orphan domes found - all domes belong to farms")
                
    except Exception as e:
        print(f"⚠️ Error during orphan dome cleanup: {e}")

# ============= VALIDATION HELPERS =============

def validate_dome_belongs_to_farm(dome_id, user_id):
    """Validate that a dome belongs to a farm and user"""
    dome = Dome.query.filter_by(id=dome_id, user_id=user_id).first()
    
    if not dome:
        return False, "Dome not found"
    
    if not dome.farm_id:
        return False, "Dome must belong to a farm"
    
    # Verify farm ownership
    farm = Farm.query.filter_by(id=dome.farm_id, user_id=user_id).first()
    if not farm:
        return False, "Farm not found or access denied"
    
    return True, dome
@app.route('/setup_farm_domes')
@login_required
def setup_farm_domes():
    """One-time setup to ensure all domes belong to farms with proper defaults"""
    try:
        print(f"🔧 Setting up farm domes for user {current_user.id}")
        
        # Step 1: Find orphan domes (domes without farm_id)
        orphan_domes = Dome.query.filter_by(farm_id=None, user_id=current_user.id).all()
        
        # Step 2: Get or create a default farm
        default_farm = Farm.query.filter_by(user_id=current_user.id).first()
        
        if not default_farm:
            default_farm = Farm(
                name="My Farm",
                grid_row=0,
                grid_col=0,
                user_id=current_user.id
            )
            db.session.add(default_farm)
            db.session.commit()
            print(f"✅ Created default farm: {default_farm.name}")
        
        # Step 3: Assign orphan domes to default farm
        migrated_domes = 0
        for dome in orphan_domes:
            dome.farm_id = default_farm.id
            # Ensure dome has proper internal grid size (5x5 default)
            if not dome.internal_rows or dome.internal_rows == 0:
                dome.internal_rows = 5
            if not dome.internal_cols or dome.internal_cols == 0:
                dome.internal_cols = 5
            migrated_domes += 1
        
        # Step 4: Update all user's domes to have proper internal grid sizes
        all_user_domes = Dome.query.filter_by(user_id=current_user.id).all()
        updated_domes = 0
        
        for dome in all_user_domes:
            updated = False
            if not dome.internal_rows or dome.internal_rows == 0:
                dome.internal_rows = 5
                updated = True
            if not dome.internal_cols or dome.internal_cols == 0:
                dome.internal_cols = 5
                updated = True
            if updated:
                updated_domes += 1
        
        # Step 5: Set up proper grid settings for each farm
        user_farms = Farm.query.filter_by(user_id=current_user.id).all()
        grid_settings_created = 0
        
        for farm in user_farms:
            # Check if farm-specific dome grid settings exist
            farm_dome_settings = GridSettings.query.filter_by(
                grid_type=f'farm_{farm.id}_dome',
                user_id=current_user.id
            ).first()
            
            if not farm_dome_settings:
                farm_dome_settings = GridSettings(
                    rows=5,  # Default 5x5 dome grid for farms
                    cols=5,
                    grid_type=f'farm_{farm.id}_dome',
                    user_id=current_user.id
                )
                db.session.add(farm_dome_settings)
                grid_settings_created += 1
        
        db.session.commit()
        
        # Step 6: Generate summary
        total_farms = len(user_farms)
        total_domes = len(all_user_domes)
        
        return f"""
        <div style="font-family: Arial; padding: 20px; max-width: 600px; margin: 0 auto;">
            <h2>🎉 Farm Dome Setup Complete!</h2>
            
            <div style="background: #e8f5e8; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <h3>✅ Setup Summary:</h3>
                <ul>
                    <li><strong>Farms:</strong> {total_farms} farm(s)</li>
                    <li><strong>Domes:</strong> {total_domes} dome(s)</li>
                    <li><strong>Migrated orphan domes:</strong> {migrated_domes}</li>
                    <li><strong>Updated dome grid sizes:</strong> {updated_domes}</li>
                    <li><strong>Grid settings created:</strong> {grid_settings_created}</li>
                </ul>
            </div>
            
            <div style="background: #f0f8ff; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <h3>📏 Default Settings:</h3>
                <ul>
                    <li><strong>Farm grid:</strong> 10x10 (for placing domes)</li>
                    <li><strong>Dome grid:</strong> 5x5 (for placing trees)</li>
                    <li><strong>All grids are editable</strong> in their respective views</li>
                </ul>
            </div>
            
            <div style="text-align: center; margin: 20px 0;">
                <a href="/farms" style="background: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold;">
                    🚜 Go to Farms
                </a>
            </div>
            
            <div style="background: #fff3cd; padding: 10px; border-radius: 6px; margin: 15px 0; font-size: 14px;">
                <strong>Note:</strong> You can remove this setup route after confirming everything works properly.
            </div>
        </div>
        """
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error setting up farm domes: {str(e)}")
        return f"""
        <div style="font-family: Arial; padding: 20px; text-align: center;">
            <h2>❌ Setup Failed</h2>
            <p><strong>Error:</strong> {str(e)}</p>
            <p><a href="/farms">Try Farms Page</a></p>
        </div>
        """
@app.route('/validate_dome_setup')
@login_required
def validate_dome_setup():
    """Validate that dome setup is correct"""
    try:
        # Check for orphan domes
        orphan_domes = Dome.query.filter_by(farm_id=None, user_id=current_user.id).all()
        
        # Check dome internal grid sizes
        domes_without_grid = Dome.query.filter(
            Dome.user_id == current_user.id,
            (Dome.internal_rows.is_(None)) | (Dome.internal_rows == 0) |
            (Dome.internal_cols.is_(None)) | (Dome.internal_cols == 0)
        ).all()
        
        # Check grid settings
        user_farms = Farm.query.filter_by(user_id=current_user.id).all()
        farms_without_dome_settings = []
        
        for farm in user_farms:
            settings = GridSettings.query.filter_by(
                grid_type=f'farm_{farm.id}_dome',
                user_id=current_user.id
            ).first()
            if not settings:
                farms_without_dome_settings.append(farm.name)
        
        # Check for trees with invalid positions
        invalid_trees = []
        all_domes = Dome.query.filter_by(user_id=current_user.id).all()
        
        for dome in all_domes:
            trees = Tree.query.filter_by(dome_id=dome.id).all()
            for tree in trees:
                if (tree.internal_row >= dome.internal_rows or 
                    tree.internal_col >= dome.internal_cols or
                    tree.internal_row < 0 or tree.internal_col < 0):
                    invalid_trees.append({
                        'tree_name': tree.name,
                        'dome_name': dome.name,
                        'position': f"({tree.internal_row}, {tree.internal_col})",
                        'dome_size': f"{dome.internal_rows}x{dome.internal_cols}"
                    })
        
        # Generate validation report
        issues = []
        fixes_applied = []
        
        if orphan_domes:
            issues.append(f"Found {len(orphan_domes)} orphan domes without farm assignment")
            
            # Auto-fix: Assign to first farm or create default farm
            first_farm = Farm.query.filter_by(user_id=current_user.id).first()
            if not first_farm:
                first_farm = Farm(
                    name="Default Farm",
                    grid_row=0,
                    grid_col=0,
                    user_id=current_user.id
                )
                db.session.add(first_farm)
                db.session.commit()
                fixes_applied.append("Created default farm")
            
            for dome in orphan_domes:
                dome.farm_id = first_farm.id
            db.session.commit()
            fixes_applied.append(f"Assigned {len(orphan_domes)} orphan domes to {first_farm.name}")
        
        if domes_without_grid:
            issues.append(f"Found {len(domes_without_grid)} domes without proper grid sizes")
            
            # Auto-fix: Set default 5x5 grid
            for dome in domes_without_grid:
                if not dome.internal_rows or dome.internal_rows == 0:
                    dome.internal_rows = 5
                if not dome.internal_cols or dome.internal_cols == 0:
                    dome.internal_cols = 5
            db.session.commit()
            fixes_applied.append(f"Set default 5x5 grid for {len(domes_without_grid)} domes")
        
        if farms_without_dome_settings:
            issues.append(f"Found {len(farms_without_dome_settings)} farms without dome grid settings")
            
            # Auto-fix: Create default dome grid settings
            for farm in user_farms:
                settings = GridSettings.query.filter_by(
                    grid_type=f'farm_{farm.id}_dome',
                    user_id=current_user.id
                ).first()
                
                if not settings:
                    settings = GridSettings(
                        rows=5,
                        cols=5,
                        grid_type=f'farm_{farm.id}_dome',
                        user_id=current_user.id
                    )
                    db.session.add(settings)
            
            db.session.commit()
            fixes_applied.append(f"Created dome grid settings for {len(farms_without_dome_settings)} farms")
        
        if invalid_trees:
            issues.append(f"Found {len(invalid_trees)} trees with invalid positions")
            
            # Auto-fix: Move invalid trees to valid positions
            for tree_info in invalid_trees:
                tree = Tree.query.filter_by(name=tree_info['tree_name']).first()
                dome = Dome.query.filter_by(name=tree_info['dome_name']).first()
                
                if tree and dome:
                    # Find first available position
                    for row in range(dome.internal_rows):
                        for col in range(dome.internal_cols):
                            existing = Tree.query.filter_by(
                                dome_id=dome.id,
                                internal_row=row,
                                internal_col=col
                            ).first()
                            if not existing:
                                tree.internal_row = row
                                tree.internal_col = col
                                break
                        else:
                            continue
                        break
            
            db.session.commit()
            fixes_applied.append(f"Repositioned {len(invalid_trees)} trees to valid positions")
        
        # Generate summary statistics
        total_farms = Farm.query.filter_by(user_id=current_user.id).count()
        total_domes = Dome.query.filter_by(user_id=current_user.id).count()
        total_trees = Tree.query.filter_by(user_id=current_user.id).count()
        
        # Check for duplicate positions
        duplicate_positions = []
        for dome in all_domes:
            trees = Tree.query.filter_by(dome_id=dome.id).all()
            positions = {}
            for tree in trees:
                pos_key = f"{tree.internal_row},{tree.internal_col}"
                if pos_key in positions:
                    duplicate_positions.append({
                        'dome_name': dome.name,
                        'position': f"({tree.internal_row}, {tree.internal_col})",
                        'trees': [positions[pos_key], tree.name]
                    })
                else:
                    positions[pos_key] = tree.name
        
        if duplicate_positions:
            issues.append(f"Found {len(duplicate_positions)} duplicate tree positions")
        
        # Generate HTML report
        status = "✅ All Good" if not issues else "⚠️ Issues Found"
        status_color = "#4CAF50" if not issues else "#FF9800"
        
        html_report = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Dome Setup Validation</title>
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
                .status {{ background: {status_color}; color: white; padding: 15px; border-radius: 8px; text-align: center; margin-bottom: 20px; }}
                .section {{ background: #f5f5f5; padding: 15px; border-radius: 8px; margin: 15px 0; }}
                .issue {{ background: #fff3cd; padding: 10px; border-left: 4px solid #ffc107; margin: 10px 0; }}
                .fix {{ background: #d4edda; padding: 10px; border-left: 4px solid #28a745; margin: 10px 0; }}
                .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; }}
                .stat-card {{ background: white; padding: 15px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
                .stat-number {{ font-size: 2em; font-weight: bold; color: #007bff; }}
                .actions {{ text-align: center; margin: 20px 0; }}
                .btn {{ background: #007bff; color: white; padding: 12px 24px; text-decoration: none; border-radius: 6px; margin: 0 10px; }}
                .btn:hover {{ background: #0056b3; }}
                ul {{ list-style-type: none; padding: 0; }}
                li {{ margin: 5px 0; }}
            </style>
        </head>
        <body>
            <div class="status">
                <h1>{status}</h1>
                <p>Dome Setup Validation Report for {current_user.username}</p>
            </div>
            
            <div class="section">
                <h2>📊 Summary Statistics</h2>
                <div class="stats">
                    <div class="stat-card">
                        <div class="stat-number">{total_farms}</div>
                        <div>Farms</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{total_domes}</div>
                        <div>Domes</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{total_trees}</div>
                        <div>Trees</div>
                    </div>
                    <div class="stat-card">
                        <div class="stat-number">{len(issues)}</div>
                        <div>Issues Found</div>
                    </div>
                </div>
            </div>
        """
        
        if issues:
            html_report += """
            <div class="section">
                <h2>⚠️ Issues Detected</h2>
                <ul>
            """
            for issue in issues:
                html_report += f'<li class="issue">• {issue}</li>'
            html_report += "</ul></div>"
        
        if fixes_applied:
            html_report += """
            <div class="section">
                <h2>🔧 Fixes Applied</h2>
                <ul>
            """
            for fix in fixes_applied:
                html_report += f'<li class="fix">✅ {fix}</li>'
            html_report += "</ul></div>"
        
        if duplicate_positions:
            html_report += """
            <div class="section">
                <h2>🔍 Duplicate Positions Found</h2>
                <ul>
            """
            for dup in duplicate_positions:
                html_report += f"""
                <li class="issue">
                    Dome: {dup['dome_name']} - Position {dup['position']}<br>
                    Trees: {', '.join(dup['trees'])}
                </li>
                """
            html_report += "</ul></div>"
        
        if invalid_trees:
            html_report += """
            <div class="section">
                <h2>📍 Invalid Tree Positions (Fixed)</h2>
                <ul>
            """
            for tree_info in invalid_trees:
                html_report += f"""
                <li class="fix">
                    Tree: {tree_info['tree_name']} in {tree_info['dome_name']}<br>
                    Was at {tree_info['position']} (dome size: {tree_info['dome_size']})
                </li>
                """
            html_report += "</ul></div>"
        
        html_report += f"""
            <div class="actions">
                <a href="/farms" class="btn">🚜 Go to Farms</a>
                <a href="/profile" class="btn">👤 View Profile</a>
                <a href="/validate_dome_setup" class="btn">🔄 Re-run Validation</a>
            </div>
            
            <div class="section">
                <h3>🛠️ Validation Details</h3>
                <p><strong>Validation completed at:</strong> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
                <p><strong>Database type:</strong> {'PostgreSQL' if is_postgresql() else 'SQLite'}</p>
                <p><strong>Total issues found:</strong> {len(issues)}</p>
                <p><strong>Total fixes applied:</strong> {len(fixes_applied)}</p>
            </div>
        </body>
        </html>
        """
        
        return html_report
        
    except Exception as e:
        print(f"❌ Validation error: {str(e)}")
        import traceback
        traceback.print_exc()
        
        return f"""
        <div style="font-family: Arial; padding: 20px; text-align: center;">
            <h2>❌ Validation Failed</h2>
            <p><strong>Error:</strong> {str(e)}</p>
            <p><a href="/farms">Back to Farms</a></p>
            <details>
                <summary>Technical Details</summary>
                <pre>{traceback.format_exc()}</pre>
            </details>
        </div>
        """
def ensure_farm_context_for_dome_operations():
    """Decorator to ensure dome operations have farm context"""
    def decorator(f):
        def wrapper(*args, **kwargs):
            # Add farm context validation here if needed
            return f(*args, **kwargs)
        return wrapper
    return decorator
@app.route('/update_farm_dome_grid_size/<int:farm_id>', methods=['POST'])
@login_required
def update_farm_dome_grid_size(farm_id):
    """Update dome grid size for a specific farm"""
    try:
        # Verify farm ownership
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify({'success': False, 'error': 'Farm not found'}), 404
            
        data = request.json
        rows = data.get('rows')
        cols = data.get('cols')
        
        print(f"🔧 Updating Farm {farm_id} ({farm.name}) dome grid size to {rows}x{cols}")
        
        # Validation
        if not rows or not cols:
            return jsonify({'success': False, 'error': 'Rows and columns are required'}), 400
        
        try:
            rows = int(rows)
            cols = int(cols)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid grid size values'}), 400
        
        # Validate size bounds
        if rows < 1 or cols < 1 or rows > 20 or cols > 20:
            return jsonify({'success': False, 'error': 'Grid size must be between 1x1 and 20x20'}), 400
        
        # Check if shrinking would affect existing domes
        existing_domes = Dome.query.filter(
            Dome.farm_id == farm_id,
            Dome.user_id == current_user.id,
            (Dome.grid_row >= rows) | (Dome.grid_col >= cols)
        ).all()
        
        if existing_domes:
            dome_names = [dome.name for dome in existing_domes]
            return jsonify({
                'success': False, 
                'error': f'Cannot shrink grid. Domes would be affected: {", ".join(dome_names)}'
            }), 400
        
        # Update farm-specific dome grid settings
        success = update_grid_settings('dome', rows, cols, current_user.id, farm_id)
        
        if success:
            print(f"✅ Farm {farm_id} ({farm.name}) dome grid size updated to {rows}x{cols}")
            return jsonify({
                'success': True,
                'message': f'Dome grid updated to {rows}x{cols} for {farm.name}',
                'farm_name': farm.name,
                'rows': rows,
                'cols': cols
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to update farm dome grid settings'}), 500
            
    except Exception as e:
        print(f"Error updating farm dome grid size: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
# ✅ NEW: Debug route for farm-specific grid settings
@app.route('/debug/farm_grid_settings/<int:farm_id>')
@login_required
def debug_farm_grid_settings(farm_id):
    """Debug route to check farm-specific grid settings"""
    try:
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return f"<pre>Farm {farm_id} not found</pre>"
            
        # Get all grid settings for this user
        all_settings = GridSettings.query.filter_by(user_id=current_user.id).all()
        
        debug_info = {
            'farm_id': farm_id,
            'farm_name': farm.name,
            'user_id': current_user.id,
            'total_settings': len(all_settings),
            'settings': []
        }
        
        for setting in all_settings:
            debug_info['settings'].append({
                'id': setting.id,
                'type': setting.grid_type,
                'rows': setting.rows,
                'cols': setting.cols,
                'user_id': setting.user_id
            })
        
        # Get current settings for different types
        farm_settings = get_grid_settings('farm', current_user.id)
        global_dome_settings = get_grid_settings('dome', current_user.id)
        farm_dome_settings = get_grid_settings('dome', current_user.id, farm_id)
        
        debug_info['current_farm'] = f"{farm_settings.rows}x{farm_settings.cols}"
        debug_info['current_global_dome'] = f"{global_dome_settings.rows}x{global_dome_settings.cols}"
        debug_info['current_farm_dome'] = f"{farm_dome_settings.rows}x{farm_dome_settings.cols}"
        
        return f"<pre>{json.dumps(debug_info, indent=2)}</pre>"
        
    except Exception as e:
        return f"<pre>Error: {str(e)}</pre>"
# ============= VIEW ROUTES =============
@app.route('/debug/grid_settings')
@login_required
def debug_grid_settings():
    """Debug route to check current grid settings"""
    try:
        grid_settings = GridSettings.query.first()
        all_settings = GridSettings.query.all()
        
        debug_info = {
            'grid_settings_found': grid_settings is not None,
            'current_rows': grid_settings.rows if grid_settings else 'No settings',
            'current_cols': grid_settings.cols if grid_settings else 'No settings',
            'total_grid_settings_records': len(all_settings),
            'all_settings': [{'id': s.id, 'rows': s.rows, 'cols': s.cols} for s in all_settings],
            'user_id': current_user.id
        }
        
        return f"<pre>{json.dumps(debug_info, indent=2)}</pre>"
        
    except Exception as e:
        return f"<pre>Error: {str(e)}</pre>"

@app.route('/profile')
@login_required
def profile():
    """User profile page - updated to show only farm-specific stats"""
    try:
        # Get user statistics
        farms_count = Farm.query.filter_by(user_id=current_user.id).count()
        domes_count = Dome.query.filter_by(user_id=current_user.id).count()  # All domes (farm-specific only)
        trees_count = Tree.query.filter_by(user_id=current_user.id).count()
        
        # Get grid settings for farms only
        farm_grid = get_grid_settings('farm', current_user.id)
        
        return render_template('profile.html',
                             user=current_user,
                             farms_count=farms_count,
                             domes_count=domes_count,
                             trees_count=trees_count,
                             farm_grid=farm_grid)
                             
    except Exception as e:
        print(f"Error in profile route: {str(e)}")
        flash('Error loading profile', 'error')
        return redirect(url_for('farms'))
    
# Update your dome_info route in app.py to handle the count error

@app.route('/dome_info/<int:dome_id>')
@login_required
def dome_info(dome_id):
    """Display dome information page"""
    try:
        print(f"🎯 Dome info route called for dome_id: {dome_id}")
        print(f"🎯 User ID: {current_user.id}")
        
        # Get dome with ownership verification
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            print(f"❌ Dome {dome_id} not found or access denied")
            flash('Dome not found or access denied', 'error')
            return redirect(url_for('farms'))
        
        print(f"✅ Dome found: {dome_id}")
        
        # ✅ FIXED: Safer tree counting
        try:
            tree_count = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).count()
            print(f"✅ Tree count using .count(): {tree_count}")
        except Exception as count_error:
            print(f"⚠️ .count() method failed: {count_error}")
            try:
                trees_list = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
                tree_count = len(trees_list)
                print(f"✅ Tree count using len(): {tree_count}")
            except Exception as len_error:
                print(f"⚠️ len() method also failed: {len_error}")
                tree_count = 0
                print("⚠️ Using fallback count: 0")
        
        # ✅ FIXED: Safer mother/cutting counts
        try:
            mother_count = Tree.query.filter_by(
                dome_id=dome_id, 
                user_id=current_user.id, 
                plant_type='mother'
            ).count()
        except:
            try:
                all_trees = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
                mother_count = len([t for t in all_trees if t.plant_type == 'mother'])
            except:
                mother_count = 0
        
        try:
            cutting_count = Tree.query.filter_by(
                dome_id=dome_id, 
                user_id=current_user.id, 
                plant_type='cutting'
            ).count()
        except:
            try:
                all_trees = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
                cutting_count = len([t for t in all_trees if t.plant_type == 'cutting'])
            except:
                cutting_count = 0
        
        # ✅ FIXED: Safer relationship count
        try:
            relationship_count = PlantRelationship.query.filter_by(dome_id=dome_id, user_id=current_user.id).count()
        except:
            try:
                all_relationships = PlantRelationship.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
                relationship_count = len(all_relationships)
            except:
                relationship_count = 0
        
        # Calculate dome statistics
        total_capacity = dome.internal_rows * dome.internal_cols
        occupancy_rate = (tree_count / total_capacity * 100) if total_capacity > 0 else 0
        
        # Get recent activity (last 30 days)
        thirty_days_ago = datetime.utcnow() - timedelta(days=30)
        try:
            recent_trees = Tree.query.filter(
                Tree.dome_id == dome_id,
                Tree.user_id == current_user.id,
                Tree.created_at >= thirty_days_ago
            ).count()
        except:
            try:
                all_trees = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
                recent_trees = len([t for t in all_trees if t.created_at and t.created_at >= thirty_days_ago])
            except:
                recent_trees = 0
        
        try:
            recent_relationships = PlantRelationship.query.filter(
                PlantRelationship.dome_id == dome_id,
                PlantRelationship.user_id == current_user.id,
                PlantRelationship.cutting_date >= thirty_days_ago
            ).count()
        except:
            try:
                all_relationships = PlantRelationship.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
                recent_relationships = len([r for r in all_relationships if r.cutting_date and r.cutting_date >= thirty_days_ago])
            except:
                recent_relationships = 0
        
        # Prepare dome statistics
        dome_stats = {
            'dome': dome.to_dict(),
            'capacity': {
                'total': total_capacity,
                'occupied': tree_count,
                'available': total_capacity - tree_count,
                'occupancy_rate': round(occupancy_rate, 1)
            },
            'trees': {
                'total': tree_count,
                'mothers': mother_count,
                'cuttings': cutting_count,
                'recent': recent_trees
            },
            'relationships': {
                'total': relationship_count,
                'recent': recent_relationships
            }
        }
        
        print(f"📊 Dome stats calculated: {tree_count} trees, {mother_count} mothers, {cutting_count} cuttings")
        
        # ✅ FIXED: Pass all required variables to template
        return render_template('dome_info.html', 
                             dome=dome, 
                             dome_stats=dome_stats,
                             tree_count=tree_count,  # ✅ ADD THIS
                             mother_count=mother_count,  # ✅ ADD THIS
                             cutting_count=cutting_count,  # ✅ ADD THIS
                             relationship_count=relationship_count,  # ✅ ADD THIS
                             total_capacity=total_capacity,  # ✅ ADD THIS
                             occupancy_rate=round(occupancy_rate, 1),  # ✅ ADD THIS
                             current_user=current_user)
        
    except Exception as e:
        print(f"❌ Error in dome_info route: {str(e)}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        flash('Error loading dome information', 'error')
        return redirect(url_for('farms'))
@app.route('/migrate_tree_breed_complete')
@login_required
def migrate_tree_breed_complete():
    """Complete migration for tree_breed table - adds all missing columns"""
    try:
        migration_log = []
        migration_log.append("🔧 Starting complete TreeBreed table migration...")
        
        with db.engine.connect() as conn:
            # Check if tree_breed table exists
            result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='tree_breed'"))
            table_exists = result.fetchone() is not None
            
            if not table_exists:
                migration_log.append("📋 tree_breed table doesn't exist, creating it...")
                # Create the complete table
                conn.execute(text("""
                    CREATE TABLE tree_breed (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        name VARCHAR(100) UNIQUE NOT NULL,
                        description TEXT,
                        user_id INTEGER NOT NULL,
                        farm_id INTEGER,
                        is_active BOOLEAN DEFAULT 1,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (user_id) REFERENCES user (id) ON DELETE CASCADE,
                        FOREIGN KEY (farm_id) REFERENCES farm (id) ON DELETE CASCADE
                    )
                """))
                migration_log.append("✅ tree_breed table created with all columns")
                
                # Insert default breeds
                default_breeds = [
                    ('Apple', 'Sweet and crispy fruit tree'),
                    ('Orange', 'Citrus fruit tree with vitamin C'),
                    ('Mango', 'Tropical fruit tree with sweet flesh'),
                    ('Banana', 'Tropical fruit tree with potassium-rich fruit'),
                    ('Coconut', 'Palm tree with versatile coconut fruit'),
                    ('Avocado', 'Nutrient-rich fruit tree'),
                    ('Cherry', 'Small stone fruit tree'),
                    ('Peach', 'Soft stone fruit tree'),
                    ('Lemon', 'Sour citrus fruit tree'),
                    ('Lime', 'Small green citrus fruit tree'),
                    ('Papaya', 'Tropical fruit tree with enzyme-rich fruit'),
                    ('Guava', 'Tropical fruit tree with vitamin C')
                ]
                
                for breed_name, description in default_breeds:
                    conn.execute(text("""
                        INSERT INTO tree_breed (name, description, user_id, farm_id, is_active)
                        VALUES (:name, :description, :user_id, :farm_id, 1)
                    """), {
                        'name': breed_name,
                        'description': description,
                        'user_id': current_user.id,
                        'farm_id': 1  # Default to farm 1
                    })
                
                migration_log.append(f"✅ Inserted {len(default_breeds)} default breeds")
                
            else:
                # Check existing columns
                result = conn.execute(text("PRAGMA table_info(tree_breed)"))
                existing_columns = [row[1] for row in result.fetchall()]
                migration_log.append(f"📋 Existing columns: {', '.join(existing_columns)}")
                
                # Define required columns
                required_columns = {
                    'description': 'TEXT',
                    'farm_id': 'INTEGER',
                    'is_active': 'BOOLEAN DEFAULT 1',
                    'created_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP',
                    'updated_at': 'TIMESTAMP DEFAULT CURRENT_TIMESTAMP'
                }
                
                # Add missing columns
                for column_name, column_type in required_columns.items():
                    if column_name not in existing_columns:
                        migration_log.append(f"➕ Adding {column_name} column...")
                        conn.execute(text(f"ALTER TABLE tree_breed ADD COLUMN {column_name} {column_type}"))
                        migration_log.append(f"✅ {column_name} column added")
                    else:
                        migration_log.append(f"ℹ️ {column_name} column already exists")
                
                # Update existing records with default values
                if 'farm_id' not in existing_columns:
                    conn.execute(text("UPDATE tree_breed SET farm_id = 1 WHERE farm_id IS NULL"))
                    migration_log.append("✅ Updated existing records with default farm_id")
                
                if 'is_active' not in existing_columns:
                    conn.execute(text("UPDATE tree_breed SET is_active = 1 WHERE is_active IS NULL"))
                    migration_log.append("✅ Updated existing records with default is_active")
            
            # Commit changes
            conn.commit()
            migration_log.append("💾 Changes committed to database")
            
            # Verify final table structure
            result = conn.execute(text("PRAGMA table_info(tree_breed)"))
            final_columns = [row[1] for row in result.fetchall()]
            migration_log.append(f"🎯 Final table structure: {', '.join(final_columns)}")
            
            # Count records
            result = conn.execute(text("SELECT COUNT(*) FROM tree_breed"))
            record_count = result.fetchone()[0]
            migration_log.append(f"📊 Total breeds in database: {record_count}")
        
        migration_log.append("🎉 TreeBreed migration completed successfully!")
        
        # Create HTML response
        html_response = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>TreeBreed Migration Complete</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 40px; background: #f5f5f5; }}
                .container {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .success {{ color: #4CAF50; }}
                .log {{ background: #f9f9f9; padding: 15px; border-left: 4px solid #4CAF50; margin: 20px 0; }}
                .log pre {{ margin: 0; font-family: monospace; }}
                .button {{ background: #4CAF50; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px; display: inline-block; margin: 10px 5px; }}
                .warning {{ background: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1 class="success">✅ TreeBreed Migration Complete!</h1>
                
                <div class="log">
                    <h3>Migration Log:</h3>
                    <pre>{'<br>'.join(migration_log)}</pre>
                </div>
                
                <h3>What was fixed:</h3>
                <ul>
                    <li>✅ Added missing <code>description</code> column</li>
                    <li>✅ Added missing <code>farm_id</code> column</li>
                    <li>✅ Added missing <code>is_active</code> column</li>
                    <li>✅ Added missing <code>created_at</code> column</li>
                    <li>✅ Added missing <code>updated_at</code> column</li>
                    <li>✅ Inserted default breed data if table was empty</li>
                </ul>
                
                <div class="warning">
                    <h4>⚠️ Important: Restart Your Application</h4>
                    <p>After this migration, please restart your Flask application to ensure all changes take effect:</p>
                    <ol>
                        <li>Stop your current Flask app (Ctrl+C in terminal)</li>
                        <li>Restart with: <code>python app.py</code></li>
                        <li>Try creating a tree again</li>
                    </ol>
                </div>
                
                <div style="margin-top: 30px;">
                    <a href="/farms" class="button">🚜 Go to Farms</a>
                    <a href="/grid/1" class="button">🌱 Test Grid</a>
                    <a href="/api/farm/1/breeds" class="button">🧬 Test Breeds API</a>
                </div>
            </div>
        </body>
        </html>
        """
        
        return html_response
        
    except Exception as e:
        error_msg = str(e)
        migration_log.append(f"❌ Migration failed: {error_msg}")
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head><title>Migration Failed</title></head>
        <body style="font-family: Arial; margin: 40px;">
            <h1 style="color: #f44336;">❌ Migration Failed</h1>
            <p><strong>Error:</strong> {error_msg}</p>
            <p>Please check your database permissions and try again.</p>
            <a href="/farms" style="background: #2196F3; color: white; padding: 12px 24px; text-decoration: none; border-radius: 5px;">🚜 Back to Farms</a>
        </body>
        </html>
        """, 500
@app.route('/api/tree/<int:tree_id>')
@login_required
def api_get_tree(tree_id):
    """API endpoint to get a specific tree"""
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        tree_data = {
            'id': tree.id,
            'name': tree.name,
            'row': tree.row,
            'col': tree.col,
            'life_days': tree.life_days if hasattr(tree, 'life_days') else 0,
            'info': tree.info if hasattr(tree, 'info') else '',
            'image_url': tree.image_url if hasattr(tree, 'image_url') else None,
            'dome_id': tree.dome_id,
            'dome_name': tree.dome.name if hasattr(tree, 'dome') and tree.dome else 'Unknown'
        }
        
        return jsonify({
            'success': True,
            'tree': tree_data
        })
        
    except Exception as e:
        print(f"Error getting tree: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
# ✅ STEP 3A: Get mother trees for selection


# ✅ STEP 3B: Create cutting relationship
@app.route('/api/create_cutting_relationship', methods=['POST'])
@login_required
def create_cutting_relationship():
    """Create a relationship between mother and cutting tree"""
    try:
        data = request.get_json()
        mother_tree_id = data.get('mother_tree_id')
        cutting_tree_id = data.get('cutting_tree_id')
        notes = data.get('notes', '')
        dome_id = data.get('dome_id')
        
        # Validate input
        if not mother_tree_id or not cutting_tree_id:
            return jsonify({'success': False, 'error': 'Mother and cutting tree IDs are required'}), 400
        
        # Verify trees exist and belong to user
        mother_tree = Tree.query.filter_by(id=mother_tree_id, user_id=current_user.id).first()
        cutting_tree = Tree.query.filter_by(id=cutting_tree_id, user_id=current_user.id).first()
        
        if not mother_tree or not cutting_tree:
            return jsonify({'success': False, 'error': 'Trees not found'}), 404
        
        # Verify mother is actually a mother plant
        if mother_tree.plant_type != 'mother':
            return jsonify({'success': False, 'error': 'Selected tree is not a mother plant'}), 400
        
        # Check if cutting already has a mother
        existing_relationship = PlantRelationship.query.filter_by(cutting_tree_id=cutting_tree_id).first()
        if existing_relationship:
            return jsonify({'success': False, 'error': 'Cutting already has a mother plant'}), 400
        
        # Create relationship
        relationship = PlantRelationship(
            mother_tree_id=mother_tree_id,
            cutting_tree_id=cutting_tree_id,
            notes=notes,
            user_id=current_user.id,
            dome_id=dome_id or cutting_tree.dome_id
        )
        
        db.session.add(relationship)
        db.session.commit()
        
        print(f"✅ Created cutting relationship: Mother {mother_tree_id} -> Cutting {cutting_tree_id}")
        
        return jsonify({
            'success': True,
            'message': f'Cutting relationship created: {cutting_tree.name} from {mother_tree.name}',
            'relationship': relationship.to_dict()
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error creating cutting relationship: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ✅ STEP 3C: Get tree relationships (for tree_info.html)
@app.route('/api/tree/<int:tree_id>/relationships')
@login_required
def get_tree_relationships(tree_id):
    """Get tree relationships (mother/cutting) information with accurate cutting counts and debugging"""
    try:
        print(f"🔗 === GETTING RELATIONSHIPS FOR TREE {tree_id} ===")
        
        # Get the tree and verify ownership
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            print(f"❌ Tree {tree_id} not found for user {current_user.id}")
            return jsonify({'success': False, 'error': 'Tree not found'})
        
        print(f"✅ Found tree: {tree.name} (ID: {tree.id})")
        print(f"🔍 Tree plant_type: '{tree.plant_type}'")
        print(f"🔍 Tree mother_plant_id: {getattr(tree, 'mother_plant_id', 'NOT_SET')}")
        
        # Determine tree type
        tree_type = getattr(tree, 'plant_type', 'mother')  # Default to mother if not set
        print(f"🔍 Determined tree_type: '{tree_type}'")
        
        # ✅ ENHANCED: Debug all trees in the dome to see relationships
        all_dome_trees = Tree.query.filter_by(dome_id=tree.dome_id, user_id=current_user.id).all()
        print(f"🔍 All trees in dome {tree.dome_id}:")
        for t in all_dome_trees:
            mother_id = getattr(t, 'mother_plant_id', None)
            print(f"   - Tree {t.id} '{t.name}' | plant_type: '{t.plant_type}' | mother_plant_id: {mother_id}")
        
        # Get mother tree if this is a cutting
        mother_tree = None
        if tree_type == 'cutting':
            mother_plant_id = getattr(tree, 'mother_plant_id', None)
            print(f"🔍 This is a cutting tree, looking for mother with ID: {mother_plant_id}")
            
            if mother_plant_id:
                mother = Tree.query.filter_by(id=mother_plant_id, user_id=current_user.id).first()
                if mother:
                    print(f"✅ Found mother tree: {mother.name} (ID: {mother.id})")
                    
                    # ✅ ENHANCED: Get mother's current cutting count with detailed query
                    mother_cuttings_query = Tree.query.filter_by(
                        mother_plant_id=mother.id, 
                        user_id=current_user.id,
                        plant_type='cutting'
                    )
                    mother_cuttings = mother_cuttings_query.all()
                    mother_cutting_count = len(mother_cuttings)
                    
                    print(f"🔍 Mother {mother.id} has {mother_cutting_count} cuttings:")
                    for cutting in mother_cuttings:
                        print(f"   - Cutting {cutting.id} '{cutting.name}'")
                    
                    mother_tree = {
                        'id': mother.id,
                        'name': mother.name,
                        'breed': mother.breed or '',
                        'internal_row': mother.internal_row,
                        'internal_col': mother.internal_col,
                        'life_days': mother.life_days or 0,
                        'image_url': mother.image_url,
                        'cutting_count': mother_cutting_count,
                        'plant_type': mother.plant_type
                    }
                else:
                    print(f"❌ Mother tree with ID {mother_plant_id} not found")
            else:
                print(f"⚠️ Cutting tree has no mother_plant_id set")
        
        # Get cutting trees if this is a mother
        cutting_trees = []
        if tree_type == 'mother':
            print(f"🔍 This is a mother tree, looking for cutting trees...")
            
            # ✅ ENHANCED: Multiple query approaches to find all cuttings
            
            # Method 1: Direct query by mother_plant_id
            cuttings_method1 = Tree.query.filter_by(
                mother_plant_id=tree_id, 
                user_id=current_user.id,
                plant_type='cutting'
            ).all()
            print(f"🔍 Method 1 (mother_plant_id={tree_id}, plant_type='cutting'): {len(cuttings_method1)} results")
            
            # Method 2: Query by mother_plant_id without plant_type filter
            cuttings_method2 = Tree.query.filter_by(
                mother_plant_id=tree_id, 
                user_id=current_user.id
            ).all()
            print(f"🔍 Method 2 (mother_plant_id={tree_id}, any plant_type): {len(cuttings_method2)} results")
            
            # Method 3: Query all trees and filter manually
            all_trees = Tree.query.filter_by(user_id=current_user.id).all()
            cuttings_method3 = [t for t in all_trees if getattr(t, 'mother_plant_id', None) == tree_id]
            print(f"🔍 Method 3 (manual filter): {len(cuttings_method3)} results")
            
            # Use the method that returns the most results
            if len(cuttings_method3) >= len(cuttings_method1) and len(cuttings_method3) >= len(cuttings_method2):
                cuttings = cuttings_method3
                print(f"✅ Using Method 3 results: {len(cuttings)} cuttings")
            elif len(cuttings_method2) >= len(cuttings_method1):
                cuttings = cuttings_method2
                print(f"✅ Using Method 2 results: {len(cuttings)} cuttings")
            else:
                cuttings = cuttings_method1
                print(f"✅ Using Method 1 results: {len(cuttings)} cuttings")
            
            print(f"🔍 Found {len(cuttings)} cutting trees for mother {tree_id}:")
            for cutting in cuttings:
                print(f"   - Cutting {cutting.id} '{cutting.name}' | plant_type: '{cutting.plant_type}' | mother_plant_id: {getattr(cutting, 'mother_plant_id', 'NOT_SET')}")
            
            # ✅ ENHANCED: Build cutting trees data with comprehensive info
            cutting_trees = []
            for cutting in cuttings:
                try:
                    cutting_data = {
                        'id': cutting.id,
                        'name': cutting.name,
                        'breed': cutting.breed or '',
                        'internal_row': cutting.internal_row,
                        'internal_col': cutting.internal_col,
                        'life_days': cutting.life_days or 0,
                        'cutting_notes': getattr(cutting, 'cutting_notes', ''),
                        'image_url': cutting.image_url,
                        'created_at': cutting.created_at.isoformat() if cutting.created_at else None,
                        'plant_type': cutting.plant_type,
                        'mother_plant_id': getattr(cutting, 'mother_plant_id', None)
                    }
                    cutting_trees.append(cutting_data)
                    print(f"✅ Added cutting data for {cutting.name}")
                except Exception as cutting_error:
                    print(f"❌ Error processing cutting {cutting.id}: {cutting_error}")
                    continue
        
        # Determine available actions
        can_convert_to_mother = tree_type != 'mother'
        can_link_to_mother = tree_type != 'mother' and not mother_tree
        can_unlink_from_mother = tree_type == 'cutting' and mother_tree is not None
        
        # ✅ ENHANCED: Build comprehensive result
        result = {
            'success': True,
            'relationships': {
                'tree': {
                    'id': tree_id,
                    'name': tree.name,
                    'tree_type': tree_type,
                    'plant_type': tree_type
                },
                'is_mother': tree_type == 'mother',
                'is_cutting': tree_type == 'cutting',
                'mother': mother_tree,
                'cuttings': cutting_trees,
                'summary': {
                    'cutting_count': len(cutting_trees),
                    'has_mother': mother_tree is not None,
                    'tree_type': tree_type,
                    'can_convert_to_mother': can_convert_to_mother,
                    'can_link_to_mother': can_link_to_mother,
                    'can_unlink_from_mother': can_unlink_from_mother
                }
            },
            'debug_info': {
                'tree_id': tree_id,
                'tree_name': tree.name,
                'tree_type': tree_type,
                'mother_tree_found': mother_tree is not None,
                'cutting_trees_found': len(cutting_trees),
                'dome_id': tree.dome_id,
                'user_id': current_user.id,
                'query_methods_results': {
                    'method1_strict': len(cuttings_method1) if tree_type == 'mother' else 0,
                    'method2_loose': len(cuttings_method2) if tree_type == 'mother' else 0,
                    'method3_manual': len(cuttings_method3) if tree_type == 'mother' else 0
                } if tree_type == 'mother' else {}
            }
        }
        
        print(f"✅ === RELATIONSHIP QUERY COMPLETE ===")
        print(f"Tree Type: {tree_type}")
        print(f"Is Mother: {tree_type == 'mother'}")
        print(f"Is Cutting: {tree_type == 'cutting'}")
        print(f"Mother Found: {mother_tree is not None}")
        print(f"Cuttings Found: {len(cutting_trees)}")
        print(f"========================================")
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Error getting tree relationships for tree {tree_id}: {e}")
        import traceback
        print(f"❌ Full traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/dome/<int:dome_id>/debug_relationships')
@login_required
def debug_dome_relationships(dome_id):
    """Debug endpoint to check all tree relationships in a dome"""
    try:
        print(f"🔍 === DEBUGGING RELATIONSHIPS IN DOME {dome_id} ===")
        
        # Get all trees in the dome
        trees = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
        print(f"🔍 Found {len(trees)} trees in dome {dome_id}")
        
        relationships_data = {
            'dome_id': dome_id,
            'total_trees': len(trees),
            'mothers': [],
            'cuttings': [],
            'independent': [],
            'broken_relationships': []
        }
        
        for tree in trees:
            tree_data = {
                'id': tree.id,
                'name': tree.name,
                'plant_type': tree.plant_type,
                'mother_plant_id': getattr(tree, 'mother_plant_id', None),
                'position': f"({tree.internal_row}, {tree.internal_col})"
            }
            
            if tree.plant_type == 'mother':
                # Count cuttings for this mother
                cuttings = Tree.query.filter_by(mother_plant_id=tree.id, user_id=current_user.id).all()
                tree_data['cutting_count'] = len(cuttings)
                tree_data['cutting_ids'] = [c.id for c in cuttings]
                relationships_data['mothers'].append(tree_data)
                
            elif tree.plant_type == 'cutting':
                mother_id = getattr(tree, 'mother_plant_id', None)
                if mother_id:
                    mother = Tree.query.filter_by(id=mother_id, user_id=current_user.id).first()
                    tree_data['mother_exists'] = mother is not None
                    tree_data['mother_name'] = mother.name if mother else 'NOT_FOUND'
                    
                    if not mother:
                        relationships_data['broken_relationships'].append(tree_data)
                    else:
                        relationships_data['cuttings'].append(tree_data)
                else:
                    tree_data['mother_exists'] = False
                    tree_data['mother_name'] = 'NO_MOTHER_ID'
                    relationships_data['broken_relationships'].append(tree_data)
                    
            else:
                relationships_data['independent'].append(tree_data)
        
        print(f"🔍 Relationship summary:")
        print(f"   - Mothers: {len(relationships_data['mothers'])}")
        print(f"   - Cuttings: {len(relationships_data['cuttings'])}")
        print(f"   - Independent: {len(relationships_data['independent'])}")
        print(f"   - Broken: {len(relationships_data['broken_relationships'])}")
        
        return jsonify({
            'success': True,
            'relationships_data': relationships_data
        })
        
    except Exception as e:
        print(f"❌ Error debugging dome relationships: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/tree/<int:tree_id>/convert_to_mother', methods=['POST'])
@login_required
def convert_to_mother_tree(tree_id):
    """Convert a tree to a mother tree"""
    try:
        print(f"🌳 Converting tree {tree_id} to mother")
        
        # Get the tree and verify ownership
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'})
        
        # Update plant type
        tree.plant_type = 'mother'
        tree.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        print(f"✅ Tree {tree_id} converted to mother successfully")
        
        return jsonify({
            'success': True,
            'message': f'Tree "{tree.name}" converted to mother tree successfully',
            'tree': tree.to_dict()
        })
        
    except Exception as e:
        print(f"❌ Error converting tree to mother: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tree/<int:tree_id>/link_to_mother', methods=['POST'])
@login_required
def link_to_mother_tree(tree_id):
    """Link a tree to a mother tree as a cutting"""
    try:
        print(f"🔗 Linking tree {tree_id} to mother")
        
        # Get the tree and verify ownership
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'})
        
        data = request.get_json()
        mother_tree_id = data.get('mother_tree_id')
        cutting_notes = data.get('cutting_notes', '')
        
        if not mother_tree_id:
            return jsonify({'success': False, 'error': 'Mother tree ID is required'})
        
        # Verify mother tree exists and belongs to user
        mother_tree = Tree.query.filter_by(
            id=mother_tree_id,
            user_id=current_user.id,
            plant_type='mother'
        ).first()
        
        if not mother_tree:
            return jsonify({'success': False, 'error': 'Invalid mother tree or mother tree not found'})
        
        # Update tree to be a cutting
        tree.plant_type = 'cutting'
        tree.mother_tree_id = mother_tree_id
        tree.cutting_notes = cutting_notes
        tree.updated_at = datetime.utcnow()
        
        # Create plant relationship record
        try:
            # Check if relationship already exists
            existing_relationship = PlantRelationship.query.filter_by(
                cutting_tree_id=tree_id
            ).first()
            
            if existing_relationship:
                # Update existing relationship
                existing_relationship.mother_tree_id = mother_tree_id
                existing_relationship.notes = cutting_notes
                existing_relationship.updated_at = datetime.utcnow()
            else:
                # Create new relationship
                relationship = PlantRelationship(
                    mother_tree_id=mother_tree_id,
                    cutting_tree_id=tree_id,
                    notes=cutting_notes,
                    user_id=current_user.id,
                    dome_id=tree.dome_id,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.session.add(relationship)
                
        except Exception as rel_error:
            print(f"⚠️ Warning: Could not create plant relationship: {rel_error}")
            # Continue without relationship - tree linking is more important
        
        db.session.commit()
        
        print(f"✅ Tree {tree_id} linked to mother {mother_tree_id} successfully")
        
        return jsonify({
            'success': True,
            'message': f'Tree "{tree.name}" linked to mother "{mother_tree.name}" successfully',
            'tree': tree.to_dict(),
            'mother_tree': mother_tree.to_dict()
        })
        
    except Exception as e:
        print(f"❌ Error linking tree to mother: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tree/<int:tree_id>/unlink_from_mother', methods=['POST'])
@login_required
def unlink_from_mother_tree(tree_id):
    """Unlink a cutting tree from its mother"""
    try:
        print(f"🔓 Unlinking tree {tree_id} from mother")
        
        # Get the tree and verify ownership
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'})
        
        # Update tree to be independent
        tree.plant_type = 'mother'  # Convert to independent mother
        tree.mother_tree_id = None
        tree.cutting_notes = ''
        tree.updated_at = datetime.utcnow()
        
        # Remove plant relationship record
        try:
            relationship = PlantRelationship.query.filter_by(
                cutting_tree_id=tree_id
            ).first()
            
            if relationship:
                db.session.delete(relationship)
                print(f"✅ Removed plant relationship for tree {tree_id}")
                
        except Exception as rel_error:
            print(f"⚠️ Warning: Could not remove plant relationship: {rel_error}")
            # Continue - tree unlinking is more important
        
        db.session.commit()
        
        print(f"✅ Tree {tree_id} unlinked from mother successfully")
        
        return jsonify({
            'success': True,
            'message': f'Tree "{tree.name}" unlinked from mother successfully',
            'tree': tree.to_dict()
        })
        
    except Exception as e:
        print(f"❌ Error unlinking tree from mother: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/tree/<int:tree_id>/create_cutting', methods=['POST'])
@login_required
def create_cutting_tree(tree_id):
    """Create a new cutting tree from a mother tree with bidirectional relationship updates"""
    try:
        print(f"✂️ Creating cutting from mother tree {tree_id}")
        
        # Get the mother tree and verify ownership
        mother_tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not mother_tree:
            return jsonify({'success': False, 'error': 'Mother tree not found'})
        
        # Ensure mother tree is actually a mother
        if getattr(mother_tree, 'plant_type', 'mother') != 'mother':
            # Convert to mother if not already
            mother_tree.plant_type = 'mother'
            mother_tree.updated_at = datetime.utcnow()
        
        data = request.get_json()
        cutting_name = data.get('name', '').strip()
        cutting_notes = data.get('cutting_notes', '').strip()
        
        if not cutting_name:
            return jsonify({'success': False, 'error': 'Cutting name is required'})
        
        # Find an empty position in the same dome
        dome = mother_tree.dome
        if not dome:
            return jsonify({'success': False, 'error': 'Mother tree dome not found'})
        
        # Find next available position
        existing_positions = set()
        existing_trees = Tree.query.filter_by(dome_id=dome.id, user_id=current_user.id).all()
        for tree in existing_trees:
            existing_positions.add((tree.internal_row, tree.internal_col))
        
        # Find empty position
        new_row, new_col = None, None
        for row in range(1, (dome.internal_rows or 10) + 1):
            for col in range(1, (dome.internal_cols or 10) + 1):
                if (row, col) not in existing_positions:
                    new_row, new_col = row, col
                    break
            if new_row is not None:
                break
        
        if new_row is None:
            return jsonify({'success': False, 'error': 'No empty positions available in dome'})
        
        # ✅ CRITICAL: Create the cutting tree with proper relationship
        cutting_tree = Tree(
            name=cutting_name,
            breed=mother_tree.breed,  # Inherit breed from mother
            dome_id=dome.id,
            user_id=current_user.id,
            internal_row=new_row,
            internal_col=new_col,
            plant_type='cutting',
            mother_plant_id=tree_id,  # ✅ CRITICAL: Set mother relationship
            cutting_notes=cutting_notes,
            info=f"Cutting from {mother_tree.name}",
            life_days=0,  # Start fresh
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.session.add(cutting_tree)
        db.session.flush()  # Get the new ID
        
        # ✅ CRITICAL: Update mother tree's cutting count
        cutting_count = update_mother_cutting_count(mother_tree)
        
        db.session.commit()
        
        print(f"✅ Cutting tree created: {cutting_tree.id} '{cutting_name}' at ({new_row}, {new_col})")
        print(f"🌳 Mother '{mother_tree.name}' now has {cutting_count} cuttings")
        
        return jsonify({
            'success': True,
            'message': f"Cutting tree '{cutting_name}' created from mother '{mother_tree.name}'",
            'cutting_tree': {
                'id': cutting_tree.id,
                'name': cutting_tree.name,
                'breed': cutting_tree.breed,
                'internal_row': cutting_tree.internal_row,
                'internal_col': cutting_tree.internal_col,
                'cutting_notes': cutting_tree.cutting_notes,
                'mother_plant_id': cutting_tree.mother_plant_id,
                'plant_type': cutting_tree.plant_type
            },
            'mother_tree': {
                'id': mother_tree.id,
                'name': mother_tree.name,
                'cutting_count': cutting_count,
                'plant_type': mother_tree.plant_type
            }
        })
        
    except Exception as e:
        print(f"❌ Error creating cutting tree: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/dome/<int:dome_id>/mother_trees')
@login_required
def get_dome_mother_trees(dome_id):
    """Get all mother trees in a dome for relationship linking"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'})
        
        # Get mother trees
        mother_trees = Tree.query.filter_by(
            dome_id=dome_id, 
            user_id=current_user.id,
            plant_type='mother'
        ).all()
        
        mother_trees_data = [{
            'id': tree.id,
            'name': tree.name,
            'breed': tree.breed or '',
            'internal_row': tree.internal_row,
            'internal_col': tree.internal_col,
            'life_days': tree.life_days or 0,
            'cutting_count': len([t for t in Tree.query.filter_by(mother_plant_id=tree.id).all()])
        } for tree in mother_trees]
        
        return jsonify({
            'success': True,
            'mother_trees': mother_trees_data,
            'count': len(mother_trees_data)
        })
        
    except Exception as e:
        print(f"❌ Error getting mother trees: {e}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/tree_info/<int:tree_id>')
@login_required
def tree_info(tree_id):
    try:
        # Get the tree and verify ownership
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            flash('Tree not found', 'error')
            return redirect(url_for('index'))
        
        # ✅ ADDED: Get the dome object that contains this tree
        dome = Dome.query.filter_by(id=tree.dome_id, user_id=current_user.id).first()
        if not dome:
            flash('Dome not found', 'error')
            return redirect(url_for('index'))
        
        # ✅ DEBUG: Log breed information
        print(f"🧬 Tree {tree_id} info route - Breed: '{tree.breed}' (type: {type(tree.breed)})")
        print(f"   Tree name: '{tree.name}'")
        print(f"   Has breed: {bool(tree.breed)}")
        print(f"   Breed length: {len(tree.breed) if tree.breed else 0}")
        
        timestamp = int(time.time())
        
        # ✅ FIXED: Pass both tree AND dome objects to template
        response = make_response(render_template('tree_info.html', 
                                               tree=tree, 
                                               dome=dome,  # ✅ Added dome object
                                               timestamp=timestamp,
                                               # ✅ DEBUG: Add explicit breed variable
                                               debug_breed=tree.breed or 'NO_BREED'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
        
    except Exception as e:
        print(f"❌ Error in tree_info route: {str(e)}")
        import traceback
        traceback.print_exc()  # ✅ Better error debugging
        flash('An error occurred while loading tree information', 'error')
        return redirect(url_for('index'))
#dome
@app.route('/api/dome/<int:dome_id>/trees', methods=['POST'])
@login_required
def create_tree_api(dome_id):
    """Create a new tree in the specified dome with plant type support"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Validate required fields
        required_fields = ['name', 'internal_row', 'internal_col']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        name = data['name'].strip()
        internal_row = int(data['internal_row'])
        internal_col = int(data['internal_col'])
        
        # ✅ FIXED: Get plant type and validate
        plant_type = data.get('plant_type', 'mother')
        if plant_type not in ['mother', 'cutting']:
            return jsonify({'success': False, 'error': 'Plant type must be "mother" or "cutting"'}), 400
        
        # ✅ FIXED: If it's a cutting, validate mother plant
        mother_plant_id = None
        if plant_type == 'cutting':
            mother_plant_id = data.get('mother_plant_id')  # ✅ CHANGED: from mother_tree_id to mother_plant_id
            if not mother_plant_id:
                return jsonify({'success': False, 'error': 'Mother plant ID is required for cuttings'}), 400
            
            # Verify mother plant exists and belongs to user
            mother_plant = Tree.query.filter_by(
                id=mother_plant_id, 
                user_id=current_user.id,
                plant_type='mother'
            ).first()
            
            if not mother_plant:
                return jsonify({'success': False, 'error': 'Invalid mother plant or mother plant not found'}), 400
        
        # Validate name
        if not name:
            return jsonify({'success': False, 'error': 'Tree name cannot be empty'}), 400
        
        if len(name) > 100:
            return jsonify({'success': False, 'error': 'Tree name too long (max 100 characters)'}), 400
        
        # Validate position bounds
        if internal_row < 0 or internal_row >= dome.internal_rows:
            return jsonify({'success': False, 'error': f'Row {internal_row} out of bounds (0-{dome.internal_rows-1})'}), 400
        
        if internal_col < 0 or internal_col >= dome.internal_cols:
            return jsonify({'success': False, 'error': f'Column {internal_col} out of bounds (0-{dome.internal_cols-1})'}), 400
        
        # Check if position is already occupied
        existing_tree = Tree.query.filter_by(
            dome_id=dome_id,
            internal_row=internal_row,
            internal_col=internal_col
        ).first()
        
        if existing_tree:
            return jsonify({
                'success': False, 
                'error': f'Position ({internal_row}, {internal_col}) already occupied by "{existing_tree.name}"'
            }), 400
        
        # ✅ FIXED: Create new tree with correct field names
        new_tree = Tree(
            name=name,
            dome_id=dome_id,
            internal_row=internal_row,
            internal_col=internal_col,
            info=data.get('info', ''),
            life_days=data.get('life_days', 0),
            user_id=current_user.id,
            image_url=data.get('image_url', ''),
            breed=data.get('breed', ''),
            plant_type=plant_type,
            cutting_notes=data.get('cutting_notes', ''),
            mother_plant_id=mother_plant_id,  # ✅ FIXED: Use correct field name
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        
        db.session.add(new_tree)
        db.session.flush()  # Get the tree ID before commit
        
        # ✅ OPTIONAL: Create PlantRelationship record if you're using that table too
        relationship_created = False
        if plant_type == 'cutting' and mother_plant_id:
            try:
                # Check if you have a PlantRelationship table and want to use it
                if 'PlantRelationship' in globals():
                    relationship = PlantRelationship(
                        mother_tree_id=mother_plant_id,
                        cutting_tree_id=new_tree.id,
                        notes=data.get('cutting_notes', ''),
                        user_id=current_user.id,
                        dome_id=dome_id,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    db.session.add(relationship)
                    relationship_created = True
                    print(f"✅ Created plant relationship: Mother {mother_plant_id} -> Cutting {new_tree.id}")
            except Exception as rel_error:
                print(f"⚠️ Warning: Could not create plant relationship: {rel_error}")
                # Continue without relationship - tree creation is more important
        
        db.session.commit()
        
        # ✅ ENHANCED: Update mother tree's cutting count if this is a cutting
        if plant_type == 'cutting' and mother_plant_id:
            mother_tree = db.session.get(Tree, mother_plant_id)
            if mother_tree:
                update_mother_cutting_count(mother_tree)
                db.session.commit()
                print(f'✅ Updated mother tree "{mother_tree.name}" cutting count')

        # ✅ ENHANCED: Success message
        if plant_type == 'cutting' and mother_plant_id:
            mother_name = db.session.get(Tree, mother_plant_id).name
            print(f'✅ Cutting "{name}" created from mother "{mother_name}" at ({internal_row}, {internal_col}) in dome {dome_id}')
        else:
            print(f'✅ Tree "{name}" created at ({internal_row}, {internal_col}) in dome {dome_id}')
        
        # ✅ FIXED: Return complete tree data
        tree_data = new_tree.to_dict()
        
        # ✅ ENHANCED: Add relationship info if it's a cutting
        if plant_type == 'cutting' and mother_plant_id:
            mother_tree = db.session.get(Tree, mother_plant_id)
            tree_data['mother_plant_name'] = mother_tree.name if mother_tree else 'Unknown'
            tree_data['relationship_created'] = relationship_created
        
        return jsonify({
            'success': True,
            'message': f'{"Cutting" if plant_type == "cutting" else "Tree"} "{name}" created successfully',
            'tree_id': new_tree.id,
            'tree': tree_data
        })
        
    except ValueError as e:
        return jsonify({'success': False, 'error': f'Invalid data format: {str(e)}'}), 400
    except Exception as e:
        print(f'❌ Error creating tree: {str(e)}')
        import traceback
        print(f'❌ Full traceback: {traceback.format_exc()}')
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Failed to create tree: {str(e)}'}), 500

@app.route('/api/save_regular_area/<int:dome_id>', methods=['POST'])
@login_required
def save_regular_area_api(dome_id):
    """Save a regular (selection box) area to the database"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404
        
        data = request.get_json()
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        # Validate required fields
        required_fields = ['name', 'color', 'cells']
        for field in required_fields:
            if field not in data:
                return jsonify({'success': False, 'error': f'Missing required field: {field}'}), 400
        
        name = data['name'].strip()
        color = data['color']
        cells = data['cells']
        
        if not name:
            return jsonify({'success': False, 'error': 'Area name cannot be empty'}), 400
        
        if not cells or len(cells) == 0:
            return jsonify({'success': False, 'error': 'No cells selected'}), 400
        
        # Check for duplicate names
        existing_area = RegularArea.query.filter_by(dome_id=dome_id, name=name).first()
        if existing_area:
            return jsonify({'success': False, 'error': f'Area name "{name}" already exists'}), 400
        
        # Calculate bounds
        rows = [cell['row'] for cell in cells]
        cols = [cell['col'] for cell in cells]
        
        min_row = min(rows)
        max_row = max(rows)
        min_col = min(cols)
        max_col = max(cols)
        
        # Create regular area
        new_area = RegularArea(
            name=name,
            color=color,
            dome_id=dome_id,
            min_row=min_row,
            max_row=max_row,
            min_col=min_col,
            max_col=max_col,
            visible=data.get('visible', True)
        )
        
        db.session.add(new_area)
        db.session.flush()  # Get the ID
        
        # Add cells
        for cell in cells:
            area_cell = RegularAreaCell(
                regular_area_id=new_area.id,
                row=cell['row'],
                col=cell['col']
            )
            db.session.add(area_cell)
        
        # Add tree associations
        tree_ids = data.get('tree_ids', [])
        for tree_id in tree_ids:
            # Use the association table
            tree = db.session.get(Tree, tree_id)
            if tree and tree.dome_id == dome_id:
                new_area.trees.append(tree)
        
        db.session.commit()
        
        print(f'✅ Regular area "{name}" saved with {len(cells)} cells and {len(tree_ids)} trees')
        
        return jsonify({
            'success': True,
            'message': f'Area "{name}" saved successfully',
            'area_id': new_area.id,
            'cell_count': len(cells),
            'tree_count': len(tree_ids)
        })
        
    except Exception as e:
        print(f'❌ Error saving regular area: {str(e)}')
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Failed to save area: {str(e)}'}), 500
# ============= TREE MANAGEMENT CONTINUED =============

@app.route('/update_tree_name/<int:tree_id>', methods=['POST'])
@login_required
def update_tree_name(tree_id):
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify(success=False, error="Tree not found"), 404
        
        data = request.json
        new_name = data.get('name')
        
        if not new_name:
            return jsonify(success=False, error="Name is required"), 400
        
        tree.name = new_name
        db.session.commit()
        
        return jsonify(success=True)
        
    except Exception as e:
        print(f"Error updating tree name: {e}")
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500

@app.route('/update_tree_info/<int:tree_id>', methods=['POST'])
@login_required
def update_tree_info(tree_id):
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify(success=False, error="Tree not found"), 404
        
        data = request.json
        tree.info = data.get('info', tree.info)
        
        db.session.commit()
        return jsonify(success=True)
        
    except Exception as e:
        print(f"Error updating tree info: {e}")
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500





@app.route('/swap_trees', methods=['POST'])
@login_required
def swap_trees():
    """Swap positions of two trees in the grid"""
    try:
        data = request.get_json()
        tree1_id = data.get('tree1_id')
        tree2_id = data.get('tree2_id')
        
        if not tree1_id or not tree2_id:
            return jsonify({
                'success': False,
                'error': 'Both tree IDs are required'
            })
        
        if tree1_id == tree2_id:
            return jsonify({
                'success': False,
                'error': 'Cannot swap tree with itself'
            })
        
        # Get both trees and verify ownership
        tree1 = Tree.query.filter_by(id=tree1_id, user_id=current_user.id).first()
        tree2 = Tree.query.filter_by(id=tree2_id, user_id=current_user.id).first()
        
        if not tree1:
            return jsonify({
                'success': False,
                'error': f'Tree with ID {tree1_id} not found'
            })
        
        if not tree2:
            return jsonify({
                'success': False,
                'error': f'Tree with ID {tree2_id} not found'
            })
        
        # Verify both trees belong to the same dome
        if tree1.dome_id != tree2.dome_id:
            return jsonify({
                'success': False,
                'error': 'Trees must belong to the same dome'
            })
        
        # Store original positions
        tree1_original_row = tree1.internal_row
        tree1_original_col = tree1.internal_col
        tree2_original_row = tree2.internal_row
        tree2_original_col = tree2.internal_col
        
        # Swap positions
        tree1.internal_row = tree2_original_row
        tree1.internal_col = tree2_original_col
        tree2.internal_row = tree1_original_row
        tree2.internal_col = tree1_original_col
        
        # Commit changes to database
        db.session.commit()
        
        print(f"✅ Successfully swapped trees:")
        print(f"   Tree {tree1_id} ({tree1.name}): ({tree1_original_row},{tree1_original_col}) -> ({tree1.internal_row},{tree1.internal_col})")
        print(f"   Tree {tree2_id} ({tree2.name}): ({tree2_original_row},{tree2_original_col}) -> ({tree2.internal_row},{tree2.internal_col})")
        
        return jsonify({
            'success': True,
            'message': 'Trees swapped successfully',
            'tree1': {
                'id': tree1.id,
                'name': tree1.name,
                'internal_row': tree1.internal_row,
                'internal_col': tree1.internal_col
            },
            'tree2': {
                'id': tree2.id,
                'name': tree2.name,
                'internal_row': tree2.internal_row,
                'internal_col': tree2.internal_col
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error swapping trees: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Database error: {str(e)}'
        })
@app.route('/api/dome/<int:dome_id>/trees')
def get_dome_trees_api(dome_id):
    """API endpoint to get all trees for a dome"""
    try:
        dome = Dome.query.get_or_404(dome_id)
        trees = Tree.query.filter_by(dome_id=dome_id).all()
        
        trees_data = []
        for tree in trees:
            tree_data = {
                'id': tree.id,
                'name': tree.name,
                'internal_row': tree.internal_row,
                'internal_col': tree.internal_col,
                'image_url': tree.image_url,
                'dome_id': tree.dome_id
            }
            trees_data.append(tree_data)
        
        return jsonify({
            'success': True,
            'trees': trees_data,
            'count': len(trees_data),
            'dome_id': dome_id
        })
        
    except Exception as e:
        print(f"❌ Error getting trees for dome {dome_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': str(e),
            'trees': [],
            'count': 0
        })

# Also make sure you have the move_tree endpoint
@app.route('/api/trees/<int:tree_id>/move', methods=['POST'])
@login_required
def api_move_tree(tree_id):
    """API endpoint for moving a tree to a new position"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({
                'success': False,
                'error': 'No data provided'
            }), 400
        
        new_row = data.get('internal_row')
        new_col = data.get('internal_col')
        
        # Validate input data
        if new_row is None or new_col is None:
            return jsonify({
                'success': False,
                'error': 'Both internal_row and internal_col are required'
            }), 400
        
        # Validate data types
        try:
            new_row = int(new_row)
            new_col = int(new_col)
        except (ValueError, TypeError):
            return jsonify({
                'success': False,
                'error': 'internal_row and internal_col must be integers'
            }), 400
        
        # Validate position bounds (basic check)
        if new_row < 0 or new_col < 0:
            return jsonify({
                'success': False,
                'error': 'Position coordinates cannot be negative'
            }), 400
        
        # Get the tree and verify ownership
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({
                'success': False,
                'error': f'Tree with ID {tree_id} not found or access denied'
            }), 404
        
        # Get dome to validate bounds
        dome = db.session.get(Dome, tree.dome_id)
        if not dome:
            return jsonify({
                'success': False,
                'error': 'Dome not found'
            }), 404
        
        # Validate position is within dome bounds
        if new_row >= dome.internal_rows or new_col >= dome.internal_cols:
            return jsonify({
                'success': False,
                'error': f'Position ({new_row}, {new_col}) is outside dome bounds ({dome.internal_rows}x{dome.internal_cols})'
            }), 400
        
        # Store original position
        old_row = tree.internal_row
        old_col = tree.internal_col
        
        # Check if target position is already occupied
        existing_tree = Tree.query.filter_by(
            dome_id=tree.dome_id,
            internal_row=new_row,
            internal_col=new_col
        ).first()
        
        swapped = False
        swapped_tree_data = None
        
        if existing_tree and existing_tree.id != tree_id:
            # Swap positions
            existing_tree.internal_row = old_row
            existing_tree.internal_col = old_col
            
            swapped = True
            swapped_tree_data = {
                'id': existing_tree.id,
                'name': existing_tree.name,
                'internal_row': old_row,
                'internal_col': old_col,
                'old_row': new_row,
                'old_col': new_col
            }
            
            print(f"🔄 Swapping trees: {tree.name} ({old_row},{old_col}) <-> {existing_tree.name} ({new_row},{new_col})")
        
        # Move the dragged tree to new position
        tree.internal_row = new_row
        tree.internal_col = new_col
        
        # Commit changes
        db.session.commit()
        
        print(f"✅ Successfully moved tree {tree_id} ({tree.name}): ({old_row},{old_col}) -> ({new_row},{new_col})")
        if swapped:
            print(f"✅ Swapped with tree {existing_tree.id} ({existing_tree.name})")
        
        return jsonify({
            'success': True,
            'message': f'Tree "{tree.name}" moved successfully',
            'swapped': swapped,
            'swapped_tree': swapped_tree_data,
            'tree': {
                'id': tree.id,
                'name': tree.name,
                'internal_row': tree.internal_row,
                'internal_col': tree.internal_col,
                'old_row': old_row,
                'old_col': old_col,
                'dome_id': tree.dome_id
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error moving tree {tree_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Failed to move tree: {str(e)}'
        }), 500

# ============= TREE IMAGE MANAGEMENT =============

@app.route('/upload_tree_image/<int:tree_id>', methods=['POST'])
@login_required
def upload_tree_image(tree_id):
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'})
        
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image file'})
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'})
        
        # Save image as base64 data URL
        image_url = save_image_to_database(file, 'tree', tree_id)
        
        if image_url:
            tree.image_url = image_url
            db.session.commit()
            
            print(f"✅ Tree {tree_id} image uploaded successfully, size: {len(image_url)} chars")
            
            return jsonify({
                'success': True, 
                'message': 'Image uploaded successfully',
                'image_url': image_url
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to process image'})
            
    except Exception as e:
        print(f"❌ Tree image upload error: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)})
@app.route('/migrate_images_to_database')
@login_required
def migrate_images_to_database():
    """One-time migration to convert file URLs to data URLs"""
    try:
        migrated = 0
        
        # Check farms with file-based image URLs
        farms = Farm.query.filter(Farm.image_url.like('/uploads/%')).all()
        for farm in farms:
            # Convert to placeholder or remove
            farm.image_url = None
            migrated += 1
        
        # Check domes with file-based image URLs
        domes = Dome.query.filter(Dome.image_url.like('/uploads/%')).all()
        for dome in domes:
            # Convert to placeholder or remove
            dome.image_url = None
            migrated += 1
        
        # Check trees with file-based image URLs
        trees = Tree.query.filter(Tree.image_url.like('/uploads/%')).all()
        for tree in trees:
            # Convert to placeholder or remove
            tree.image_url = None
            migrated += 1
        
        db.session.commit()
        
        return f"""
        <h2>✅ Image Migration Complete</h2>
        <p>Cleaned up {migrated} old file references.</p>
        <p>All future uploads will be stored in the database.</p>
        <p><a href="/farms">Back to Farms</a></p>
        """
        
    except Exception as e:
        return f"❌ Migration error: {e}"
@app.route('/remove_tree_image/<int:tree_id>', methods=['POST'])
@login_required
def remove_tree_image(tree_id):
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        # Delete image file if exists
        if tree.image_url:
            try:
                filename = tree.image_url.split('/')[-1]
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'trees', filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error deleting tree image file: {e}")
        
        # Remove image URL from database
        tree.image_url = None
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Tree image removed successfully'
        })
        
    except Exception as e:
        print(f"Error removing tree image: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============= QR CODE GENERATION =============

@app.route('/generate_qr/<int:tree_id>', methods=['GET', 'POST'])
@login_required
def generate_qr(tree_id):
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        # Create QR code data - use the full URL
        qr_data = f"{request.url_root}tree_info/{tree_id}"
        
        print(f"🔗 Generating QR code for: {qr_data}")
        
        # ✅ FIXED: Simplified QR code generation without problematic parameters
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # ✅ FIXED: Create QR code image without image_factory parameter
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Resize image for better web display
        qr_img = qr_img.resize((200, 200), Image.LANCZOS)
        
        # Convert to base64 for web display
        img_buffer = io.BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
        
        print(f"✅ QR code generated successfully for tree {tree_id}")
        print(f"📏 Base64 length: {len(img_base64)} characters")
        
        return jsonify({
            'success': True,
            'qr_code': f"data:image/png;base64,{img_base64}",
            'tree_url': qr_data,
            'tree_name': tree.name
        })
        
    except Exception as e:
        print(f"❌ Error generating QR code: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f'QR generation failed: {str(e)}'}), 500
@app.route('/simple_qr/<int:tree_id>')
@login_required
def simple_qr(tree_id):
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'})
        
        # Generate tree URL
        tree_url = url_for('tree_info', tree_id=tree_id, _external=True)
        
        # Generate QR code using qrcode library
        import qrcode
        from io import BytesIO
        import base64
        
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(tree_url)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = BytesIO()
        img.save(buffer, format='PNG')
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'qr_code': f'data:image/png;base64,{img_str}',
            'tree_url': tree_url
        })
        
    except Exception as e:
        print(f"Error generating simple QR: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/api/tree/<int:tree_id>')
@login_required
def get_tree_data(tree_id):
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'})
        
        # ✅ FIXED: Use internal_row/internal_col instead of row/col
        tree_data = {
            'id': tree.id,
            'name': tree.name,
            'image_url': tree.image_url,
            'info': tree.info,
            'life_days': tree.life_days or 0,
            'dome_id': tree.dome_id,
            'internal_row': tree.internal_row,  # ✅ Use internal_row
            'internal_col': tree.internal_col,  # ✅ Use internal_col
            'user_id': tree.user_id,
            'created_at': tree.created_at.isoformat() if tree.created_at else None,
            'updated_at': tree.updated_at.isoformat() if tree.updated_at else None
        }
        
        return jsonify({'success': True, 'tree': tree_data})
        
    except Exception as e:
        print(f"Error getting tree data: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
@app.route('/update_tree/<int:tree_id>', methods=['POST'])
@login_required
def update_tree(tree_id):
    """Update tree information"""
    try:
        data = request.get_json()
        print(f"🌱 Updating tree {tree_id} with data: {data}")
        
        # Validate input data
        if not data:
            return jsonify({'success': False, 'error': 'No data provided'}), 400
        
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        # ✅ IMPROVED: Handle breed field properly (empty string vs None)
        if 'name' in data and data['name']:
            tree.name = data['name'].strip()
        
        if 'breed' in data:
            breed_value = data['breed'].strip() if data['breed'] else None
            tree.breed = breed_value if breed_value else None  # Convert empty string to None
        
        if 'info' in data:
            info_value = data['info'].strip() if data['info'] else None
            tree.info = info_value if info_value else None  # Convert empty string to None
        
        if 'life_days' in data:
            try:
                tree.life_days = int(data['life_days']) if data['life_days'] is not None else 0
            except (ValueError, TypeError):
                tree.life_days = 0
        
        # ✅ IMPROVED: Update timestamp
        tree.updated_at = datetime.utcnow()
        
        db.session.commit()
        print(f"✅ Tree {tree_id} updated successfully")
        
        # ✅ SAFE: Return response without calling to_dict() if it causes issues
        try:
            tree_dict = tree.to_dict()
        except AttributeError as attr_error:
            print(f"⚠️ to_dict() error: {attr_error}")
            # Return manual dict if to_dict() fails
            tree_dict = {
                'id': tree.id,
                'name': tree.name,
                'breed': tree.breed or '',
                'internal_row': tree.internal_row,
                'internal_col': tree.internal_col,
                'info': tree.info or '',
                'life_days': tree.life_days or 0,
                'dome_id': tree.dome_id,
                'user_id': tree.user_id,
                'created_at': tree.created_at.isoformat() if tree.created_at else None,
                'updated_at': tree.updated_at.isoformat() if tree.updated_at else None
            }
        
        return jsonify({
            'success': True,
            'message': 'Tree updated successfully',
            'tree': tree_dict
        })
        
    except Exception as e:
        print(f"❌ Error updating tree: {e}")
        import traceback
        traceback.print_exc()  # ✅ This will show the full error trace
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/qr_image/<int:tree_id>')
@login_required
def qr_image(tree_id):
    """Returns QR code as direct PNG image"""
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            abort(404)
        
        # Create QR code data
        qr_data = f"{request.url_root}tree_info/{tree_id}"
        
        print(f"🖼️ Generating QR image for: {qr_data}")
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=8,
            border=2,
        )
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        # Create QR code image
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Save to BytesIO
        img_buffer = io.BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        print(f"✅ QR image generated successfully")
        
        return send_file(
            img_buffer,
            mimetype='image/png',
            as_attachment=False,
            download_name=f'qr_tree_{tree_id}.png'
        )
        
    except Exception as e:
        print(f"❌ Error generating QR image: {e}")
        abort(500)

@app.route('/test_qr/<int:tree_id>')
@login_required
def test_qr(tree_id):
    """Test route to debug QR code generation"""
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return f"Tree {tree_id} not found", 404
        
        qr_data = f"{request.url_root}tree_info/{tree_id}"
        
        # Test QR code generation
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(qr_data)
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        # Test HTML with embedded QR
        img_buffer = io.BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        img_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>QR Code Test</title>
        </head>
        <body>
            <h1>QR Code Test for Tree: {tree.name}</h1>
            <p>URL: {qr_data}</p>
            <img src="data:image/png;base64,{img_base64}" alt="QR Code" style="border: 1px solid #ccc;">
            <br><br>
            <a href="/tree_info/{tree_id}">Go to Tree Info</a>
        </body>
        </html>
        """
        return html
        
    except Exception as e:
        return f"Error: {str(e)}", 500   
# ============= STATIC FILE SERVING =============
@app.route('/request_password_reset', methods=['GET', 'POST'])
def request_password_reset():
    """Handle password reset requests"""
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            email = data.get('email', '').strip()
            
            if not email:
                return jsonify({'success': False, 'error': 'Email is required'}), 400
            
            user = User.query.filter_by(email=email).first()
            if user:
                try:
                    token = user.generate_reset_token()
                    db.session.commit()
                    
                    # Try to send email
                    try:
                        send_reset_email(email, token, user.username)
                        return jsonify({'success': True, 'message': 'Password reset email sent'})
                    except Exception as e:
                        # If email fails, show the reset link in console
                        reset_url = f"{request.url_root}reset_password?token={token}"
                        print(f"Password reset requested for: {email} ({user.username})")
                        print(f"Reset URL: {reset_url}")
                        print("Email functionality disabled - check console for reset link")
                        return jsonify({'success': True, 'message': 'Password reset link generated (check console)'})
                        
                except Exception as e:
                    print(f"Error generating reset token: {e}")
                    return jsonify({'success': False, 'error': 'Failed to generate reset token'}), 500
            else:
                # Don't reveal if email exists or not for security
                return jsonify({'success': True, 'message': 'If your email is registered, you will receive a reset link'})
                
        except Exception as e:
            print(f"Password reset request error: {e}")
            return jsonify({'success': False, 'error': 'Password reset request failed'}), 500
    
    # GET request - show password reset form
    return render_template('auth/reset_request.html')
@app.route('/fix_image_columns')
def fix_image_columns():
    """Fix image_url columns to handle base64 data"""
    try:
        with db.engine.connect() as conn:
            print("🔧 Fixing image_url column sizes...")
            
            is_postgresql = 'postgresql' in str(db.engine.url)
            fixes_applied = []
            
            if is_postgresql:
                # PostgreSQL version - change VARCHAR(255) to TEXT
                try:
                    # Fix farm table
                    conn.execute(text("ALTER TABLE farm ALTER COLUMN image_url TYPE TEXT"))
                    fixes_applied.append("✅ Fixed farm.image_url column")
                except Exception as e:
                    if "does not exist" in str(e):
                        fixes_applied.append("ℹ️ farm.image_url column doesn't exist")
                    else:
                        fixes_applied.append(f"⚠️ farm.image_url: {str(e)[:100]}")
                
                try:
                    # Fix dome table
                    conn.execute(text("ALTER TABLE dome ALTER COLUMN image_url TYPE TEXT"))
                    fixes_applied.append("✅ Fixed dome.image_url column")
                except Exception as e:
                    if "does not exist" in str(e):
                        fixes_applied.append("ℹ️ dome.image_url column doesn't exist")
                    else:
                        fixes_applied.append(f"⚠️ dome.image_url: {str(e)[:100]}")
                
                try:
                    # Fix tree table
                    conn.execute(text("ALTER TABLE tree ALTER COLUMN image_url TYPE TEXT"))
                    fixes_applied.append("✅ Fixed tree.image_url column")
                except Exception as e:
                    if "does not exist" in str(e):
                        fixes_applied.append("ℹ️ tree.image_url column doesn't exist")
                    else:
                        fixes_applied.append(f"⚠️ tree.image_url: {str(e)[:100]}")
                        
            else:
                # SQLite doesn't support ALTER COLUMN TYPE directly
                fixes_applied.append("ℹ️ SQLite detected - column types are flexible")
            
            conn.commit()
            
            # Clear SQLAlchemy cache
            db.metadata.clear()
            db.metadata.reflect(bind=db.engine)
            
            return f"""
            <h2>✅ Image Column Fix Complete!</h2>
            <ul>
                {''.join([f'<li>{fix}</li>' for fix in fixes_applied])}
            </ul>
            
            <p><a href="/clean_old_images" style="background: #ff9800; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🧹 Next: Clean Old Images</a></p>
            
            <hr>
            <p><small>Step 1 of 2 complete</small></p>
            """
            
    except Exception as e:
        return f"""
        <h2>❌ Image Column Fix Failed</h2>
        <p><strong>Error:</strong> {str(e)}</p>
        <p><a href="/farms">Back to Farms</a></p>
        """
@app.route('/clean_old_images')
def clean_old_images():
    """Clean up old file-based image URLs"""
    try:
        cleaned = 0
        
        # Clean farm images
        farms_with_old_images = Farm.query.filter(
            Farm.image_url.like('/static/uploads/%')
        ).all()
        
        for farm in farms_with_old_images:
            farm.image_url = None
            cleaned += 1
        
        # Clean dome images
        domes_with_old_images = Dome.query.filter(
            Dome.image_url.like('/static/uploads/%')
        ).all()
        
        for dome in domes_with_old_images:
            dome.image_url = None
            cleaned += 1
        
        # Clean tree images
        trees_with_old_images = Tree.query.filter(
            Tree.image_url.like('/static/uploads/%')
        ).all()
        
        for tree in trees_with_old_images:
            tree.image_url = None
            cleaned += 1
        
        db.session.commit()
        
        return f"""
        <h2>✅ Old Images Cleaned!</h2>
        <p>Removed {cleaned} old file references.</p>
        <p>All future uploads will be stored as base64 in the database.</p>
        
        <h3>🎉 Image Upload System Ready!</h3>
        <p><a href="/farms" style="background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🚜 Test Image Upload</a></p>
        
        <hr>
        <p><small>Setup complete - images will now persist through deployments!</small></p>
        """
        
    except Exception as e:
        return f"""
        <h2>❌ Image Cleanup Failed</h2>
        <p><strong>Error:</strong> {str(e)}</p>
        <p><a href="/farms">Back to Farms</a></p>
        """
@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            email = data.get('email', '').strip()
            
            print(f"Password reset request for: {email}")
            
            if not email:
                return jsonify({'success': False, 'error': 'Email address is required'}), 400
            
            # Find user by email
            user = User.query.filter_by(email=email).first()
            
            if user:
                # Generate reset token
                token = user.generate_reset_token()
                db.session.commit()
                
                try:
                    # Send reset email
                    send_reset_email(email, token, user.username)
                    print(f"Password reset email sent to: {email}")
                    
                    return jsonify({
                        'success': True, 
                        'message': f'Password reset instructions have been sent to {email}'
                    })
                    
                except Exception as e:
                    print(f"Failed to send reset email: {e}")
                    return jsonify({
                        'success': False, 
                        'error': 'Failed to send reset email. Please try again later.'
                    }), 500
            else:
                # Don't reveal if email exists or not for security
                print(f"Password reset requested for non-existent email: {email}")
                return jsonify({
                    'success': True, 
                    'message': f'If an account with {email} exists, password reset instructions have been sent.'
                })
                
        except Exception as e:
            print(f"Forgot password error: {e}")
            return jsonify({'success': False, 'error': 'Password reset request failed'}), 500
    
    # GET request - show the forgot password form
    return render_template('auth/forgot_password.html')
@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    """Handle password reset with token"""
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            token = data.get('token')
            new_password = data.get('password')
            confirm_password = data.get('confirm_password')
            
            if not token or not new_password:
                return jsonify({'success': False, 'error': 'Token and password are required'}), 400
            
            if new_password != confirm_password:
                return jsonify({'success': False, 'error': 'Passwords do not match'}), 400
            
            if len(new_password) < 6:
                return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
            
            # Find user with this token
            user = User.query.filter_by(reset_token=token).first()
            if not user or not user.verify_reset_token(token):
                return jsonify({'success': False, 'error': 'Invalid or expired reset token'}), 400
            
            # Update password
            user.set_password(new_password)
            user.clear_reset_token()
            db.session.commit()
            
            return jsonify({'success': True, 'message': 'Password reset successful'})
            
        except Exception as e:
            print(f"Password reset error: {e}")
            return jsonify({'success': False, 'error': 'Password reset failed'}), 500
    
    # GET request - show password reset form
    token = request.args.get('token')
    if not token:
        return render_template('auth/reset_request.html', error='No reset token provided')
    
    # Verify token exists
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.verify_reset_token(token):
        return render_template('auth/reset_request.html', error='Invalid or expired reset token')
    
    return render_template('auth/reset_password.html', token=token)
@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """Serve uploaded files"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/static/uploads/<path:subpath>/<filename>')
def serve_upload(subpath, filename):
    """Serve uploaded files from subdirectories"""
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], subpath, filename)
    if os.path.exists(file_path):
        return send_from_directory(os.path.join(app.config['UPLOAD_FOLDER'], subpath), filename)
    else:
        abort(404)

# ============= DOME GRID SIZE MANAGEMENT =============

@app.route('/update_dome_size/<int:dome_id>', methods=['POST'])
@login_required
def update_dome_size(dome_id):
    try:
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify(success=False, error="Dome not found"), 404
        
        data = request.json
        new_rows = data.get('rows', dome.internal_rows)
        new_cols = data.get('cols', dome.internal_cols)
        
        # Validate size
        if new_rows < 1 or new_cols < 1 or new_rows > 50 or new_cols > 50:
            return jsonify(success=False, error="Grid size must be between 1x1 and 50x50"), 400
        
        # Check if shrinking would affect existing trees
        if new_rows < dome.internal_rows or new_cols < dome.internal_cols:
            affected_trees = Tree.query.filter(
                Tree.dome_id == dome_id,
                Tree.user_id == current_user.id,
                (Tree.row >= new_rows) | (Tree.col >= new_cols)
            ).all()
            
            if affected_trees:
                tree_names = [tree.name for tree in affected_trees]
                return jsonify(
                    success=False, 
                    error=f"Cannot shrink grid. Trees would be affected: {', '.join(tree_names)}"
                ), 400
        
        # Update dome size
        dome.internal_rows = new_rows
        dome.internal_cols = new_cols
        
        db.session.commit()
        
        return jsonify(success=True)
        
    except Exception as e:
        print(f"Error updating dome size: {e}")
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500

# ============= API ENDPOINTS =============

@app.route('/api/trees/<int:dome_id>')
@login_required
def api_get_trees(dome_id):
    """API endpoint to get trees for a specific dome with breed information"""
    try:
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        trees = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
        
        trees_data = []
        for tree in trees:
            tree_data = {
                'id': tree.id,
                'name': tree.name or f'Tree {tree.id}',
                'breed': tree.breed or '',  # ✅ CRITICAL: Add breed field
                'internal_row': tree.internal_row,  # ✅ FIXED: Use internal_row instead of row
                'internal_col': tree.internal_col,  # ✅ FIXED: Use internal_col instead of col
                'life_days': tree.life_days if tree.life_days is not None else 0,
                'info': tree.info or '',
                'image_url': tree.image_url or '',
                'dome_id': tree.dome_id,
                'user_id': tree.user_id,
                'created_at': tree.created_at.isoformat() if tree.created_at else None,
                'updated_at': tree.updated_at.isoformat() if tree.updated_at else None
            }
            trees_data.append(tree_data)
            
            # ✅ DEBUG: Log breed information
            print(f"🌳 API Tree {tree.id} '{tree.name}' - Breed: '{tree.breed or 'None'}'")
        
        print(f"✅ API returning {len(trees_data)} trees for dome {dome_id}")
        
        return jsonify({
            'success': True,
            'trees': trees_data,
            'dome': {
                'id': dome.id,
                'name': dome.name,
                'internal_rows': dome.internal_rows,
                'internal_cols': dome.internal_cols
            },
            'count': len(trees_data)
        })
        
    except Exception as e:
        print(f"❌ Error getting trees for dome {dome_id}: {str(e)}")
        import traceback
        print(f"   Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/stats')
@login_required
def api_stats():
    """API endpoint to get user statistics - farm-specific only"""
    try:
        farms_count = Farm.query.filter_by(user_id=current_user.id).count()
        domes_count = Dome.query.filter_by(user_id=current_user.id).count()
        trees_count = Tree.query.filter_by(user_id=current_user.id).count()
        
        # Get trees by life stage
        young_trees = Tree.query.filter(
            Tree.user_id == current_user.id,
            Tree.life_days < 30
        ).count()
        
        mature_trees = Tree.query.filter(
            Tree.user_id == current_user.id,
            Tree.life_days >= 30,
            Tree.life_days < 90
        ).count()
        
        old_trees = Tree.query.filter(
            Tree.user_id == current_user.id,
            Tree.life_days >= 90
        ).count()
        
        return jsonify({
            'success': True,
            'stats': {
                'farms': farms_count,
                'domes': domes_count,
                'trees': trees_count,
                'young_trees': young_trees,
                'mature_trees': mature_trees,
                'old_trees': old_trees
            }
        })
        
    except Exception as e:
        print(f"Error getting stats: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/migrate_database')
def migrate_database():
    """Manually trigger database migration - REMOVE AFTER USE"""
    try:
        print("🔄 Starting database migration...")
        
        # Check current table structure
        with db.engine.connect() as conn:
            if is_postgresql():
                # ✅ FIXED: PostgreSQL version
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'tree'
                    ORDER BY ordinal_position
                """))
                columns = [row[0] for row in result.fetchall()]
            else:
                # SQLite version
                result = conn.execute(text("PRAGMA table_info(tree)"))
                columns = [row[1] for row in result.fetchall()]
                
            print(f"Current tree table columns: {columns}")
            
            if 'internal_row' not in columns and 'row' in columns:
                print("✅ Migration needed - adding new columns...")
                
                # Add new columns
                conn.execute(text('ALTER TABLE tree ADD COLUMN internal_row INTEGER DEFAULT 0'))
                conn.execute(text('ALTER TABLE tree ADD COLUMN internal_col INTEGER DEFAULT 0'))
                
                # Copy data from old columns to new columns
                conn.execute(text('UPDATE tree SET internal_row = row, internal_col = col'))
                
                # Commit the changes
                conn.commit()
                
                print("✅ Migration completed successfully!")
                return "Migration completed successfully! You can now use the app normally. <a href='/farms'>Go to Farms</a>"
                
            elif 'internal_row' in columns:
                print("✅ Migration already completed")
                return "Migration already completed - new columns exist. <a href='/farms'>Go to Farms</a>"
                
            else:
                print("❌ Unexpected table structure")
                return f"Unexpected table structure. Columns: {columns}"
                
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        return f"Migration failed: {str(e)}"
# ============= ERROR HANDLERS =============
@app.route('/fix_database_for_render')
def fix_database_for_render():
    """Comprehensive database fix for Render deployment - REMOVE AFTER USE"""
    try:
        print("🔧 Starting comprehensive database fix for Render...")
        
        with db.engine.connect() as conn:
            fixes_applied = []
            
            # 1. Check and fix dome table
            if is_postgresql():
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'dome'
                """))
                dome_columns = [row[0] for row in result.fetchall()]
            else:
                result = conn.execute(text("PRAGMA table_info(dome)"))
                dome_columns = [row[1] for row in result.fetchall()]
            
            if 'farm_id' not in dome_columns:
                conn.execute(text('ALTER TABLE dome ADD COLUMN farm_id INTEGER'))
                if is_postgresql():
                    try:
                        conn.execute(text('ALTER TABLE dome ADD CONSTRAINT fk_dome_farm FOREIGN KEY (farm_id) REFERENCES farm(id)'))
                    except:
                        pass  # Constraint might already exist
                fixes_applied.append("Added farm_id column to dome table")
            
            # 2. Check and fix tree table
            if is_postgresql():
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'tree'
                """))
                tree_columns = [row[0] for row in result.fetchall()]
            else:
                result = conn.execute(text("PRAGMA table_info(tree)"))
                tree_columns = [row[1] for row in result.fetchall()]
            
            if 'internal_row' not in tree_columns:
                conn.execute(text('ALTER TABLE tree ADD COLUMN internal_row INTEGER DEFAULT 0'))
                conn.execute(text('ALTER TABLE tree ADD COLUMN internal_col INTEGER DEFAULT 0'))
                
                # Copy data if old columns exist
                if 'row' in tree_columns:
                    conn.execute(text('UPDATE tree SET internal_row = row, internal_col = col'))
                
                fixes_applied.append("Added internal_row/internal_col columns to tree table")
            
            # 3. Check and fix grid_settings table
            if is_postgresql():
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'grid_settings'
                """))
                grid_columns = [row[0] for row in result.fetchall()]
            else:
                result = conn.execute(text("PRAGMA table_info(grid_settings)"))
                grid_columns = [row[1] for row in result.fetchall()]
            
            missing_grid_columns = []
            if 'grid_type' not in grid_columns:
                conn.execute(text("ALTER TABLE grid_settings ADD COLUMN grid_type VARCHAR(20) DEFAULT 'dome'"))
                missing_grid_columns.append("grid_type")
            
            if 'user_id' not in grid_columns:
                conn.execute(text("ALTER TABLE grid_settings ADD COLUMN user_id INTEGER"))
                missing_grid_columns.append("user_id")
            
            if 'created_at' not in grid_columns:
                if is_postgresql():
                    conn.execute(text("ALTER TABLE grid_settings ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                else:
                    conn.execute(text("ALTER TABLE grid_settings ADD COLUMN created_at TIMESTAMP"))
                missing_grid_columns.append("created_at")
            
            if 'updated_at' not in grid_columns:
                if is_postgresql():
                    conn.execute(text("ALTER TABLE grid_settings ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                else:
                    conn.execute(text("ALTER TABLE grid_settings ADD COLUMN updated_at TIMESTAMP"))
                missing_grid_columns.append("updated_at")
            
            if missing_grid_columns:
                fixes_applied.append(f"Added columns to grid_settings: {', '.join(missing_grid_columns)}")
            
            # Commit all changes
            conn.commit()
            
            # 4. Test queries
            test_results = []
            try:
                result = conn.execute(text("SELECT COUNT(*) FROM dome WHERE farm_id IS NULL OR farm_id IS NOT NULL"))
                count = result.fetchone()[0]
                test_results.append(f"✅ Dome farm_id query works: {count} domes")
            except Exception as e:
                test_results.append(f"❌ Dome farm_id query failed: {e}")
            
            try:
                result = conn.execute(text("SELECT COUNT(*) FROM tree WHERE internal_row IS NOT NULL"))
                count = result.fetchone()[0]
                test_results.append(f"✅ Tree internal_row query works: {count} trees")
            except Exception as e:
                test_results.append(f"❌ Tree internal_row query failed: {e}")
            
            # Clear SQLAlchemy cache
            db.metadata.clear()
            db.metadata.reflect(bind=db.engine)
            
            return f"""
            <h2>🔧 Database Fix Results</h2>
            <h3>Fixes Applied:</h3>
            <ul>
                {''.join([f'<li>✅ {fix}</li>' for fix in fixes_applied]) if fixes_applied else '<li>No fixes needed</li>'}
            </ul>
            
            <h3>Test Results:</h3>
            <ul>
                {''.join([f'<li>{result}</li>' for result in test_results])}
            </ul>
            
            <hr>
            <p><strong>Database Type:</strong> {'PostgreSQL' if is_postgresql() else 'SQLite'}</p>
            <p><a href="/farms">🚜 Test Farms Page</a></p>
            <p><a href="/">🏠 Go Home</a></p>
            <hr>
            <p><strong>Note:</strong> Remove this route after the fix works.</p>
            """
                
    except Exception as e:
        print(f"❌ Database fix failed: {e}")
        import traceback
        return f"""
        <h2>❌ Database Fix Failed</h2>
        <p>Error: {str(e)}</p>
        <pre>{traceback.format_exc()}</pre>
        <p><a href="/farms">Try Farms Anyway</a></p>
        """
@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

@app.errorhandler(413)
def too_large(error):
    return jsonify({'success': False, 'error': 'File too large. Maximum size is 16MB.'}), 413

# ============= MAIN APPLICATION ENTRY POINT =============
@app.route('/fix_dome_columns')
def fix_dome_columns():
    """Fix missing created_at and updated_at columns in dome table"""
    try:
        with db.engine.connect() as conn:
            print("🔧 Fixing dome table columns...")
            
            # Check if we're on PostgreSQL (Render) or SQLite (local)
            is_postgresql = 'postgresql' in str(db.engine.url)
            
            if is_postgresql:
                # PostgreSQL version (for Render)
                try:
                    # Add created_at column
                    conn.execute(text("ALTER TABLE dome ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                    print("✅ Added created_at column")
                except Exception as e:
                    if "already exists" in str(e):
                        print("ℹ️ created_at column already exists")
                    else:
                        print(f"⚠️ Error adding created_at: {e}")
                
                try:
                    # Add updated_at column
                    conn.execute(text("ALTER TABLE dome ADD COLUMN updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                    print("✅ Added updated_at column")
                except Exception as e:
                    if "already exists" in str(e):
                        print("ℹ️ updated_at column already exists")
                    else:
                        print(f"⚠️ Error adding updated_at: {e}")
            else:
                # SQLite version (for local development)
                try:
                    conn.execute(text("ALTER TABLE dome ADD COLUMN created_at TIMESTAMP"))
                    conn.execute(text("ALTER TABLE dome ADD COLUMN updated_at TIMESTAMP"))
                    print("✅ Added timestamp columns (SQLite)")
                except Exception as e:
                    print(f"ℹ️ Columns might already exist: {e}")
            
            # Commit the changes
            conn.commit()
            
            # Update existing records with current timestamp
            from datetime import datetime
            current_time = datetime.utcnow()
            try:
                conn.execute(text("UPDATE dome SET created_at = :time WHERE created_at IS NULL"), {"time": current_time})
                conn.execute(text("UPDATE dome SET updated_at = :time WHERE updated_at IS NULL"), {"time": current_time})
                conn.commit()
                print("✅ Updated existing records with timestamps")
            except Exception as e:
                print(f"⚠️ Error updating existing records: {e}")
            
            # Clear SQLAlchemy metadata cache to recognize new columns
            db.metadata.clear()
            db.metadata.reflect(bind=db.engine)
            print("✅ Cleared SQLAlchemy metadata cache")
            
            # Test the fix by trying a simple query
            try:
                result = conn.execute(text("SELECT COUNT(*) FROM dome WHERE created_at IS NOT NULL"))
                count = result.fetchone()[0]
                print(f"✅ Test query successful: {count} domes have timestamps")
                
                return f"""
                <h2>✅ Database Fix Completed!</h2>
                <p><strong>Successfully added missing columns to dome table:</strong></p>
                <ul>
                    <li>✅ created_at column added</li>
                    <li>✅ updated_at column added</li>
                    <li>✅ {count} existing records updated</li>
                    <li>✅ SQLAlchemy cache cleared</li>
                </ul>
                
                <h3>🎉 Your farm system should now work!</h3>
                <p><a href="/farms" style="background: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">🚜 Test Farms Page</a></p>
                
                <hr>
                <p><small>Database: {'PostgreSQL (Render)' if is_postgresql else 'SQLite (Local)'}</small></p>
                <p><small>You can remove this route after confirming everything works.</small></p>
                """
                
            except Exception as test_error:
                return f"""
                <h2>⚠️ Partial Fix Applied</h2>
                <p>Columns were added but test query failed: {test_error}</p>
                <p><a href="/farms">Try Farms Page Anyway</a></p>
                """
                
    except Exception as e:
        print(f"❌ Database fix failed: {e}")
        return f"""
        <h2>❌ Database Fix Failed</h2>
        <p><strong>Error:</strong> {str(e)}</p>
        <p>This might be a permissions issue or the columns might already exist.</p>
        <p><a href="/farms">Try Farms Page</a></p>
        """
@app.route('/bulk_delete_trees', methods=['POST'])
@login_required
def bulk_delete_trees():
    """Delete multiple trees at once"""
    try:
        data = request.get_json()
        tree_ids = data.get('tree_ids', [])
        
        if not tree_ids:
            return jsonify({'success': False, 'error': 'No trees selected'}), 400
        
        # Verify all trees belong to the user
        trees = Tree.query.filter(
            Tree.id.in_(tree_ids),
            Tree.user_id == current_user.id
        ).all()
        
        if len(trees) != len(tree_ids):
            return jsonify({'success': False, 'error': 'Some trees not found or access denied'}), 403
        
        # Delete all selected trees
        deleted_count = 0
        tree_names = []
        
        for tree in trees:
            tree_names.append(tree.name)
            db.session.delete(tree)
            deleted_count += 1
        
        db.session.commit()
        
        print(f"✅ Bulk deleted {deleted_count} trees: {', '.join(tree_names)}")
        
        return jsonify({
            'success': True,
            'message': f'Successfully deleted {deleted_count} trees',
            'deleted_count': deleted_count,
            'deleted_trees': tree_names
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in bulk delete: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/bulk_move_trees', methods=['POST'])
@login_required
def bulk_move_trees():
    """Move multiple trees to new positions"""
    try:
        data = request.get_json()
        moves = data.get('moves', [])  # Array of {tree_id, new_row, new_col}
        
        if not moves:
            return jsonify({'success': False, 'error': 'No moves specified'}), 400
        
        # Verify all trees belong to the user and get dome info
        tree_ids = [move['tree_id'] for move in moves]
        trees = Tree.query.filter(
            Tree.id.in_(tree_ids),
            Tree.user_id == current_user.id
        ).all()
        
        if len(trees) != len(tree_ids):
            return jsonify({'success': False, 'error': 'Some trees not found or access denied'}), 403
        
        # Check for position conflicts
        dome_id = trees[0].dome_id  # Assume all trees are in the same dome
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Validate all new positions are within dome bounds
        for move in moves:
            new_row = move.get('new_row')
            new_col = move.get('new_col')
            
            if (new_row < 0 or new_row >= dome.internal_rows or 
                new_col < 0 or new_col >= dome.internal_cols):
                return jsonify({
                    'success': False, 
                    'error': f'Position ({new_row}, {new_col}) is outside dome bounds'
                }), 400
        
        # Check for conflicts with existing trees (excluding the ones being moved)
        new_positions = [(move['new_row'], move['new_col']) for move in moves]
        existing_trees = Tree.query.filter(
            Tree.dome_id == dome_id,
            Tree.user_id == current_user.id,
            ~Tree.id.in_(tree_ids)  # Exclude trees being moved
        ).all()
        
        for existing_tree in existing_trees:
            pos = (existing_tree.internal_row, existing_tree.internal_col)
            if pos in new_positions:
                return jsonify({
                    'success': False,
                    'error': f'Position ({pos[0]}, {pos[1]}) is occupied by "{existing_tree.name}"'
                }), 400
        
        # Check for conflicts within the moves themselves
        if len(set(new_positions)) != len(new_positions):
            return jsonify({
                'success': False,
                'error': 'Cannot move multiple trees to the same position'
            }), 400
        
        # Apply all moves
        moved_trees = []
        for move in moves:
            tree = next(t for t in trees if t.id == move['tree_id'])
            old_pos = (tree.internal_row, tree.internal_col)
            
            tree.internal_row = move['new_row']
            tree.internal_col = move['new_col']
            
            moved_trees.append({
                'id': tree.id,
                'name': tree.name,
                'old_position': old_pos,
                'new_position': (tree.internal_row, tree.internal_col)
            })
        
        db.session.commit()
        
        print(f"✅ Bulk moved {len(moved_trees)} trees")
        
        return jsonify({
            'success': True,
            'message': f'Successfully moved {len(moved_trees)} trees',
            'moved_trees': moved_trees
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in bulk move: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/bulk_update_trees', methods=['POST'])
@login_required
def bulk_update_trees():
    """Update properties of multiple trees at once"""
    try:
        data = request.get_json()
        tree_ids = data.get('tree_ids', [])
        updates = data.get('updates', {})  # {field: value} pairs
        
        if not tree_ids:
            return jsonify({'success': False, 'error': 'No trees selected'}), 400
        
        if not updates:
            return jsonify({'success': False, 'error': 'No updates specified'}), 400
        
        # Verify all trees belong to the user
        trees = Tree.query.filter(
            Tree.id.in_(tree_ids),
            Tree.user_id == current_user.id
        ).all()
        
        if len(trees) != len(tree_ids):
            return jsonify({'success': False, 'error': 'Some trees not found or access denied'}), 403
        
        # Apply updates to all selected trees
        updated_trees = []
        allowed_fields = ['name', 'info', 'life_days']  # Only allow certain fields
        
        for tree in trees:
            tree_updated = False
            old_values = {}
            
            for field, value in updates.items():
                if field in allowed_fields and hasattr(tree, field):
                    old_values[field] = getattr(tree, field)
                    setattr(tree, field, value)
                    tree_updated = True
            
            if tree_updated:
                tree.updated_at = datetime.utcnow()
                updated_trees.append({
                    'id': tree.id,
                    'name': tree.name,
                    'old_values': old_values,
                    'new_values': {k: v for k, v in updates.items() if k in allowed_fields}
                })
        
        db.session.commit()
        
        print(f"✅ Bulk updated {len(updated_trees)} trees")
        
        return jsonify({
            'success': True,
            'message': f'Successfully updated {len(updated_trees)} trees',
            'updated_trees': updated_trees
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in bulk update: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/get_selected_trees_info', methods=['POST'])
@login_required
def get_selected_trees_info():
    """Get detailed information about selected trees"""
    try:
        data = request.get_json()
        tree_ids = data.get('tree_ids', [])
        
        if not tree_ids:
            return jsonify({'success': False, 'error': 'No trees selected'}), 400
        
        # Get all selected trees
        trees = Tree.query.filter(
            Tree.id.in_(tree_ids),
            Tree.user_id == current_user.id
        ).all()
        
        if len(trees) != len(tree_ids):
            return jsonify({'success': False, 'error': 'Some trees not found or access denied'}), 403
        
        # Compile tree information
        trees_info = []
        total_life_days = 0
        life_stages = {'Young': 0, 'Mature': 0, 'Old': 0}
        
        for tree in trees:
            tree_info = {
                'id': tree.id,
                'name': tree.name,
                'internal_row': tree.internal_row,
                'internal_col': tree.internal_col,
                'life_days': tree.life_days or 0,
                'life_stage': tree.get_life_stage(),
                'info': tree.info or '',
                'has_image': bool(tree.image_url),
                'dome_id': tree.dome_id,
                'created_at': tree.created_at.isoformat() if tree.created_at else None
            }
            trees_info.append(tree_info)
            
            total_life_days += tree.life_days or 0
            life_stages[tree.get_life_stage()] += 1
        
        # Calculate statistics
        avg_life_days = total_life_days / len(trees) if trees else 0
        
        summary = {
            'total_trees': len(trees),
            'total_life_days': total_life_days,
            'average_life_days': round(avg_life_days, 1),
            'life_stages': life_stages,
            'trees_with_images': sum(1 for t in trees_info if t['has_image']),
            'trees_with_info': sum(1 for t in trees_info if t['info'])
        }
        
        return jsonify({
            'success': True,
            'trees': trees_info,
            'summary': summary
        })
        
    except Exception as e:
        print(f"❌ Error getting selected trees info: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/clear_dome_area', methods=['POST'])
@login_required
def clear_dome_area():
    """Clear all trees in a specified area of the dome"""
    try:
        data = request.get_json()
        dome_id = data.get('dome_id')
        start_row = data.get('start_row')
        end_row = data.get('end_row')
        start_col = data.get('start_col')
        end_col = data.get('end_col')
        
        # Validate input
        if not all([dome_id is not None, start_row is not None, end_row is not None, 
                   start_col is not None, end_col is not None]):
            return jsonify({'success': False, 'error': 'Missing required parameters'}), 400
        
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Find trees in the specified area
        trees_to_delete = Tree.query.filter(
            Tree.dome_id == dome_id,
            Tree.user_id == current_user.id,
            Tree.internal_row >= start_row,
            Tree.internal_row <= end_row,
            Tree.internal_col >= start_col,
            Tree.internal_col <= end_col
        ).all()
        
        if not trees_to_delete:
            return jsonify({
                'success': True,
                'message': 'No trees found in the specified area',
                'deleted_count': 0
            })
        
        # Delete trees in the area
        deleted_trees = []
        for tree in trees_to_delete:
            deleted_trees.append({
                'id': tree.id,
                'name': tree.name,
                'position': (tree.internal_row, tree.internal_col)
            })
            db.session.delete(tree)
        
        db.session.commit()
        
        print(f"✅ Cleared {len(deleted_trees)} trees from area ({start_row},{start_col}) to ({end_row},{end_col})")
        
        return jsonify({
            'success': True,
            'message': f'Cleared {len(deleted_trees)} trees from the selected area',
            'deleted_count': len(deleted_trees),
            'deleted_trees': deleted_trees
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error clearing dome area: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/fix_all_tables')
def fix_all_tables():
    """Fix missing columns in all tables"""
    try:
        with db.engine.connect() as conn:
            print("🔧 Fixing all database tables...")
            
            is_postgresql = 'postgresql' in str(db.engine.url)
            fixes_applied = []
            
            # Fix user table
            try:
                if is_postgresql:
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP'))
                    conn.execute(text('ALTER TABLE "user" ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP'))
                else:
                    conn.execute(text("ALTER TABLE user ADD COLUMN created_at TIMESTAMP"))
                    conn.execute(text("ALTER TABLE user ADD COLUMN updated_at TIMESTAMP"))
                fixes_applied.append("✅ Fixed user table")
            except:
                fixes_applied.append("ℹ️ User table already fixed")
            
            # Fix farm table
            try:
                if is_postgresql:
                    conn.execute(text("ALTER TABLE farm ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                    conn.execute(text("ALTER TABLE farm ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                else:
                    conn.execute(text("ALTER TABLE farm ADD COLUMN created_at TIMESTAMP"))
                    conn.execute(text("ALTER TABLE farm ADD COLUMN updated_at TIMESTAMP"))
                fixes_applied.append("✅ Fixed farm table")
            except:
                fixes_applied.append("ℹ️ Farm table already fixed")
            
            # Fix tree table
            try:
                if is_postgresql:
                    conn.execute(text("ALTER TABLE tree ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                    conn.execute(text("ALTER TABLE tree ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"))
                else:
                    conn.execute(text("ALTER TABLE tree ADD COLUMN created_at TIMESTAMP"))
                    conn.execute(text("ALTER TABLE tree ADD COLUMN updated_at TIMESTAMP"))
                fixes_applied.append("✅ Fixed tree table")
            except:
                fixes_applied.append("ℹ️ Tree table already fixed")
            
            conn.commit()
            
            # Clear cache
            db.metadata.clear()
            db.metadata.reflect(bind=db.engine)
            
            return f"""
            <h2>✅ All Tables Fixed!</h2>
            <ul>
                {''.join([f'<li>{fix}</li>' for fix in fixes_applied])}
            </ul>
            <p><a href="/register">🔐 Test Register</a></p>
            <p><a href="/farms">🚜 Test Farms</a></p>
            """
            
    except Exception as e:
        return f"❌ Error: {e}"
@app.route('/api/update_drag_area_color/<int:dome_id>/<int:area_id>', methods=['PUT'])
@login_required
def update_drag_area_color(dome_id, area_id):
    """Update drag area color"""
    try:
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404
        
        # Get the drag area
        drag_area = DragArea.query.filter_by(id=area_id, dome_id=dome_id).first()
        if not drag_area:
            return jsonify({'success': False, 'error': 'Drag area not found'}), 404
        
        data = request.get_json()
        new_color = data.get('color')
        
        if not new_color:
            return jsonify({'success': False, 'error': 'Color is required'}), 400
        
        # Validate hex color format
        if not new_color.startswith('#') or len(new_color) != 7:
            return jsonify({'success': False, 'error': 'Invalid color format. Use #RRGGBB'}), 400
        
        # Update color
        drag_area.color = new_color
        if hasattr(drag_area, 'updated_at'):
            drag_area.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        print(f"✅ Updated drag area {area_id} color to {new_color}")
        
        return jsonify({
            'success': True,
            'message': f'Area color updated to {new_color}',
            'area': {
                'id': drag_area.id,
                'name': drag_area.name,
                'color': drag_area.color
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error updating drag area color: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

#

# ============= ENHANCED COPY/PASTE BACKEND ROUTES =============
# Enhanced Copy/Paste Backend Implementation
# This file contains the enhanced copy/paste functionality that saves clipboard data to the backend

from flask import request, jsonify
from flask_login import login_required, current_user
from models import db, Dome, DragArea, DragAreaTree, Tree, ClipboardData
from datetime import datetime
import json

@app.route('/api/copy_drag_area_to_backend/<int:dome_id>/<int:area_id>', methods=['POST'])
@login_required
def copy_drag_area_to_backend(dome_id, area_id):
    """Copy a drag area to backend clipboard storage with full tree data"""
    try:
        print(f"🔄 Backend copy: Copying drag area {area_id} from dome {dome_id}")
        
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404

        # Get the drag area with all relationships
        drag_area = DragArea.query.filter_by(id=area_id, dome_id=dome_id).first()
        if not drag_area:
            return jsonify({'success': False, 'error': f'Drag area {area_id} not found'}), 404

        print(f"✅ Found drag area: {drag_area.name}")
        print(f"🔍 Drag area details: ID={drag_area.id}, Name='{drag_area.name}', Size={drag_area.width}x{drag_area.height}")
        print(f"🔍 Drag area bounds: ({drag_area.min_row},{drag_area.min_col}) to ({drag_area.max_row},{drag_area.max_col})")

        # ✅ DEBUG: Check if there are any trees in this dome at all
        all_dome_trees = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
        print(f"🔍 Total trees in dome {dome_id}: {len(all_dome_trees)}")
        
        # ✅ DEBUG: Check which trees are within the drag area bounds
        trees_in_bounds = []
        for tree in all_dome_trees:
            in_bounds = (drag_area.min_row <= tree.internal_row <= drag_area.max_row and 
                        drag_area.min_col <= tree.internal_col <= drag_area.max_col)
            print(f"   - Tree {tree.id} '{tree.name}' at ({tree.internal_row},{tree.internal_col}) - In bounds: {in_bounds}")
            if in_bounds:
                trees_in_bounds.append(tree)
        
        print(f"🔍 Trees within drag area bounds: {len(trees_in_bounds)}")

        # Get all trees in this area with full data including relationships
        area_trees = []
        tree_ids = []
        
        # ✅ FIX: Explicitly query drag area trees to avoid lazy loading issues
        drag_area_trees = DragAreaTree.query.filter_by(drag_area_id=area_id).all()
        print(f"🔍 Found {len(drag_area_trees)} drag area tree associations for area {area_id}")
        
        # ✅ FALLBACK: If no associations but trees are in bounds, use the trees in bounds
        if len(drag_area_trees) == 0 and len(trees_in_bounds) > 0:
            print(f"⚠️ No DragAreaTree associations found, but {len(trees_in_bounds)} trees are within bounds")
            print(f"🔄 Using trees within bounds as fallback")
            
            # Create temporary DragAreaTree objects for processing
            drag_area_trees = []
            for tree in trees_in_bounds:
                # Calculate relative position within the drag area
                relative_row = tree.internal_row - drag_area.min_row
                relative_col = tree.internal_col - drag_area.min_col
                
                # Create a temporary DragAreaTree-like object
                temp_dat = type('TempDragAreaTree', (), {
                    'drag_area_id': area_id,
                    'tree_id': tree.id,
                    'tree': tree,
                    'relative_row': relative_row,
                    'relative_col': relative_col
                })()
                
                drag_area_trees.append(temp_dat)
                print(f"   + Added tree {tree.id} '{tree.name}' with relative pos ({relative_row},{relative_col})")
        
        # ✅ DEBUG: Check all DragAreaTree records for this dome
        all_drag_area_trees = DragAreaTree.query.join(DragArea).filter(DragArea.dome_id == dome_id).all()
        print(f"🔍 Total DragAreaTree records in dome {dome_id}: {len(all_drag_area_trees)}")
        for dat in all_drag_area_trees:
            print(f"   - DragAreaTree: area_id={dat.drag_area_id}, tree_id={dat.tree_id}")
        
        # ✅ DEBUG: Check if the drag area has the relationship loaded
        try:
            original_trees = drag_area.drag_area_trees
            print(f"🔍 Original relationship loaded: {len(original_trees)} trees")
        except Exception as rel_error:
            print(f"⚠️ Original relationship not loaded: {rel_error}")
        
        # ✅ DEBUG: Show what's in the DragAreaTree associations
        for i, dat in enumerate(drag_area_trees):
            print(f"🔍 DragAreaTree {i}: area_id={dat.drag_area_id}, tree_id={dat.tree_id}, relative_pos=({dat.relative_row},{dat.relative_col})")
        
        for dat in drag_area_trees:
            tree = dat.tree
            if not tree:
                # ✅ FALLBACK: If tree relationship isn't loaded, query directly
                tree = Tree.query.get(dat.tree_id)
                print(f"🔄 Fallback: Loaded tree {dat.tree_id} directly")
            
            if tree:
                print(f"🌳 Processing tree {tree.id} '{tree.name}' in drag area")
                tree_data = {
                    'id': tree.id,
                    'name': tree.name,
                    'breed': tree.breed or '',
                    'internal_row': tree.internal_row,
                    'internal_col': tree.internal_col,
                    'relative_row': dat.relative_row,
                    'relative_col': dat.relative_col,
                    'image_url': tree.image_url,
                    'info': tree.info or '',
                    'life_days': tree.life_days or 0,
                    'plant_type': getattr(tree, 'plant_type', 'mother'),
                    'mother_plant_id': getattr(tree, 'mother_plant_id', None),
                    'cutting_notes': getattr(tree, 'cutting_notes', ''),
                    'created_at': tree.created_at.isoformat() if tree.created_at else None,
                    'updated_at': tree.updated_at.isoformat() if tree.updated_at else None
                }
                area_trees.append(tree_data)
                tree_ids.append(tree.id)

        print(f"📦 Collected {len(area_trees)} trees from drag area")

        # ✅ NEW: Auto-include cutting trees when copying mother trees
        additional_trees = []
        mother_tree_ids = [t['id'] for t in area_trees if t['plant_type'] == 'mother']
        
        if mother_tree_ids:
            print(f"🔍 Found {len(mother_tree_ids)} mother trees, checking for their cuttings...")
            
            # Find all cutting trees that belong to these mothers (anywhere in the dome)
            for mother_id in mother_tree_ids:
                cutting_trees_for_mother = Tree.query.filter_by(
                    dome_id=dome_id,
                    user_id=current_user.id,
                    mother_plant_id=mother_id,
                    plant_type='cutting'
                ).all()
                
                print(f"��� Mother {mother_id} has {len(cutting_trees_for_mother)} cutting trees")
                
                for cutting_tree in cutting_trees_for_mother:
                    # Check if this cutting is already in the area
                    already_included = any(t['id'] == cutting_tree.id for t in area_trees)
                    if not already_included:
                        # Add the cutting tree to the copy
                        cutting_data = {
                            'id': cutting_tree.id,
                            'name': cutting_tree.name,
                            'breed': cutting_tree.breed or '',
                            'internal_row': cutting_tree.internal_row,
                            'internal_col': cutting_tree.internal_col,
                            'relative_row': 0,  # Will be calculated later
                            'relative_col': 0,  # Will be calculated later
                            'image_url': cutting_tree.image_url,
                            'info': cutting_tree.info or '',
                            'life_days': cutting_tree.life_days or 0,
                            'plant_type': 'cutting',
                            'mother_plant_id': cutting_tree.mother_plant_id,
                            'cutting_notes': getattr(cutting_tree, 'cutting_notes', ''),
                            'created_at': cutting_tree.created_at.isoformat() if cutting_tree.created_at else None,
                            'updated_at': cutting_tree.updated_at.isoformat() if cutting_tree.updated_at else None,
                            'auto_included': True  # Mark as auto-included
                        }
                        additional_trees.append(cutting_data)
                        tree_ids.append(cutting_tree.id)
                        print(f"➕ Auto-included cutting '{cutting_tree.name}' (ID: {cutting_tree.id})")

        # Add the additional trees to the main list
        area_trees.extend(additional_trees)
        print(f"📦 Total trees after auto-inclusion: {len(area_trees)} (added {len(additional_trees)} cuttings)")

        # Analyze relationships within the copied trees
        mother_trees = [t for t in area_trees if t['plant_type'] == 'mother']
        cutting_trees = [t for t in area_trees if t['plant_type'] == 'cutting']
        
        print(f"🔍 RELATIONSHIP DEBUG: Found {len(mother_trees)} mothers, {len(cutting_trees)} cuttings")
        for tree in area_trees:
            print(f"🔍 Tree {tree['id']} '{tree['name']}' - Type: {tree['plant_type']} - Mother ID: {tree.get('mother_plant_id', 'None')}")
        
        # Find relationships that will be preserved (both mother and cutting in the area)
        preserved_relationships = []
        broken_relationships = []
        
        for cutting in cutting_trees:
            print(f"🔍 Analyzing cutting {cutting['id']} '{cutting['name']}' - Mother ID: {cutting.get('mother_plant_id', 'None')}")
            if cutting['mother_plant_id']:
                mother_in_area = any(t['id'] == cutting['mother_plant_id'] for t in area_trees)
                print(f"🔍 Mother {cutting['mother_plant_id']} in area: {mother_in_area}")
                if mother_in_area:
                    preserved_relationships.append({
                        'mother_id': cutting['mother_plant_id'],
                        'cutting_id': cutting['id']
                    })
                    print(f"✅ Preserved relationship: Cutting {cutting['id']} -> Mother {cutting['mother_plant_id']}")
                else:
                    broken_relationships.append({
                        'cutting_id': cutting['id'],
                        'original_mother_id': cutting['mother_plant_id']
                    })
                    print(f"💔 Broken relationship: Cutting {cutting['id']} -> Mother {cutting['mother_plant_id']} (not in area)")
            else:
                print(f"ℹ️ Cutting {cutting['id']} has no mother relationship")

        # Get breed information
        breeds = list(set([tree['breed'] for tree in area_trees if tree['breed']]))
        
        # Create comprehensive clipboard data
        clipboard_data = {
            'id': drag_area.id,
            'name': drag_area.name,
            'type': 'dragArea',
            'color': drag_area.color,
            'width': drag_area.width,
            'height': drag_area.height,
            'min_row': drag_area.min_row,
            'max_row': drag_area.max_row,
            'min_col': drag_area.min_col,
            'max_col': drag_area.max_col,
            'trees': area_trees,
            'tree_count': len(area_trees),
            'tree_ids': tree_ids,
            'visible': drag_area.visible,
            'copied_at': datetime.utcnow().isoformat(),
            'source_dome_id': dome_id,
            'source_dome_name': dome.name,
            'source_farm_id': dome.farm_id,
            'clipboard_version': '3.0',
            'clipboard_source': 'backend_enhanced',
            'summary': {
                'total_trees': len(area_trees),
                'breeds': breeds,
                'breed_count': len(breeds),
                'has_images': len([tree for tree in area_trees if tree['image_url']]),
                'plant_relationships': {
                    'mother_trees': len(mother_trees),
                    'cutting_trees': len(cutting_trees),
                    'preserved_relationships': len(preserved_relationships),
                    'broken_relationships': len(broken_relationships),
                    'complete_relationships': preserved_relationships,
                    'broken_relationships_detail': broken_relationships
                }
            },
            'relationship_metadata': {
                'mother_cutting_pairs': preserved_relationships,
                'broken_relationships': broken_relationships,
                'total_relationships': len(preserved_relationships) + len(broken_relationships)
            }
        }

        # Save to backend clipboard storage
        # First, clear any existing clipboard data for this user
        ClipboardData.query.filter_by(user_id=current_user.id).delete()
        
        # Create new clipboard entry
        clipboard_entry = ClipboardData(
            user_id=current_user.id,
            clipboard_type='drag_area',
            name=clipboard_data['name'],
            source_dome_id=dome_id,
            source_farm_id=dome.farm_id,
            clipboard_content=json.dumps(clipboard_data),
            width=clipboard_data['width'],
            height=clipboard_data['height'],
            tree_count=clipboard_data['tree_count'],
            created_at=datetime.utcnow()
        )
        
        db.session.add(clipboard_entry)
        db.session.commit()

        print(f"✅ Drag area '{clipboard_data['name']}' saved to backend clipboard")
        print(f"   📏 Area size: {clipboard_data['width']}x{clipboard_data['height']}")
        print(f"   🌳 Trees: {len(area_trees)}")
        print(f"   🧬 Breeds: {len(breeds)} ({', '.join(breeds) if breeds else 'None'})")
        print(f"   🔗 Relationships: {len(preserved_relationships)} preserved, {len(broken_relationships)} broken")
        print(f"   💾 Clipboard entry ID: {clipboard_entry.id}")
        print(f"   ���� Clipboard data preview: {clipboard_data['name']} - {clipboard_data['tree_count']} trees")

        return jsonify({
            'success': True,
            'clipboard_data': clipboard_data,
            'message': f'Drag area "{drag_area.name}" copied to backend clipboard',
            'stats': {
                'trees_copied': len(area_trees),
                'breeds_found': len(breeds),
                'relationships_preserved': len(preserved_relationships),
                'relationships_broken': len(broken_relationships)
            }
        })

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in copy_drag_area_to_backend: {str(e)}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/paste_drag_area_from_backend/<int:dome_id>', methods=['POST'])
@login_required
def paste_drag_area_from_backend(dome_id):
    """Paste a drag area from backend clipboard storage with orphaned relationship handling"""
    try:
        print(f"📋 Backend paste: Pasting to dome {dome_id}")

        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404

        # Get clipboard data from backend
        clipboard_entry = ClipboardData.query.filter_by(
            user_id=current_user.id,
            clipboard_type='drag_area'
        ).order_by(ClipboardData.created_at.desc()).first()

        if not clipboard_entry:
            return jsonify({'success': False, 'error': 'No clipboard data found'}), 400

        # Parse clipboard data
        try:
            clipboard_data = json.loads(clipboard_entry.clipboard_content)
        except json.JSONDecodeError:
            return jsonify({'success': False, 'error': 'Invalid clipboard data format'}), 400

        # Get paste parameters
        data = request.get_json()
        paste_row = data.get('paste_row', 0)
        paste_col = data.get('paste_col', 0)
        new_name = data.get('name', f"{clipboard_data.get('name', 'Pasted Area')} Copy")
        create_trees = data.get('create_trees', True)
        
        # ✅ NEW: Get orphan handling parameters
        # Check both direct orphan_handling and relationship_metadata.orphan_handling
        orphan_handling = data.get('orphan_handling', {})
        relationship_metadata = data.get('relationship_metadata', {})
        if not orphan_handling and relationship_metadata.get('orphan_handling'):
            orphan_handling = relationship_metadata.get('orphan_handling', {})
        
        # ✅ FIX: Ensure orphan_handling is never None
        if orphan_handling is None:
            orphan_handling = {}
        
        orphan_mode = orphan_handling.get('mode', 'preserve_original') if orphan_handling else 'preserve_original'
        orphaned_cuttings_info = orphan_handling.get('orphaned_cuttings', []) if orphan_handling else []
        
        # ✅ Map frontend mode names to backend mode names
        mode_mapping = {
            'preserve_original': 'preserve_original',
            'find_mothers': 'link_to_existing',
            'link_to_existing': 'link_to_existing',
            'convert_to_independent': 'convert_to_independent',
            'keep_orphaned': 'keep_orphaned'
        }
        orphan_mode = mode_mapping.get(orphan_mode, 'preserve_original')  # Default to preserve original

        print(f"📋 Pasting '{new_name}' at ({paste_row}, {paste_col})")
        print(f"🔗 Orphan handling mode: {orphan_mode}")
        if orphaned_cuttings_info:
            print(f"⚠️ Orphaned cuttings to handle: {len(orphaned_cuttings_info)}")

        # Check for name conflicts
        existing_area = DragArea.query.filter_by(dome_id=dome_id, name=new_name).first()
        if existing_area:
            # Auto-generate unique name
            counter = 1
            base_name = new_name
            while existing_area:
                new_name = f"{base_name} ({counter})"
                existing_area = DragArea.query.filter_by(dome_id=dome_id, name=new_name).first()
                counter += 1

        # Calculate new boundaries
        width = clipboard_data.get('width', 1)
        height = clipboard_data.get('height', 1)
        new_min_row = paste_row
        new_max_row = paste_row + height - 1
        new_min_col = paste_col
        new_max_col = paste_col + width - 1

        # Validate boundaries
        if new_max_row >= dome.internal_rows or new_max_col >= dome.internal_cols:
            return jsonify({
                'success': False,
                'error': f'Area would extend outside grid boundaries ({dome.internal_rows}x{dome.internal_cols})'
            }), 400

        # Create new drag area
        new_area = DragArea(
            name=new_name,
            color=clipboard_data.get('color', '#007bff'),
            min_row=new_min_row,
            max_row=new_max_row,
            min_col=new_min_col,
            max_col=new_max_col,
            width=width,
            height=height,
            dome_id=dome_id,
            visible=True,
            created_at=datetime.utcnow()
        )

        db.session.add(new_area)
        db.session.flush()  # Get the new area ID

        print(f"✅ Created new drag area: {new_area.name} (ID: {new_area.id})")

        # Create trees if requested
        new_trees = []
        old_to_new_tree_mapping = {}
        
        if create_trees and clipboard_data.get('trees'):
            trees_data = clipboard_data['trees']
            
            # Calculate position offsets
            original_min_row = clipboard_data.get('min_row', 0)
            original_min_col = clipboard_data.get('min_col', 0)
            row_offset = paste_row - original_min_row
            col_offset = paste_col - original_min_col

            print(f"🌳 Creating {len(trees_data)} trees with offset ({row_offset}, {col_offset})")

            # First pass: Create all trees without relationships
            for tree_data in trees_data:
                new_row = tree_data['internal_row'] + row_offset
                new_col = tree_data['internal_col'] + col_offset
                
                # Skip if position is occupied
                existing_tree = Tree.query.filter_by(
                    dome_id=dome_id,
                    internal_row=new_row,
                    internal_col=new_col
                ).first()
                
                if existing_tree:
                    print(f"⚠️ Position ({new_row}, {new_col}) occupied, skipping tree '{tree_data['name']}'")
                    continue

                new_tree = Tree(
                    name=tree_data['name'],
                    breed=tree_data.get('breed', ''),
                    internal_row=new_row,
                    internal_col=new_col,
                    life_days=tree_data.get('life_days', 0),
                    info=tree_data.get('info', ''),
                    image_url=tree_data.get('image_url', ''),
                    dome_id=dome_id,
                    user_id=current_user.id,
                    plant_type=tree_data.get('plant_type', 'mother'),
                    cutting_notes=tree_data.get('cutting_notes', ''),
                    created_at=datetime.utcnow()
                )

                db.session.add(new_tree)
                db.session.flush()  # Get the new tree ID
                
                # Map old ID to new ID for relationship restoration
                old_to_new_tree_mapping[tree_data['id']] = new_tree.id
                new_trees.append(new_tree)

                # Create drag area tree association
                relative_row = tree_data.get('relative_row', new_row - paste_row)
                relative_col = tree_data.get('relative_col', new_col - paste_col)
                
                drag_area_tree = DragAreaTree(
                    drag_area_id=new_area.id,
                    tree_id=new_tree.id,
                    relative_row=relative_row,
                    relative_col=relative_col,
                    created_at=datetime.utcnow()
                )
                db.session.add(drag_area_tree)

                print(f"🌳 Created tree '{new_tree.name}' at ({new_row}, {new_col})")

            # Second pass: Handle relationships based on orphan handling mode
            relationships_created = 0
            independent_cuttings = 0
            orphaned_cuttings_handled = 0
            linked_to_existing_mothers = 0
            transferred_cuttings = 0
            
            # Find all mother trees that were pasted
            mother_trees_pasted = []
            cutting_trees_pasted = []
            
            for tree_data in trees_data:
                if tree_data.get('plant_type') == 'mother' and tree_data['id'] in old_to_new_tree_mapping:
                    mother_trees_pasted.append({
                        'old_id': tree_data['id'],
                        'new_id': old_to_new_tree_mapping[tree_data['id']],
                        'name': tree_data['name']
                    })
                elif tree_data.get('plant_type') == 'cutting' and tree_data['id'] in old_to_new_tree_mapping:
                    cutting_trees_pasted.append({
                        'old_id': tree_data['id'],
                        'new_id': old_to_new_tree_mapping[tree_data['id']],
                        'name': tree_data['name'],
                        'original_mother_id': tree_data.get('mother_plant_id')
                    })
            
            # ✅ NEW: Handle cutting tree transfers when mother trees are pasted
            if mother_trees_pasted and cutting_trees_pasted:
                print(f"🔄 Processing cutting tree transfers for {len(mother_trees_pasted)} mother trees...")
                
                for mother in mother_trees_pasted:
                    # Find all cutting trees that belong to this mother
                    mother_cuttings = [c for c in cutting_trees_pasted if c['original_mother_id'] == mother['old_id']]
                    
                    if mother_cuttings:
                        print(f"🔄 Transferring {len(mother_cuttings)} cutting trees from old mother {mother['old_id']} to new mother {mother['new_id']}")
                        
                        for cutting in mother_cuttings:
                            cutting_tree = Tree.query.get(cutting['new_id'])
                            if cutting_tree:
                                # Update cutting to point to new mother
                                cutting_tree.mother_plant_id = mother['new_id']
                                cutting_tree.plant_type = 'cutting'
                                relationships_created += 1
                                transferred_cuttings += 1
                                print(f"✅ Transferred cutting '{cutting['name']}' to new mother '{mother['name']}'")
                        
                        # ✅ CRITICAL: Remove cutting trees from old mother (always, regardless of dome)
                        old_mother_id = mother['old_id']
                        print(f"🗑️ Removing {len(mother_cuttings)} cutting trees from old mother {old_mother_id}")
                        
                        # Find all cutting trees that belong to the old mother (anywhere in the system)
                        old_cuttings_to_remove = Tree.query.filter_by(
                            mother_plant_id=old_mother_id,
                            plant_type='cutting',
                            user_id=current_user.id
                        ).all()
                        
                        print(f"🔍 Found {len(old_cuttings_to_remove)} cutting trees linked to old mother {old_mother_id}")
                        
                        for old_cutting in old_cuttings_to_remove:
                            # Check if this cutting was copied (by checking if its ID is in the copied list)
                            cutting_was_copied = any(c['old_id'] == old_cutting.id for c in cutting_trees_pasted)
                            if cutting_was_copied:
                                # Remove the cutting tree from the old mother
                                old_cutting.mother_plant_id = None
                                old_cutting.plant_type = 'mother'  # Convert to independent
                                print(f"🗑️ Removed cutting '{old_cutting.name}' (ID: {old_cutting.id}) from old mother and converted to independent")
                            else:
                                print(f"ℹ️ Keeping cutting '{old_cutting.name}' (ID: {old_cutting.id}) - not in copied list")
                        
                        print(f"✅ Completed transfer of {len(mother_cuttings)} cutting trees from old mother {old_mother_id}")
                        
                        # ✅ FORCE: Update the old mother's cutting count to reflect the changes
                        old_mother_tree = Tree.query.get(old_mother_id)
                        if old_mother_tree:
                            # Force update the cutting count for the old mother
                            remaining_cuttings = Tree.query.filter_by(
                                mother_plant_id=old_mother_id,
                                plant_type='cutting',
                                user_id=current_user.id
                            ).count()
                            print(f"🔄 Old mother '{old_mother_tree.name}' now has {remaining_cuttings} cutting trees remaining")
            
            print(f"🌳 Found {len(mother_trees_pasted)} mother trees and {len(cutting_trees_pasted)} cutting trees")
            
            # Create a mapping of orphaned cutting IDs for quick lookup
            orphaned_cutting_ids = set()
            orphan_handling_map = {}
            for orphan_info in orphaned_cuttings_info:
                orphaned_cutting_ids.add(orphan_info.get('cutting_id'))
                orphan_handling_map[orphan_info.get('cutting_id')] = orphan_info
            
            # Get available mother trees in the destination dome for linking
            available_mothers_in_dome = []
            if orphan_mode == 'link_to_existing':
                available_mothers_in_dome = Tree.query.filter_by(
                    dome_id=dome_id,
                    user_id=current_user.id,
                    plant_type='mother'
                ).all()
                print(f"🔍 Found {len(available_mothers_in_dome)} available mother trees in destination dome")
            
            # For each cutting tree, handle relationships based on orphan mode
            for cutting in cutting_trees_pasted:
                cutting_tree = Tree.query.get(cutting['new_id'])
                if not cutting_tree:
                    continue
                
                is_orphaned = cutting['old_id'] in orphaned_cutting_ids
                
                if is_orphaned:
                    print(f"⚠️ Handling orphaned cutting: '{cutting['name']}' (mode: {orphan_mode})")
                    
                    if orphan_mode == 'preserve_original':
                        # Preserve the original mother relationship (even if mother is in different dome)
                        original_mother_id = cutting.get('original_mother_id')
                        if original_mother_id:
                            cutting_tree.mother_plant_id = original_mother_id
                            cutting_tree.plant_type = 'cutting'
                            relationships_created += 1
                            orphaned_cuttings_handled += 1
                            print(f"🔄 Preserved original relationship: cutting '{cutting['name']}' -> mother ID {original_mother_id}")
                        else:
                            # No original mother ID, convert to independent
                            cutting_tree.mother_plant_id = None
                            cutting_tree.plant_type = 'mother'
                            independent_cuttings += 1
                            orphaned_cuttings_handled += 1
                            print(f"🌱 No original mother ID, converted '{cutting['name']}' to independent")
                        
                    elif orphan_mode == 'convert_to_independent':
                        # Convert to independent mother tree
                        cutting_tree.mother_plant_id = None
                        cutting_tree.plant_type = 'mother'
                        independent_cuttings += 1
                        orphaned_cuttings_handled += 1
                        print(f"🌱 Converted orphaned cutting '{cutting['name']}' to independent mother")
                        
                    elif orphan_mode == 'link_to_existing' and available_mothers_in_dome:
                        # Link to an existing mother tree in the dome
                        # Try to find a mother with the same breed first
                        suitable_mother = None
                        cutting_breed = cutting_tree.breed or ''
                        
                        for mother in available_mothers_in_dome:
                            if mother.breed == cutting_breed:
                                suitable_mother = mother
                                break
                        
                        # If no breed match, use the first available mother
                        if not suitable_mother and available_mothers_in_dome:
                            suitable_mother = available_mothers_in_dome[0]
                        
                        if suitable_mother:
                            cutting_tree.mother_plant_id = suitable_mother.id
                            cutting_tree.plant_type = 'cutting'
                            relationships_created += 1
                            linked_to_existing_mothers += 1
                            orphaned_cuttings_handled += 1
                            print(f"🔗 Linked orphaned cutting '{cutting['name']}' to existing mother '{suitable_mother.name}'")
                        else:
                            # No suitable mother found, convert to independent
                            cutting_tree.mother_plant_id = None
                            cutting_tree.plant_type = 'mother'
                            independent_cuttings += 1
                            orphaned_cuttings_handled += 1
                            print(f"🌱 No suitable mother found, converted '{cutting['name']}' to independent")
                            
                    else:  # keep_orphaned mode or fallback
                        # Keep as orphaned cutting (broken relationship)
                        cutting_tree.mother_plant_id = cutting['original_mother_id']  # Keep original reference
                        cutting_tree.plant_type = 'cutting'
                        orphaned_cuttings_handled += 1
                        print(f"⚠️ Kept '{cutting['name']}' as orphaned cutting (broken relationship)")
                        
                else:
                    # Not orphaned - handle normal relationship restoration
                    # Check if the original mother was also pasted
                    original_mother_pasted = None
                    if cutting['original_mother_id']:
                        for mother in mother_trees_pasted:
                            if mother['old_id'] == cutting['original_mother_id']:
                                original_mother_pasted = mother
                                break
                    
                    if original_mother_pasted:
                        # Link to the original mother that was pasted
                        cutting_tree.mother_plant_id = original_mother_pasted['new_id']
                        relationships_created += 1
                        print(f"🔗 Linked cutting '{cutting['name']}' to original mother '{original_mother_pasted['name']}'")
                    elif mother_trees_pasted:
                        # Link to the first available mother tree that was pasted
                        first_mother = mother_trees_pasted[0]
                        cutting_tree.mother_plant_id = first_mother['new_id']
                        relationships_created += 1
                        print(f"🔗 Linked cutting '{cutting['name']}' to available pasted mother '{first_mother['name']}'")
                    else:
                        # No mother trees available, convert to independent
                        cutting_tree.mother_plant_id = None
                        cutting_tree.plant_type = 'mother'
                        independent_cuttings += 1
                        print(f"🌱 Converted cutting '{cutting['name']}' to independent mother (no mothers pasted)")

        # ✅ FORCE: Ensure all database changes are committed and visible
        db.session.commit()
        
        # ✅ DEBUG: Verify the changes were actually applied
        if mother_trees_pasted:
            for mother in mother_trees_pasted:
                old_mother_id = mother['old_id']
                old_mother_tree = Tree.query.get(old_mother_id)
                if old_mother_tree:
                    remaining_cuttings = Tree.query.filter_by(
                        mother_plant_id=old_mother_id,
                        plant_type='cutting',
                        user_id=current_user.id
                    ).count()
                    print(f"🔍 VERIFICATION: Old mother '{old_mother_tree.name}' (ID: {old_mother_id}) has {remaining_cuttings} cuttings after transfer")

        print(f"✅ Paste completed successfully")
        print(f"   📏 Area: {new_area.name} ({width}x{height})")
        print(f"   🌳 Trees created: {len(new_trees)}")
        print(f"   🔗 Relationships created: {relationships_created}")
        print(f"   🌱 Independent cuttings converted: {independent_cuttings}")
        print(f"   ⚠️ Orphaned cuttings handled: {orphaned_cuttings_handled}")
        print(f"   🔗 Linked to existing mothers: {linked_to_existing_mothers}")
        print(f"   🔄 Cutting trees transferred: {transferred_cuttings}")
        
        # Calculate preserved relationships
        preserved_relationships = 0
        if orphan_mode == 'preserve_original':
            preserved_relationships = orphaned_cuttings_handled

        return jsonify({
            'success': True,
            'message': f'Drag area "{new_name}" pasted successfully',
            'area': {
                'id': new_area.id,
                'name': new_area.name,
                'position': f"({paste_row}, {paste_col})",
                'size': f"{width}x{height}"
            },
            'stats': {
                'trees_created': len(new_trees),
                'mother_trees_pasted': len(mother_trees_pasted),
                'cutting_trees_pasted': len(cutting_trees_pasted),
                'relationships_created': relationships_created,
                'independent_cuttings_converted': independent_cuttings,
                'orphaned_cuttings_handled': orphaned_cuttings_handled,
                'linked_to_existing_mothers': linked_to_existing_mothers,
                'preserved_original_relationships': preserved_relationships,
                'transferred_cuttings': transferred_cuttings,
                'orphan_handling_mode': orphan_mode,
                'source_dome': clipboard_data.get('source_dome_name', 'Unknown')
            }
        })

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in paste_drag_area_from_backend: {str(e)}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        
        # ✅ DEBUG: Log the problematic data
        print(f"❌ DEBUG: data = {data}")
        print(f"❌ DEBUG: orphan_handling = {orphan_handling}")
        print(f"❌ DEBUG: orphaned_cuttings_info = {orphaned_cuttings_info}")
        
        return jsonify({'success': False, 'error': str(e)}), 500













@app.route('/api/refresh_tree_relationships/<int:tree_id>', methods=['POST'])
@login_required
def refresh_tree_relationships(tree_id):
    """Force refresh tree relationships data (cache-busting)"""
    try:
        # This endpoint forces a fresh query of tree relationships
        # It's useful after paste operations that might affect relationships
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        # Force a fresh count of cutting trees
        if tree.plant_type == 'mother':
            cutting_count = Tree.query.filter_by(
                mother_plant_id=tree.id,
                plant_type='cutting',
                user_id=current_user.id
            ).count()
            print(f"🔄 Refreshed: Mother '{tree.name}' has {cutting_count} cutting trees")
        
        return jsonify({
            'success': True,
            'message': 'Tree relationships refreshed',
            'tree_id': tree_id,
            'timestamp': datetime.utcnow().isoformat()
        })
        
    except Exception as e:
        print(f"❌ Error refreshing tree relationships: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/get_clipboard_status', methods=['GET'])
@login_required
def get_clipboard_status():
    """Get current clipboard status from backend"""
    try:
        clipboard_entry = ClipboardData.query.filter_by(
            user_id=current_user.id,
            clipboard_type='drag_area'
        ).order_by(ClipboardData.created_at.desc()).first()
        
        if not clipboard_entry:
            return jsonify({
                'success': True,
                'has_clipboard': False,
                'message': 'No clipboard data available'
            })

        # Parse clipboard data for summary
        try:
            clipboard_data = json.loads(clipboard_entry.clipboard_content)
            
            print(f"🔍 DEBUG: Clipboard entry found - ID: {clipboard_entry.id}")
            print(f"🔍 DEBUG: Clipboard entry name: {clipboard_entry.name}")
            print(f"🔍 DEBUG: Clipboard entry tree_count: {getattr(clipboard_entry, 'tree_count', 'N/A')}")
            print(f"🔍 DEBUG: Parsed clipboard_data keys: {list(clipboard_data.keys())}")
            print(f"🔍 DEBUG: Clipboard data name: {clipboard_data.get('name', 'NOT_FOUND')}")
            print(f"🔍 DEBUG: Clipboard data tree_count: {clipboard_data.get('tree_count', 'NOT_FOUND')}")
            
            return jsonify({
                'success': True,
                'has_clipboard': True,
                'clipboard_info': {
                    'name': clipboard_data.get('name', 'Unknown Area'),
                    'tree_count': clipboard_data.get('tree_count', 0),
                    'size': f"{clipboard_data.get('width', 1)}x{clipboard_data.get('height', 1)}",
                    'source_dome': clipboard_data.get('source_dome_name', 'Unknown'),
                    'copied_at': clipboard_entry.created_at.isoformat(),
                    'breeds': clipboard_data.get('summary', {}).get('breeds', []),
                    'relationships': clipboard_data.get('summary', {}).get('plant_relationships', {})
                }
            })
            
        except json.JSONDecodeError:
            return jsonify({
                'success': True,
                'has_clipboard': False,
                'message': 'Clipboard data corrupted'
            })

    except Exception as e:
        print(f"❌ Error getting clipboard status: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/clear_clipboard', methods=['POST'])
@login_required
def clear_clipboard():
    """Clear backend clipboard data"""
    try:
        deleted_count = ClipboardData.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        
        print(f"🗑️ Cleared {deleted_count} clipboard entries for user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': f'Cleared {deleted_count} clipboard entries'
        })

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error clearing clipboard: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    # Create upload directories
    os.makedirs(os.path.join(UPLOAD_FOLDER, 'trees'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_FOLDER, 'domes'), exist_ok=True)

    # Run the application
    print("🚀 Starting Flask server...")
    print("📍 Server will be available at: http://127.0.0.1:5000")
    print("🌐 Grid 1: http://127.0.0.1:5000/grid/1")
    print("🌐 Grid 2: http://127.0.0.1:5000/grid/2")
    app.run(debug=True, host='0.0.0.0', port=5000)
