import json 
from dotenv import load_dotenv
import os
import qrcode
import io
from flask import current_app, make_response, abort
import base64
from PIL import Image
from sqlalchemy import text
import time
import requests

# Load environment variables from .env file
load_dotenv()

# Now import other modules
from flask import Flask, render_template, request, jsonify, send_from_directory, send_file, redirect, session, flash, url_for
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from models import db, Dome, Tree, GridSettings, User, Farm
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
from datetime import datetime, timedelta
from flask_migrate import Migrate
from werkzeug.utils import secure_filename
from services.life_updater import TreeLifeUpdater
from flask_mail import Mail, Message

mail = Mail()

# Configuration constants
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

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
            
            print(f"Login attempt for: {username}")
            
            if not username or not password:
                return jsonify({'success': False, 'error': 'Username and password are required'}), 400
            
            # Find user by username or email
            user = User.query.filter(
                (User.username == username) | (User.email == username)
            ).first()
            
            print(f"User found: {user is not None}")
            
            if user and user.check_password(password):
                # ✅ NEW: Set permanent session and remember user
                from flask import session
                session.permanent = True
                
                login_user(user, remember=remember, duration=timedelta(days=30))
                print(f"Login successful for user: {user.username} (Remember: {remember})")
                return jsonify({'success': True, 'message': 'Login successful', 'redirect': '/farms'})
            else:
                print("Invalid username or password")
                return jsonify({'success': False, 'error': 'Invalid username or password'}), 401
                
        except Exception as e:
            print(f"Login error: {e}")
            return jsonify({'success': False, 'error': 'Login failed due to server error'}), 500
    
    return render_template('auth/login.html')

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
    try:
        print(f"🎯 Grid route called for dome_id: {dome_id}")
        print(f"🎯 User ID: {current_user.id}")
        
        # Get the dome and verify ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            print(f"❌ Dome {dome_id} not found for user {current_user.id}")
            flash('Dome not found', 'error')
            return redirect(url_for('domes'))
        
        print(f"✅ Dome found: {dome.name}")
        
        # Get all trees for this dome
        trees = Tree.query.filter_by(dome_id=dome_id).all()
        print(f"✅ Found {len(trees)} trees for dome {dome_id}")
        
        # Convert trees to JSON-serializable dictionaries
        trees_data = []
        for tree in trees:
            tree_dict = {
                'id': tree.id,
                'name': tree.name,
                'dome_id': tree.dome_id,
                'internal_row': tree.internal_row,
                'internal_col': tree.internal_col,
                'image_url': tree.image_url,
                'info': tree.info,
                'life_days': tree.life_days or 0,
                'user_id': tree.user_id,
                'created_at': tree.created_at.isoformat() if tree.created_at else None,
                'updated_at': tree.updated_at.isoformat() if tree.updated_at else None
            }
            trees_data.append(tree_dict)
            print(f"Tree {tree.id}: name={tree.name}, internal_row={tree.internal_row}, internal_col={tree.internal_col}")
        
        print(f"🎯 Rendering grid.html for dome {dome_id}")
        return render_template('grid.html',
                             dome=dome,
                             trees_data=trees_data,
                             rows=dome.internal_rows or 10,
                             cols=dome.internal_cols or 10,
                             timestamp=int(time.time()))
                             
    except Exception as e:
        print(f"❌ Error in grid route: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('An error occurred while loading the grid', 'error')
        return redirect(url_for('domes'))
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
        # Get grid settings for farms
        grid_settings = GridSettings.query.filter_by(
            user_id=current_user.id, 
            grid_type='farm'
        ).first()
        
        if not grid_settings:
            grid_settings = GridSettings(
                user_id=current_user.id,
                grid_type='farm',
                rows=10,
                cols=10
            )
            db.session.add(grid_settings)
            db.session.commit()
            print("✅ Created default farm grid settings")
        
        # Get all farms for this user
        farms = Farm.query.filter_by(user_id=current_user.id).all()
        
        print(f"✅ Found {len(farms)} farms")
        
        return render_template('farm.html', 
                             farms=farms,
                             grid_rows=grid_settings.rows,
                             grid_cols=grid_settings.cols,
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
    """Enhanced farm information page with error handling"""
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
        
        # Add timestamp for cache busting
        timestamp = int(time.time())
        
        return render_template('farm_info.html', 
                             farm=farm, 
                             domes=domes,
                             total_trees=total_trees,
                             timestamp=timestamp,
                             error_message=error_message)
        
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
        # For farm-specific dome settings
        if grid_type == 'dome' and farm_id:
            grid_type_key = f'farm_{farm_id}_dome'
        else:
            grid_type_key = grid_type
            
        settings = GridSettings.query.filter_by(
            grid_type=grid_type_key,
            user_id=user_id
        ).first()
        
        if not settings:
            # Create default settings with 5x5 for farm domes
            if grid_type == 'farm':
                default_rows, default_cols = 10, 10
            elif farm_id:  # Farm-specific dome settings
                default_rows, default_cols = 5, 5  # Default 5x5 for farm domes
            else:  # Fallback
                default_rows, default_cols = 5, 5
            
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
        # Return default object with 5x5 for farm domes
        if grid_type == 'farm':
            default_rows, default_cols = 10, 10
        elif farm_id:
            default_rows, default_cols = 5, 5
        else:
            default_rows, default_cols = 5, 5
            
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
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        grid_row = data.get('grid_row')
        grid_col = data.get('grid_col')
        password = data.get('password', '').strip()
        
        # ✅ ENHANCED: Better input validation
        if not name:
            return jsonify({'success': False, 'error': 'Farm name is required'})
        
        if grid_row is None or grid_col is None:
            return jsonify({'success': False, 'error': 'Grid position is required'})
        
        try:
            grid_row = int(grid_row)
            grid_col = int(grid_col)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid grid position values'})
        
        if len(name) > 100:
            return jsonify({'success': False, 'error': 'Farm name too long (max 100 characters)'})
        
        # ✅ OPTIMIZED: Direct SQL query for better performance on Render
        print(f"🔍 Checking position ({grid_row}, {grid_col}) for user {current_user.id}")
        
        # Check if position is occupied using raw SQL (more reliable for Render)
        position_check = db.session.execute(
            text("""
                SELECT id, name 
                FROM farm 
                WHERE grid_row = :row AND grid_col = :col AND user_id = :user_id 
                LIMIT 1
            """),
            {
                "row": grid_row, 
                "col": grid_col, 
                "user_id": current_user.id
            }
        ).fetchone()
        
        if position_check:
            existing_farm_name = position_check[1] if len(position_check) > 1 else "Unknown"
            return jsonify({
                'success': False, 
                'error': f'Position ({grid_row}, {grid_col}) is already occupied by farm "{existing_farm_name}"'
            })
        
        # ✅ ENHANCED: Validate grid bounds (optional - adjust based on your grid size)
        max_grid_size = 50  # Adjust based on your farm grid settings
        if grid_row < 0 or grid_col < 0 or grid_row >= max_grid_size or grid_col >= max_grid_size:
            return jsonify({
                'success': False, 
                'error': f'Grid position must be between 0 and {max_grid_size-1}'
            })
        
        # ✅ OPTIMIZED: Create farm using direct SQL insert for Render compatibility
        print(f"🌱 Creating farm '{name}' at ({grid_row}, {grid_col})")
        
        # Hash password if provided
        password_hash = None
        if password:
            from werkzeug.security import generate_password_hash
            password_hash = generate_password_hash(password)
            print(f"🔒 Farm will be password protected")
        
        # Insert new farm using SQL (more reliable on Render)
        result = db.session.execute(
            text("""
                INSERT INTO farm (name, grid_row, grid_col, user_id, password_hash, created_at)
                VALUES (:name, :grid_row, :grid_col, :user_id, :password_hash, :created_at)
                RETURNING id, name, grid_row, grid_col
            """),
            {
                "name": name,
                "grid_row": grid_row,
                "grid_col": grid_col,
                "user_id": current_user.id,
                "password_hash": password_hash,
                "created_at": datetime.utcnow()
            }
        )
        
        # Get the created farm data
        new_farm_data = result.fetchone()
        
        if not new_farm_data:
            raise Exception("Failed to create farm - no data returned")
        
        db.session.commit()
        
        # ✅ ENHANCED: Detailed success response
        farm_id = new_farm_data[0]
        protection_status = "with password protection" if password_hash else "without password protection"
        
        print(f"✅ Farm created successfully: ID {farm_id}, Name '{name}' {protection_status}")
        
        return jsonify({
            'success': True,
            'message': f'Farm "{name}" created successfully {protection_status}',
            'farm': {
                'id': farm_id,
                'name': name,
                'grid_row': grid_row,
                'grid_col': grid_col,
                'has_password': bool(password_hash),
                'protection_status': protection_status,
                'created_at': datetime.utcnow().isoformat()
            }
        })
        
    except Exception as e:
        db.session.rollback()
        error_msg = str(e)
        print(f"❌ Error creating farm: {error_msg}")
        
        # ✅ ENHANCED: Better error messages for common issues
        if "duplicate key" in error_msg.lower() or "unique constraint" in error_msg.lower():
            return jsonify({
                'success': False, 
                'error': 'A farm already exists at this position'
            })
        elif "foreign key" in error_msg.lower():
            return jsonify({
                'success': False, 
                'error': 'Invalid user reference'
            })
        elif "not null" in error_msg.lower():
            return jsonify({
                'success': False, 
                'error': 'Missing required farm information'
            })
        else:
            return jsonify({
                'success': False, 
                'error': 'Failed to create farm. Please try again.'
            })
@app.route('/verify_farm_password/<int:farm_id>', methods=['POST'])
@login_required
def verify_farm_password(farm_id):
    try:
        data = request.get_json()
        password = data.get('password', '')
        
        print(f"🔐 Verifying password for farm {farm_id}")
        
        # Get farm with password hash using SQL
        farm_data = db.session.execute(
            text("""
                SELECT id, name, password_hash 
                FROM farm 
                WHERE id = :farm_id AND user_id = :user_id
            """),
            {"farm_id": farm_id, "user_id": current_user.id}
        ).fetchone()
        
        if not farm_data:
            return jsonify({'success': False, 'error': 'Farm not found or access denied'})
        
        farm_password_hash = farm_data[2]  # password_hash column
        farm_name = farm_data[1]  # name column
        
        # Check password
        if not farm_password_hash:
            # No password set, allow access
            print(f"✅ Farm '{farm_name}' has no password protection")
            return jsonify({'success': True, 'message': 'Access granted (no password required)'})
        
        if not password:
            return jsonify({'success': False, 'error': 'Password required for this farm'})
        
        # Verify password
        from werkzeug.security import check_password_hash
        if check_password_hash(farm_password_hash, password):
            print(f"✅ Correct password for farm '{farm_name}'")
            return jsonify({'success': True, 'message': 'Password correct'})
        else:
            print(f"❌ Incorrect password for farm '{farm_name}'")
            return jsonify({'success': False, 'error': 'Incorrect password'})
            
    except Exception as e:
        print(f"❌ Error verifying farm password: {str(e)}")
        return jsonify({'success': False, 'error': 'Password verification failed'})
@app.route('/farm_password_status/<int:farm_id>')
@login_required
def farm_password_status(farm_id):
    try:
        # Get farm password status
        farm_data = db.session.execute(
            text("""
                SELECT id, name, password_hash 
                FROM farm 
                WHERE id = :farm_id AND user_id = :user_id
            """),
            {"farm_id": farm_id, "user_id": current_user.id}
        ).fetchone()
        
        if not farm_data:
            return jsonify({'success': False, 'error': 'Farm not found'})
        
        has_password = bool(farm_data[2])  # password_hash column
        farm_name = farm_data[1]  # name column
        
        return jsonify({
            'success': True,
            'farm_name': farm_name,
            'has_password': has_password,
            'status': '🔒 Password Protected' if has_password else '🔓 Open Access'
        })
        
    except Exception as e:
        print(f"❌ Error checking farm password status: {str(e)}")
        return jsonify({'success': False, 'error': 'Failed to check password status'})
@login_required
def update_grid_settings():
    """Update grid settings for dome grids (farm-specific or global)"""
    try:
        data = request.get_json()
        grid_type = data.get('grid_type', 'dome')
        rows = data.get('rows')
        cols = data.get('cols')
        farm_id = data.get('farm_id')  # Get farm_id from request
        
        print(f"🔧 Updating {grid_type} grid size to {rows}x{cols} (farm_id: {farm_id})")
        
        if not rows or not cols:
            return jsonify({'success': False, 'error': 'Rows and columns are required'})
        
        try:
            rows = int(rows)
            cols = int(cols)
        except (ValueError, TypeError):
            return jsonify({'success': False, 'error': 'Invalid grid size values'})
        
        if rows < 1 or rows > 100 or cols < 1 or cols > 100:
            return jsonify({'success': False, 'error': 'Grid size must be between 1x1 and 100x100'})
        
        # ✅ FIXED: Handle farm-specific vs global dome grids
        if farm_id:
            # Farm-specific dome grid
            grid_type_key = f'farm_{farm_id}_dome'
            
            # Verify farm ownership
            farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
            if not farm:
                return jsonify({'success': False, 'error': 'Farm not found or access denied'})
            
            # Check if shrinking would affect existing domes in this farm
            affected_domes = Dome.query.filter(
                Dome.farm_id == farm_id,
                Dome.user_id == current_user.id,
                (Dome.grid_row >= rows) | (Dome.grid_col >= cols)
            ).all()
        else:
            # Global dome grid
            grid_type_key = 'dome'
            
            # Check if shrinking would affect existing global domes
            affected_domes = Dome.query.filter(
                Dome.farm_id.is_(None),
                Dome.user_id == current_user.id,
                (Dome.grid_row >= rows) | (Dome.grid_col >= cols)
            ).all()
        
        if affected_domes:
            dome_names = [dome.name for dome in affected_domes]
            return jsonify({
                'success': False, 
                'error': f'Cannot shrink grid. Domes would be affected: {", ".join(dome_names)}'
            })
        
        # Update or create grid settings
        settings = GridSettings.query.filter_by(
            grid_type=grid_type_key,
            user_id=current_user.id
        ).first()
        
        if settings:
            settings.rows = rows
            settings.cols = cols
        else:
            settings = GridSettings(
                rows=rows,
                cols=cols,
                grid_type=grid_type_key,
                user_id=current_user.id
            )
            db.session.add(settings)
        
        db.session.commit()
        
        context = f"farm {farm_id}" if farm_id else "global"
        print(f"✅ {context} dome grid size updated to {rows}x{cols}")
        
        return jsonify({
            'success': True, 
            'message': f'Dome grid updated to {rows}x{cols}',
            'context': context
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error updating grid settings: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
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
@login_required
def delete_dome(dome_id):
    try:
        # Get the dome
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'})
        
        dome_name = dome.name
        
        # Delete associated trees first
        trees = Tree.query.filter_by(dome_id=dome_id).all()
        tree_count = len(trees)
        for tree in trees:
            db.session.delete(tree)
        
        # Delete the dome
        db.session.delete(dome)
        db.session.commit()
        
        print(f"✅ Dome deleted: {dome_name} (with {tree_count} trees)")
        
        return jsonify({'success': True, 'message': 'Dome deleted successfully'})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error deleting dome: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})



# ============= DOME IMAGE MANAGEMENT =============

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
    try:
        data = request.get_json()
        dome_id = data.get('dome_id')
        name = data.get('name')
        internal_row = data.get('internal_row')
        internal_col = data.get('internal_col')
        
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'})
        
        # Check if position is already occupied
        existing_tree = Tree.query.filter_by(
            dome_id=dome_id,
            internal_row=internal_row,
            internal_col=internal_col
        ).first()
        
        if existing_tree:
            return jsonify({'success': False, 'error': 'Position already occupied'})
        
        # Create new tree
        new_tree = Tree(
            name=name,
            dome_id=dome_id,
            user_id=current_user.id,
            internal_row=internal_row,
            internal_col=internal_col
        )
        
        db.session.add(new_tree)
        db.session.commit()
        
        # Return tree data
        tree_data = {
            'id': new_tree.id,
            'name': new_tree.name,
            'dome_id': new_tree.dome_id,
            'internal_row': new_tree.internal_row,
            'internal_col': new_tree.internal_col,
            'image_url': new_tree.image_url,
            'info': new_tree.info,
            'life_days': new_tree.life_days or 0
        }
        
        print(f"✅ Tree added: {new_tree.name} at ({internal_row}, {internal_col}) in dome {dome_id}")
        
        return jsonify({'success': True, 'tree': tree_data})
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error adding tree: {str(e)}")
        return jsonify({'success': False, 'error': f'Failed to add tree: {str(e)}'})

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
@app.route('/dome_info/<int:dome_id>')
@login_required
def dome_info(dome_id):
    try:
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            flash('Dome not found', 'error')
            return redirect(url_for('farms'))
        
        # Ensure dome belongs to a farm
        if not dome.farm_id:
            flash('Invalid dome - must belong to a farm', 'error')
            return redirect(url_for('farms'))
        
        # Get the farm for context
        farm = Farm.query.filter_by(id=dome.farm_id, user_id=current_user.id).first()
        if not farm:
            flash('Farm not found', 'error')
            return redirect(url_for('farms'))
        
        return render_template('dome_info.html', 
                             dome=dome, 
                             farm=farm,
                             timestamp=int(time.time()))
        
    except Exception as e:
        print(f"❌ Error in dome_info route: {e}")
        flash('Error loading dome information', 'error')
        return redirect(url_for('farms'))

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
        
        timestamp = int(time.time())
        
        # ✅ FIXED: Pass both tree AND dome objects to template
        response = make_response(render_template('tree_info.html', 
                                               tree=tree, 
                                               dome=dome,  # ✅ Added dome object
                                               timestamp=timestamp))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response
        
    except Exception as e:
        print(f"Error in tree_info route: {str(e)}")
        flash('An error occurred while loading tree information', 'error')
        return redirect(url_for('index'))

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

@app.route('/delete_tree/<int:tree_id>', methods=['DELETE'])
@login_required
def delete_tree(tree_id):
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify(success=False, error="Tree not found"), 404
        
        # Delete tree image if exists
        if tree.image_url:
            try:
                filename = tree.image_url.split('/')[-1]
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], 'trees', filename)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"🗑️ Removed tree image: {file_path}")
            except Exception as e:
                print(f"⚠️ Error deleting tree image: {e}")
        
        db.session.delete(tree)
        db.session.commit()
        
        return jsonify(success=True)
        
    except Exception as e:
        print(f"Error deleting tree: {e}")
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
@app.route('/move_tree/<int:tree_id>', methods=['POST'])
@login_required
def move_tree(tree_id):
    """Move a tree to a new position in the grid"""
    try:
        data = request.get_json()
        new_row = data.get('internal_row')
        new_col = data.get('internal_col')
        
        if new_row is None or new_col is None:
            return jsonify({
                'success': False,
                'error': 'Both internal_row and internal_col are required'
            })
        
        # Get the tree and verify ownership
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({
                'success': False,
                'error': f'Tree with ID {tree_id} not found'
            })
        
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
            old_row = tree.internal_row
            old_col = tree.internal_col
            
            # Move target tree to original position
            existing_tree.internal_row = old_row
            existing_tree.internal_col = old_col
            
            swapped = True
            swapped_tree_data = {
                'id': existing_tree.id,
                'internal_row': old_row,
                'internal_col': old_col
            }
        
        # Store original position for logging
        old_row = tree.internal_row
        old_col = tree.internal_col
        
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
            'message': 'Tree moved successfully',
            'swapped': swapped,
            'swapped_tree': swapped_tree_data,
            'tree': {
                'id': tree.id,
                'name': tree.name,
                'internal_row': tree.internal_row,
                'internal_col': tree.internal_col,
                'old_row': old_row,
                'old_col': old_col
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error moving tree {tree_id}: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Database error: {str(e)}'
        })
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
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        data = request.json
        
        # Update tree fields
        if 'name' in data:
            tree.name = data['name']
        if 'info' in data:
            tree.info = data['info']
        if 'life_days' in data:
            tree.life_days = int(data['life_days'])
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Tree updated successfully'})
        
    except Exception as e:
        print(f"Error updating tree: {e}")
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
    """API endpoint to get trees for a specific dome"""
    try:
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        trees = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
        
        trees_data = []
        for tree in trees:
            tree_data = {
                'id': tree.id,
                'name': tree.name,
                'row': tree.row,
                'col': tree.col,
                'life_days': tree.life_days,
                'info': tree.info,
                'image_url': tree.image_url
            }
            trees_data.append(tree_data)
        
        return jsonify({
            'success': True,
            'trees': trees_data,
            'dome': {
                'id': dome.id,
                'name': dome.name,
                'internal_rows': dome.internal_rows,
                'internal_cols': dome.internal_cols
            }
        })
        
    except Exception as e:
        print(f"Error getting trees: {e}")
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
if __name__ == '__main__':
    # Create upload directories
    os.makedirs(os.path.join(UPLOAD_FOLDER, 'trees'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_FOLDER, 'domes'), exist_ok=True)
    
    # Run the application
    app.run(debug=True, host='0.0.0.0', port=5000)