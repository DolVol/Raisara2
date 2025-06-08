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
# Add these helper functions to your app.py file (after the imports section)
def is_postgresql():
    """Check if we're using PostgreSQL"""
    return 'postgresql' in DATABASE_URL or os.getenv('RENDER') or os.getenv('DATABASE_URL', '').startswith('postgres')

def is_sqlite():
    """Check if we're using SQLite"""
    return 'sqlite' in DATABASE_URL and not os.getenv('RENDER')
def get_grid_settings(grid_type='dome', user_id=None):
    """Get grid settings for specific type and user"""
    try:
        settings = GridSettings.query.filter_by(
            grid_type=grid_type,
            user_id=user_id
        ).first()
        
        if not settings:
            # Create default settings
            default_rows = 10 if grid_type == 'farm' else 5
            default_cols = 10 if grid_type == 'farm' else 5
            
            settings = GridSettings(
                rows=default_rows,
                cols=default_cols,
                grid_type=grid_type,
                user_id=user_id
            )
            db.session.add(settings)
            db.session.commit()
            print(f"✅ Created default {grid_type} settings: {default_rows}x{default_cols}")
            
        return settings
    except Exception as e:
        print(f"Error getting grid settings: {e}")
        # Return default object
        return type('obj', (object,), {
            'rows': 10 if grid_type == 'farm' else 5,
            'cols': 10 if grid_type == 'farm' else 5,
            'grid_type': grid_type
        })

def update_grid_settings(grid_type, rows, cols, user_id=None):
    """Update grid settings for specific type and user"""
    try:
        settings = GridSettings.query.filter_by(
            grid_type=grid_type,
            user_id=user_id
        ).first()
        
        if not settings:
            settings = GridSettings(
                grid_type=grid_type,
                user_id=user_id
            )
            db.session.add(settings)
        
        settings.rows = rows
        settings.cols = cols
        db.session.commit()
        
        print(f"✅ Updated {grid_type} grid settings to {rows}x{cols} for user {user_id}")
        return True
    except Exception as e:
        print(f"Error updating grid settings: {e}")
        db.session.rollback()
        return False
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
            # Create default settings
            if grid_type == 'farm':
                default_rows, default_cols = 10, 10
            elif farm_id:  # Farm-specific dome settings
                default_rows, default_cols = 8, 8  # Different default for farm domes
            else:  # Global dome settings
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
        # Return default object
        if grid_type == 'farm':
            default_rows, default_cols = 10, 10
        elif farm_id:
            default_rows, default_cols = 8, 8
        else:
            default_rows, default_cols = 5, 5
            
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
def migrate_tree_columns():
    """Migrate tree table from row/col to internal_row/internal_col"""
    try:
        # Check if old columns exist
        inspector = db.inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('tree')]
        
        if 'row' in columns and 'internal_row' not in columns:
            print("Migrating tree columns...")
            
            # Add new columns
            db.engine.execute('ALTER TABLE tree ADD COLUMN internal_row INTEGER DEFAULT 0')
            db.engine.execute('ALTER TABLE tree ADD COLUMN internal_col INTEGER DEFAULT 0')
            
            # Copy data from old columns to new columns
            db.engine.execute('UPDATE tree SET internal_row = row, internal_col = col')
            
            # Note: SQLite doesn't support DROP COLUMN, so we'll leave the old columns
            # In production, you might want to create a new table and copy data
            
            print("Tree column migration completed!")
            
    except Exception as e:
        print(f"Migration error: {str(e)}")
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
        print(f"Register route error: {e}")
        return jsonify({'success': False, 'error': 'Registration page error'}), 500

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
            return redirect(url_for('dome_info', dome_id=dome_id))
        
        print(f"✅ Dome found: {dome.name}")
        
        # Get all trees for this dome
        trees = Tree.query.filter_by(dome_id=dome_id).all()
        print(f"✅ Found {len(trees)} trees for dome {dome_id}")
        
        # ✅ FIXED: Convert trees to JSON-serializable dictionaries
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
        
        # ✅ CRITICAL: Pass trees_data for JSON serialization
        print(f"🎯 Rendering grid.html for dome {dome_id}")
        return render_template('grid.html',
                             dome=dome,
                             trees_data=trees_data,  # ✅ Use trees_data for JSON
                             rows=dome.internal_rows or 10,
                             cols=dome.internal_cols or 10,
                             timestamp=int(time.time()))
                             
    except Exception as e:
        print(f"❌ Error in grid route: {str(e)}")
        import traceback
        traceback.print_exc()
        flash('An error occurred while loading the grid', 'error')
        return redirect(url_for('dome_info', dome_id=dome_id))
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
    """Main farm management page"""
    from flask import session
    session.permanent = True
    
    # ✅ FIXED: Get FARM-specific grid settings
    try:
        grid = get_grid_settings('farm', current_user.id)
        print(f"📏 Farm grid settings: {grid.rows}x{grid.cols}")
    except Exception as e:
        print(f"⚠️ Farm grid settings error: {e}")
        grid = type('obj', (object,), {'rows': 10, 'cols': 10})
    
    # Get only current user's farms
    farms = Farm.query.filter_by(user_id=current_user.id).order_by(Farm.grid_row, Farm.grid_col).all()
    
    timestamp = int(time.time())
    
    return render_template('farm.html', 
                         grid_rows=grid.rows,
                         grid_cols=grid.cols,
                         farms=farms,
                         user=current_user,
                         timestamp=timestamp)

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
    """Move farm to new position"""
    try:
        data = request.json
        
        # Get farm and check ownership
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify(success=False, error="Farm not found"), 404

        # Get new position
        new_row = data.get('grid_row')
        new_col = data.get('grid_col')

        # Convert to integers if they're strings
        try:
            new_row = int(new_row)
            new_col = int(new_col)
        except (ValueError, TypeError):
            return jsonify(success=False, error="Invalid position data"), 400

        # Validate grid bounds
        try:
            grid = GridSettings.query.first()
            if not grid:
                grid = GridSettings(rows=10, cols=10)
                db.session.add(grid)
                db.session.commit()
        except Exception as e:
            print(f"⚠️ Grid settings error: {e}")
            grid = type('obj', (object,), {'rows': 10, 'cols': 10})
            
        if new_row >= grid.rows or new_col >= grid.cols or new_row < 0 or new_col < 0:
            return jsonify(success=False, error="Position out of bounds"), 400

        # Check for existing farm in target position
        existing_farm = Farm.query.filter(
            Farm.id != farm_id,
            Farm.grid_row == new_row, 
            Farm.grid_col == new_col,
            Farm.user_id == current_user.id
        ).first()
        
        if existing_farm:
            # SWAP the farms
            print(f"Swapping farm {farm_id} with farm {existing_farm.id}")
            
            # Store original position
            original_row = farm.grid_row
            original_col = farm.grid_col
            
            # Move the first farm to the target position
            farm.grid_row = new_row
            farm.grid_col = new_col
            farm.updated_at = datetime.utcnow()
            
            # Move the existing farm to the original position
            existing_farm.grid_row = original_row
            existing_farm.grid_col = original_col
            existing_farm.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'swapped': True,
                'farm1': {
                    'id': farm.id,
                    'grid_row': farm.grid_row,
                    'grid_col': farm.grid_col,
                    'name': farm.name
                },
                'farm2': {
                    'id': existing_farm.id,
                    'grid_row': existing_farm.grid_row,
                    'grid_col': existing_farm.grid_col,
                    'name': existing_farm.name
                }
            })
        else:
            # No existing farm, just move to the new position
            farm.grid_row = new_row
            farm.grid_col = new_col
            farm.updated_at = datetime.utcnow()
            db.session.commit()
            
            return jsonify({
                'success': True,
                'swapped': False,
                'farm': {
                    'id': farm.id,
                    'grid_row': farm.grid_row,
                    'grid_col': farm.grid_col,
                    'name': farm.name
                }
            })
            
    except Exception as e:
        print(f"Error moving farm: {e}")
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500

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
    """Farm information and dome management page"""
    farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
    if not farm:
        abort(404)
    
    # Initialize variables
    domes = []
    total_trees = 0
    error_message = None
    
    # Try to get domes in this farm
    try:
        # First, check if farm_id column exists
        with db.engine.connect() as conn:
            if is_postgresql():
                # ✅ FIXED: PostgreSQL version
                result = conn.execute(text("""
                    SELECT column_name 
                    FROM information_schema.columns 
                    WHERE table_name = 'dome' AND column_name = 'farm_id'
                """))
                columns = [row[0] for row in result.fetchall()]
            else:
                # SQLite version
                result = conn.execute(text("PRAGMA table_info(dome)"))
                columns = [row[1] for row in result.fetchall()]
            
            if 'farm_id' not in columns:
                print("❌ farm_id column missing - showing all user domes instead")
                error_message = "Farm system not fully configured. Showing all your domes."
                
                # Fallback: show all user's domes
                try:
                    domes = Dome.query.filter_by(user_id=current_user.id).order_by(Dome.grid_row, Dome.grid_col).all()
                except Exception as e:
                    print(f"⚠️ Fallback query failed: {e}")
                    domes = []
            else:
                # farm_id column exists, try normal query
                try:
                    domes = Dome.query.filter_by(farm_id=farm_id, user_id=current_user.id).order_by(Dome.grid_row, Dome.grid_col).all()
                    print(f"✅ SQLAlchemy query successful for farm {farm_id}, found {len(domes)} domes")
                except Exception as e:
                    print(f"⚠️ SQLAlchemy query failed, using raw SQL: {e}")
                    try:
                        # Fallback to raw SQL
                        result = conn.execute(
                            text("SELECT * FROM dome WHERE farm_id = :farm_id AND user_id = :user_id ORDER BY grid_row, grid_col"),
                            {"farm_id": farm_id, "user_id": current_user.id}
                        )
                        
                        # Convert raw results to Dome objects
                        domes = []
                        for row in result:
                            dome = Dome()
                            dome.id = row.id
                            dome.name = row.name
                            dome.grid_row = row.grid_row
                            dome.grid_col = row.grid_col
                            dome.internal_rows = row.internal_rows
                            dome.internal_cols = row.internal_cols
                            dome.image_url = row.image_url
                            dome.user_id = row.user_id
                            dome.farm_id = getattr(row, 'farm_id', farm_id)
                            dome.created_at = getattr(row, 'created_at', None)
                            dome.updated_at = getattr(row, 'updated_at', None)
                            domes.append(dome)
                        
                        print(f"✅ Raw SQL query successful, found {len(domes)} domes")
                    except Exception as e2:
                        print(f"⚠️ Raw SQL query also failed: {e2}")
                        error_message = f"Database error: {str(e2)}"
                        domes = []
    
    except Exception as e:
        print(f"⚠️ Database connection error: {e}")
        error_message = f"Database connection error: {str(e)}"
        domes = []
    
    # Calculate total trees across all domes
    for dome in domes:
        try:
            tree_count = Tree.query.filter_by(dome_id=dome.id, user_id=current_user.id).count()
            total_trees += tree_count
        except Exception as e:
            print(f"⚠️ Error counting trees for dome {dome.id}: {e}")
            # Fallback to raw SQL for tree count
            try:
                with db.engine.connect() as conn:
                    result = conn.execute(
                        text("SELECT COUNT(*) as count FROM tree WHERE dome_id = :dome_id AND user_id = :user_id"),
                        {"dome_id": dome.id, "user_id": current_user.id}
                    )
                    tree_count = result.fetchone().count
                    total_trees += tree_count
            except Exception as e2:
                print(f"⚠️ Raw SQL tree count also failed: {e2}")
    
    # Add timestamp for cache busting
    timestamp = int(time.time())
    
    return render_template('farm_info.html', 
                         farm=farm, 
                         domes=domes,
                         total_trees=total_trees,
                         timestamp=timestamp,
                         error_message=error_message)
@app.route('/farm')
@login_required
def farm_redirect():
    """Redirect /farm to /farms for compatibility"""
    return redirect('/farms')

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
    """Delete farm and all its domes/trees"""
    try:
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify(success=False, error="Farm not found"), 404
        
        # Delete farm image if exists
        if hasattr(farm, 'image_url') and farm.image_url:
            try:
                filename = farm.image_url.split('/')[-1]
                upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
                filepath = os.path.join(upload_folder, 'farms', filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
                    print(f"🗑️ Removed farm image: {filepath}")
            except Exception as e:
                print(f"⚠️ Error deleting farm image: {e}")
        
        # Delete all domes in this farm (and their trees)
        domes = Dome.query.filter_by(farm_id=farm_id, user_id=current_user.id).all()
        for dome in domes:
            # Delete dome images
            if hasattr(dome, 'image_url') and dome.image_url:
                try:
                    filename = dome.image_url.split('/')[-1]
                    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
                    filepath = os.path.join(upload_folder, 'domes', filename)
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except Exception as e:
                    print(f"⚠️ Error deleting dome image: {e}")
            
            # Delete all trees in this dome
            trees = Tree.query.filter_by(dome_id=dome.id, user_id=current_user.id).all()
            for tree in trees:
                # Delete tree images
                if hasattr(tree, 'image_url') and tree.image_url:
                    try:
                        filename = tree.image_url.split('/')[-1]
                        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
                        filepath = os.path.join(upload_folder, 'trees', filename)
                        if os.path.exists(filepath):
                            os.remove(filepath)
                    except Exception as e:
                        print(f"⚠️ Error deleting tree image: {e}")
                db.session.delete(tree)
            
            db.session.delete(dome)
        
        db.session.delete(farm)
        db.session.commit()
        return jsonify(success=True)
        
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500

@app.route('/upload_farm_image/<int:farm_id>', methods=['POST'])
@login_required
def upload_farm_image(farm_id):
    """Upload farm image"""
    try:
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            return jsonify({'success': False, 'error': 'Farm not found'}), 404
        
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            # Create farms directory if it doesn't exist
            farms_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'farms')
            os.makedirs(farms_dir, exist_ok=True)
            
            # Delete old image if exists
            if hasattr(farm, 'image_url') and farm.image_url:
                try:
                    old_filename = farm.image_url.split('/')[-1]
                    old_file_path = os.path.join(farms_dir, old_filename)
                    if os.path.exists(old_file_path):
                        os.remove(old_file_path)
                except Exception as e:
                    print(f"Error deleting old farm image: {e}")
            
            # Generate unique filename
            timestamp = int(time.time())
            file_extension = file.filename.rsplit('.', 1)[1].lower()
            filename = f"farm_{farm_id}_{timestamp}_{secrets.token_hex(16)}.{file_extension}"
            
            # Save file
            file_path = os.path.join(farms_dir, filename)
            file.save(file_path)
            
            # Update farm image URL
            farm.image_url = f"/static/uploads/farms/{filename}"
            farm.updated_at = datetime.utcnow()
            
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'image_url': farm.image_url,
                'message': 'Farm image uploaded successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Invalid file type'}), 400
            
    except Exception as e:
        print(f"Error uploading farm image: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
@app.route('/')
@login_required
def index():
    try:
        # ✅ FIXED: Get DOME-specific grid settings
        grid_settings = get_grid_settings('dome', current_user.id)
        print(f"📏 Dome grid settings: {grid_settings.rows}x{grid_settings.cols}")
        
        # Get all domes for current user
        domes = Dome.query.filter_by(user_id=current_user.id).all()
        
        return render_template('dome.html',
                             domes=domes,
                             grid_rows=grid_settings.rows,
                             grid_cols=grid_settings.cols,
                             user=current_user,
                             timestamp=int(time.time()))
                             
    except Exception as e:
        print(f"❌ Error in index route: {str(e)}")
        import traceback
        traceback.print_exc()
        # Fallback to default grid
        return render_template('dome.html',
                             domes=[],
                             grid_rows=5,
                             grid_cols=5,
                             user=current_user,
                             timestamp=int(time.time()))
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
        # Get the farm and verify ownership
        farm = Farm.query.filter_by(id=farm_id, user_id=current_user.id).first()
        if not farm:
            flash('Farm not found', 'error')
            return redirect(url_for('farms'))
        
        # ✅ FIXED: Get FARM-SPECIFIC dome grid settings
        grid_settings = get_grid_settings('dome', current_user.id, farm_id)
        print(f"📏 Farm {farm_id} dome grid settings: {grid_settings.rows}x{grid_settings.cols}")
        
        # Get domes for this farm
        domes = Dome.query.filter_by(farm_id=farm_id, user_id=current_user.id).all()
        
        return render_template('dome.html',
                             domes=domes,
                             grid_rows=grid_settings.rows,
                             grid_cols=grid_settings.cols,
                             farm_id=farm_id,  # ✅ Pass farm_id to template
                             farm_name=farm.name,  # ✅ Pass farm name
                             page_title=f"{farm.name} - Domes",
                             user=current_user,
                             timestamp=int(time.time()))
                             
    except Exception as e:
        print(f"❌ Error in farm_domes route: {str(e)}")
        flash('An error occurred while loading farm domes', 'error')
        return redirect(url_for('farms'))

@app.route('/add_dome', methods=['POST'])
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
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify(success=False, error="Dome not found"), 404
        
        # ✅ FIXED: Delete dome image if exists
        if hasattr(dome, 'image_url') and dome.image_url:
            try:
                filename = dome.image_url.split('/')[-1]
                upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
                filepath = os.path.join(upload_folder, filename)
                if os.path.exists(filepath):
                    os.remove(filepath)
                    print(f"🗑️ Removed dome image: {filepath}")
            except Exception as e:
                print(f"⚠️ Error deleting dome image: {e}")
        
        # Delete all trees in this dome first
        trees = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
        for tree in trees:
            # Delete tree images too
            if hasattr(tree, 'image_url') and tree.image_url:
                try:
                    filename = tree.image_url.split('/')[-1]
                    upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
                    filepath = os.path.join(upload_folder, filename)
                    if os.path.exists(filepath):
                        os.remove(filepath)
                except Exception as e:
                    print(f"⚠️ Error deleting tree image: {e}")
            db.session.delete(tree)
        
        db.session.delete(dome)
        db.session.commit()
        return jsonify(success=True)
        
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500

@app.route('/move_dome/<int:dome_id>', methods=['POST'])
@login_required
def move_dome(dome_id):
    try:
        data = request.get_json()
        new_row = data.get('grid_row')
        new_col = data.get('grid_col')
        
        # Get the dome to move
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'})
        
        # ✅ FIXED: Check for conflicts within the same farm context
        existing_dome = Dome.query.filter_by(
            grid_row=new_row, 
            grid_col=new_col, 
            farm_id=dome.farm_id,  # Check within the same farm
            user_id=current_user.id
        ).filter(Dome.id != dome_id).first()
        
        if existing_dome:
            # Swap positions
            old_row, old_col = dome.grid_row, dome.grid_col
            dome.grid_row, dome.grid_col = new_row, new_col
            existing_dome.grid_row, existing_dome.grid_col = old_row, old_col
            
            db.session.commit()
            return jsonify({'success': True, 'swapped': True})
        else:
            # Simple move
            dome.grid_row = new_row
            dome.grid_col = new_col
            db.session.commit()
            return jsonify({'success': True, 'swapped': False})
            
    except Exception as e:
        db.session.rollback()
        print(f"Error moving dome: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

# ============= DOME IMAGE MANAGEMENT =============

@app.route('/upload_dome_image/<int:dome_id>', methods=['POST'])
@login_required
def upload_dome_image(dome_id):
    try:
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            # Create domes directory if it doesn't exist
            domes_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'domes')
            os.makedirs(domes_dir, exist_ok=True)
            
            # Delete old image if exists
            if dome.image_url:
                try:
                    old_filename = dome.image_url.split('/')[-1]
                    old_file_path = os.path.join(domes_dir, old_filename)
                    if os.path.exists(old_file_path):
                        os.remove(old_file_path)
                except Exception as e:
                    print(f"Error deleting old dome image: {e}")
            
            # Generate unique filename
            timestamp = int(time.time())
            file_extension = file.filename.rsplit('.', 1)[1].lower()
            filename = f"dome_{dome_id}_{timestamp}_{secrets.token_hex(16)}.{file_extension}"
            
            # Save file
            file_path = os.path.join(domes_dir, filename)
            file.save(file_path)
            
            # Update dome image URL
            dome.image_url = f"/static/uploads/domes/{filename}"
            
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'image_url': dome.image_url,
                'message': 'Dome image uploaded successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Invalid file type'}), 400
            
    except Exception as e:
        print(f"Error uploading dome image: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

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
        
        # Check if position is already occupied
        existing_tree = Tree.query.filter_by(
            dome_id=dome_id,
            internal_row=internal_row,  # ✅ Correct column name
            internal_col=internal_col   # ✅ Correct column name
        ).first()
        
        if existing_tree:
            return jsonify({'success': False, 'error': 'Position already occupied'})
        
        # Create new tree
        new_tree = Tree(
            name=name,
            dome_id=dome_id,
            user_id=current_user.id,
            internal_row=internal_row,  # ✅ Correct column name
            internal_col=internal_col   # ✅ Correct column name
        )
        
        db.session.add(new_tree)
        db.session.commit()
        
        # Return tree data
        tree_data = {
            'id': new_tree.id,
            'name': new_tree.name,
            'dome_id': new_tree.dome_id,
            'internal_row': new_tree.internal_row,  # ✅ Correct column name
            'internal_col': new_tree.internal_col,  # ✅ Correct column name
            'image_url': new_tree.image_url
        }
        
        return jsonify({'success': True, 'tree': tree_data})
        
    except Exception as e:
        db.session.rollback()
        print(f"Error adding tree: {str(e)}")
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
    """Update dome grid size (global or farm-specific)"""
    try:
        data = request.get_json()
        rows = data.get('rows')
        cols = data.get('cols')
        farm_id = data.get('farm_id')  # ✅ Get farm_id from request
        
        print(f"🔧 Updating dome grid size to {rows}x{cols} (farm_id: {farm_id})")
        
        if not rows or not cols:
            return jsonify({'success': False, 'error': 'Rows and columns are required'})
        
        if rows < 1 or rows > 100 or cols < 1 or cols > 100:
            return jsonify({'success': False, 'error': 'Grid size must be between 1 and 100'})
        
        # ✅ FIXED: Update farm-specific or global dome settings
        success = update_grid_settings('dome', rows, cols, current_user.id, farm_id)
        
        if success:
            if farm_id:
                print(f"✅ Farm {farm_id} dome grid size updated to {rows}x{cols}")
            else:
                print(f"✅ Global dome grid size updated to {rows}x{cols}")
            return jsonify({'success': True})
        else:
            return jsonify({'success': False, 'error': 'Failed to update grid settings'})
        
    except Exception as e:
        print(f"❌ Error updating dome grid size: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})
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
        rows = data.get('rows', 8)
        cols = data.get('cols', 8)
        
        print(f"🔧 Updating Farm {farm_id} dome grid size to {rows}x{cols}")
        
        # Validate size
        if rows < 1 or cols < 1 or rows > 100 or cols > 100:
            return jsonify({'success': False, 'error': 'Grid size must be between 1x1 and 100x100'}), 400
        
        # Update farm-specific dome grid settings
        success = update_grid_settings('dome', rows, cols, current_user.id, farm_id)
        
        if success:
            print(f"✅ Farm {farm_id} dome grid size updated to {rows}x{cols}")
            return jsonify({'success': True})
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
    """User profile page"""
    try:
        # Get user statistics
        farms_count = Farm.query.filter_by(user_id=current_user.id).count()
        domes_count = Dome.query.filter_by(user_id=current_user.id).count()
        trees_count = Tree.query.filter_by(user_id=current_user.id).count()
        
        # Get grid settings
        farm_grid = get_grid_settings('farm', current_user.id)
        dome_grid = get_grid_settings('dome', current_user.id)
        
        return render_template('profile.html',
                             user=current_user,
                             farms_count=farms_count,
                             domes_count=domes_count,
                             trees_count=trees_count,
                             farm_grid=farm_grid,
                             dome_grid=dome_grid)
                             
    except Exception as e:
        print(f"Error in profile route: {str(e)}")
        flash('Error loading profile', 'error')
        return redirect(url_for('farms'))
@app.route('/dome_info/<int:dome_id>')
@login_required
def dome_info(dome_id):
    import time
    
    dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
    if not dome:
        abort(404)
    
    # ✅ FIXED: Add timestamp for cache busting
    timestamp = int(time.time())
    
    return render_template('dome_info.html', dome=dome, timestamp=timestamp)


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

@app.route('/move_tree/<int:tree_id>', methods=['POST'])
@login_required
def move_tree(tree_id):
    try:
        data = request.get_json()
        new_row = data.get('internal_row')
        new_col = data.get('internal_col')
        
        # Get the tree to move
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'})
        
        # Check if target position is occupied
        target_tree = Tree.query.filter_by(
            dome_id=tree.dome_id,
            internal_row=new_row,
            internal_col=new_col
        ).first()
        
        swapped = False
        swapped_tree_data = None
        
        if target_tree and target_tree.id != tree_id:
            # Swap positions
            old_row = tree.internal_row
            old_col = tree.internal_col
            
            # Move target tree to original position
            target_tree.internal_row = old_row
            target_tree.internal_col = old_col
            
            swapped = True
            swapped_tree_data = {
                'id': target_tree.id,
                'internal_row': old_row,
                'internal_col': old_col
            }
        
        # Move the dragged tree to new position
        tree.internal_row = new_row
        tree.internal_col = new_col
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'swapped': swapped,
            'swapped_tree': swapped_tree_data
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error moving tree: {str(e)}")
        return jsonify({'success': False, 'error': str(e)})

@app.route('/swap_trees', methods=['POST'])
@login_required
def swap_trees():
    try:
        data = request.get_json()
        tree1_id = data.get('tree1_id')
        tree2_id = data.get('tree2_id')
        
        if not tree1_id or not tree2_id:
            return jsonify({'success': False, 'error': 'Both tree IDs are required'}), 400
        
        # Get both trees
        tree1 = Tree.query.filter_by(id=tree1_id, user_id=current_user.id).first()
        tree2 = Tree.query.filter_by(id=tree2_id, user_id=current_user.id).first()
        
        if not tree1 or not tree2:
            return jsonify({'success': False, 'error': 'One or both trees not found'}), 404
        
        # Store original positions
        tree1_row, tree1_col = tree1.row, tree1.col
        tree2_row, tree2_col = tree2.row, tree2.col
        
        print(f"Swapping trees: {tree1.name} ({tree1_row},{tree1_col}) <-> {tree2.name} ({tree2_row},{tree2_col})")
        
        # Use temporary position to avoid UNIQUE constraint
        # Step 1: Move tree1 to temporary position
        tree1.row = -999  # Use a position that's guaranteed to be unique
        tree1.col = -999
        db.session.flush()  # Apply to database but don't commit
        
        # Step 2: Move tree2 to tree1's original position
        tree2.row = tree1_row
        tree2.col = tree1_col
        db.session.flush()
        
        # Step 3: Move tree1 to tree2's original position
        tree1.row = tree2_row
        tree1.col = tree2_col
        db.session.flush()
        
        # Commit all changes
        db.session.commit()
        
        print(f"Trees swapped successfully: {tree1.name} now at ({tree1.row},{tree1.col}), {tree2.name} now at ({tree2.row},{tree2.col})")
        
        return jsonify({
            'success': True,
            'message': f'Trees {tree1.name} and {tree2.name} swapped successfully'
        })
        
    except Exception as e:
        print(f"Error swapping trees: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

# ============= TREE IMAGE MANAGEMENT =============

@app.route('/upload_tree_image/<int:tree_id>', methods=['POST'])
@login_required
def upload_tree_image(tree_id):
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            # Create trees directory if it doesn't exist
            trees_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'trees')
            os.makedirs(trees_dir, exist_ok=True)
            
            # Delete old image if exists
            if tree.image_url:
                try:
                    old_filename = tree.image_url.split('/')[-1]
                    old_file_path = os.path.join(trees_dir, old_filename)
                    if os.path.exists(old_file_path):
                        os.remove(old_file_path)
                except Exception as e:
                    print(f"Error deleting old tree image: {e}")
            
            # Generate unique filename
            timestamp = int(time.time())
            file_extension = file.filename.rsplit('.', 1)[1].lower()
            filename = f"tree_{tree_id}_{timestamp}_{secrets.token_hex(8)}.{file_extension}"
            
            # Save file
            file_path = os.path.join(trees_dir, filename)
            file.save(file_path)
            
            # Update tree image URL
            tree.image_url = f"/static/uploads/trees/{filename}"
            
            db.session.commit()
            
            return jsonify({
                'success': True, 
                'image_url': tree.image_url,
                'message': 'Tree image uploaded successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Invalid file type'}), 400
            
    except Exception as e:
        print(f"Error uploading tree image: {e}")
        db.session.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500

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
    """API endpoint to get user statistics"""
    try:
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

if __name__ == '__main__':
    # Create upload directories
    os.makedirs(os.path.join(UPLOAD_FOLDER, 'trees'), exist_ok=True)
    os.makedirs(os.path.join(UPLOAD_FOLDER, 'domes'), exist_ok=True)
    
    # Run the application
    app.run(debug=True, host='0.0.0.0', port=5000)