import os
from dotenv import load_dotenv
import qrcode
import io
from flask import current_app, make_response
import base64
from PIL import Image

# Load environment variables from .env file
load_dotenv()

# Now import other modules
from flask import Flask, render_template, request, jsonify, send_from_directory, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from models import db, Dome, Row, Tree, GridSettings, User
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

# ✅ FIXED: Database configuration for both development and production
def get_database_url():
    """Get database URL based on environment"""
    # Check if we're on Render (production)
    if os.getenv('RENDER'):
        # Use PostgreSQL on Render
        database_url = os.getenv('DATABASE_URL')
        if database_url and database_url.startswith('postgres://'):
            # Fix for SQLAlchemy 1.4+ compatibility
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        return database_url
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
print(f"Database URL: {DATABASE_URL[:50]}..." if DATABASE_URL else "No DATABASE_URL")

# Initialize Flask-Login
login_manager = LoginManager()
life_updater = TreeLifeUpdater(DATABASE_URL)

def create_app():
    app = Flask(__name__)
    
    # ✅ FIXED: Production-ready configuration
    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    
    # ✅ NEW: Production security settings
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
    
    with app.app_context():
        try:
            # ✅ NEW: Create tables and initialize defaults
            db.create_all()
            initialize_defaults()
            print("✅ Database initialized successfully")
        except Exception as e:
            print(f"❌ Database initialization error: {e}")
            
    return app

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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

def initialize_defaults():
    """Initialize default grid settings"""
    if not GridSettings.query.first():
        default_grid = GridSettings(rows=5, cols=5)
        db.session.add(default_grid)
        db.session.commit()

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def initialize_scheduler():
    """Initialize the daily life updater when the app starts"""
    global life_updater
    try:
        life_updater.start_scheduler()
        print("Tree life updater scheduler initialized successfully")
    except Exception as e:
        print(f"Failed to initialize scheduler: {str(e)}")

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

@app.route('/debug/database')
def debug_database():
    try:
        user_count = User.query.count()
        dome_count = Dome.query.count()
        tree_count = Tree.query.count()
        
        return jsonify({
            'database_uri': app.config['SQLALCHEMY_DATABASE_URI'],
            'users': user_count,
            'domes': dome_count,
            'trees': tree_count,
            'current_user': current_user.username if current_user.is_authenticated else 'Not logged in'
        })
    except Exception as e:
        return jsonify({'error': str(e)})

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
                return jsonify({'success': True, 'message': 'Login successful'})
            else:
                print("Invalid username or password")
                return jsonify({'success': False, 'error': 'Invalid username or password'}), 401
                
        except Exception as e:
            print(f"Login error: {e}")
            return jsonify({'success': False, 'error': 'Login failed due to server error'}), 500
    
    return render_template('auth/login.html')
@app.route('/api/auth/status')
def auth_status():
    """Check if user is logged in"""
    if current_user.is_authenticated:
        return jsonify({
            'authenticated': True,
            'user': {
                'id': current_user.id,
                'username': current_user.username,
                'email': current_user.email
            }
        })
    else:
        return jsonify({'authenticated': False})
@app.route('/')
@login_required
def index():
    # ✅ NEW: Extend session if user is active
    from flask import session
    session.permanent = True
    
    grid = GridSettings.query.first()
    if not grid:
        grid = GridSettings()
        db.session.add(grid)
        db.session.commit()
    
    # Get only current user's domes
    domes = Dome.query.filter_by(user_id=current_user.id).order_by(Dome.grid_row, Dome.grid_col).all()
    
    return render_template('index.html', 
                         grid_rows=grid.rows,
                         grid_cols=grid.cols,
                         domes=domes,
                         user=current_user)
@app.route('/debug/session')
def debug_session():
    from flask import session
    return jsonify({
        'session_data': dict(session),
        'permanent': session.permanent,
        'user_authenticated': current_user.is_authenticated,
        'user_id': current_user.id if current_user.is_authenticated else None
    })
@app.route('/logout')
@login_required
def logout():
    logout_user()
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            email = data.get('email', '').strip()
            
            print(f"Forgot password request for email: {email}")
            
            if not email:
                return jsonify({'success': False, 'error': 'Email is required'}), 400
            
            user = User.query.filter_by(email=email).first()
            print(f"User found: {user is not None}")
            
            if not user:
                # Don't reveal if email exists or not for security
                return jsonify({'success': True, 'message': 'If your email is registered, you will receive a reset link shortly.'})
            
            # Generate reset token
            reset_token = user.generate_reset_token()
            db.session.commit()
            print(f"Reset token generated: {reset_token[:10]}...")
            
            # Send reset email (this just prints to console for now)
            try:
                send_reset_email(user.email, reset_token, user.username)
                return jsonify({'success': True, 'message': 'Password reset link has been printed to the console (email disabled for development).'})
            except Exception as email_error:
                print(f"Email sending error: {email_error}")
                return jsonify({'success': True, 'message': 'Reset token generated. Check the console for the reset link.'})
                
        except Exception as e:
            print(f"Forgot password error: {e}")
            db.session.rollback()
            return jsonify({'success': False, 'error': f'Database error: {str(e)}'}), 500
    
    return render_template('auth/forgot_password.html')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    token = request.args.get('token') if request.method == 'GET' else request.json.get('token')
    
    if not token:
        return render_template('auth/reset_password.html', error='Invalid reset link')
    
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.verify_reset_token(token):
        return render_template('auth/reset_password.html', error='Invalid or expired reset link')
    
    if request.method == 'POST':
        data = request.get_json()
        new_password = data.get('new_password', '')
        confirm_password = data.get('confirm_password', '')
        
        if len(new_password) < 6:
            return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
        
        if new_password != confirm_password:
            return jsonify({'success': False, 'error': 'Passwords do not match'}), 400
        
        # Update password
        user.set_password(new_password)
        user.clear_reset_token()
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Password reset successfully! You can now login.'})
    
    return render_template('auth/reset_password.html', token=token)

@app.route('/profile')
@login_required
def profile():
    return render_template('auth/profile.html', user=current_user)

@app.route('/change_password', methods=['POST'])
@login_required
def change_password():
    data = request.get_json()
    
    current_password = data.get('current_password', '')
    new_password = data.get('new_password', '')
    confirm_password = data.get('confirm_password', '')
    
    if not current_user.check_password(current_password):
        return jsonify({'success': False, 'error': 'Current password is incorrect'}), 400
    
    if len(new_password) < 6:
        return jsonify({'success': False, 'error': 'New password must be at least 6 characters'}), 400
    
    if new_password != confirm_password:
        return jsonify({'success': False, 'error': 'New passwords do not match'}), 400
    
    current_user.set_password(new_password)
    db.session.commit()
    
    return jsonify({'success': True, 'message': 'Password changed successfully'})

# ============= LIFE DAY MANAGEMENT ROUTES =============

@app.route('/admin/update_tree_life', methods=['POST'])
def manual_update_tree_life():
    """Manual endpoint to trigger life days update"""
    try:
        affected_rows = life_updater.run_manual_update()
        return jsonify({
            "success": True, 
            "message": f"Tree life days updated successfully for {affected_rows} trees"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/admin/scheduler_status')
def scheduler_status():
    """Check if the scheduler is running"""
    try:
        status = life_updater.get_scheduler_status()
        return jsonify(status)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ============= MAIN ROUTES =============



@app.route('/dome_info/<int:dome_id>', methods=['GET'])
@login_required
def dome_info(dome_id):
    dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
    if not dome:
        return jsonify(success=False, error="Dome not found"), 404
    return render_template('dome_info.html', dome=dome)

@app.route('/grid/<int:dome_id>')
@login_required
def view_grid(dome_id):
    dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
    if not dome:
        return jsonify(success=False, error="Dome not found"), 404
    
    # Get only current user's trees for this dome
    trees_query = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
    
    # Convert trees to dictionaries for JSON serialization
    trees = []
    for tree in trees_query:
        tree_dict = {
            'id': tree.id,
            'name': tree.name,
            'row': tree.row,
            'col': tree.col,
            'dome_id': tree.dome_id
        }
        
        if hasattr(tree, 'image_url') and tree.image_url:
            tree_dict['image_url'] = tree.image_url
        if hasattr(tree, 'info') and tree.info:
            tree_dict['info'] = tree.info
        if hasattr(tree, 'life_days') and tree.life_days is not None:
            tree_dict['life_days'] = tree.life_days
            
        trees.append(tree_dict)
    
    return render_template('grid.html', 
                         dome=dome,
                         rows=dome.internal_rows,
                         cols=dome.internal_cols,
                         trees=trees)

@app.route('/tree_info/<int:tree_id>')
@login_required
def tree_info(tree_id):
    import time
    
    tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
    if not tree:
        return jsonify(success=False, error="Tree not found"), 404
    
    # Force refresh from database
    db.session.refresh(tree)
    
    timestamp = int(time.time())
    
    response = make_response(render_template('tree_info.html', tree=tree, timestamp=timestamp))
    
    # Add cache-busting headers
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    
    return response

# ============= DOME MANAGEMENT =============

@app.route('/add_dome', methods=['POST'])
@login_required
def add_dome():
    data = request.json
    name = data.get('name', 'โดมใหม่')
    grid_row = data.get('grid_row', 0)
    grid_col = data.get('grid_col', 0)
    
    # Validate position
    grid = GridSettings.query.first()
    if grid_row >= grid.rows or grid_col >= grid.cols:
        return jsonify(success=False, error="Position out of bounds"), 400
        
    existing = Dome.query.filter_by(grid_row=grid_row, grid_col=grid_col, user_id=current_user.id).first()
    if existing:
        return jsonify(success=False, error="Position occupied"), 400

    # Create new dome with user_id
    dome = Dome(
        name=name,
        internal_rows=10,
        internal_cols=10,
        grid_row=grid_row,
        grid_col=grid_col,
        user_id=current_user.id
    )
    
    db.session.add(dome)
    db.session.commit()
    
    return jsonify({
        'id': dome.id, 
        'name': dome.name,
        'grid_row': dome.grid_row,
        'grid_col': dome.grid_col,
        'internal_rows': dome.internal_rows,
        'internal_cols': dome.internal_cols
    })

@app.route('/update_dome_name/<int:dome_id>', methods=['POST'])
@login_required
def update_dome_name(dome_id):
    dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
    if not dome:
        return jsonify(success=False, error="Dome not found"), 404
    
    data = request.json
    dome.name = data.get('name', dome.name)
    db.session.commit()
    
    return jsonify(success=True)

@app.route('/delete_dome/<int:dome_id>', methods=['DELETE'])
@login_required
def delete_dome(dome_id):
    dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
    if not dome:
        return jsonify(success=False, error="Dome not found"), 404
    
    try:
        db.session.delete(dome)
        db.session.commit()
        return jsonify(success=True)
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500

@app.route('/move_dome/<int:dome_id>', methods=['POST'])
@login_required
def move_dome(dome_id):
    data = request.json
    
    # Get dome and check ownership
    dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
    if not dome:
        return jsonify(success=False, error="Dome not found"), 404

    # Check if data contains the expected keys
    if 'grid_row' not in data or 'grid_col' not in data:
        new_row = data.get('row')
        new_col = data.get('col')
        
        if new_row is None or new_col is None:
            return jsonify(success=False, error="Missing position data"), 400
    else:
        new_row = data.get('grid_row')
        new_col = data.get('grid_col')

    # Convert to integers if they're strings
    try:
        new_row = int(new_row)
        new_col = int(new_col)
    except (ValueError, TypeError):
        return jsonify(success=False, error="Invalid position data"), 400

    # Validate grid bounds
    grid = GridSettings.query.first()
    if not grid:
        return jsonify(success=False, error="Grid settings not found"), 500
        
    if new_row >= grid.rows or new_col >= grid.cols or new_row < 0 or new_col < 0:
        return jsonify(success=False, error="Position out of bounds"), 400

    # Check for existing dome in target position (only check current user's domes)
    existing_dome = Dome.query.filter(
        Dome.id != dome_id,
        Dome.grid_row == new_row, 
        Dome.grid_col == new_col,
        Dome.user_id == current_user.id
    ).first()
    
    if existing_dome:
        # SWAP the domes instead of returning an error
        print(f"Swapping dome {dome_id} with dome {existing_dome.id}")
        
        # Store original position of the dome being moved
        original_row = dome.grid_row
        original_col = dome.grid_col
        
        # Move the first dome to the target position
        dome.grid_row = new_row
        dome.grid_col = new_col
        
        # Move the existing dome to the original position
        existing_dome.grid_row = original_row
        existing_dome.grid_col = original_col
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'swapped': True,
            'dome1': {
                'id': dome.id,
                'grid_row': dome.grid_row,
                'grid_col': dome.grid_col
            },
            'dome2': {
                'id': existing_dome.id,
                'grid_row': existing_dome.grid_row,
                'grid_col': existing_dome.grid_col
            }
        })
    else:
        # No dome in target position, just move normally
        dome.grid_row = new_row
        dome.grid_col = new_col
        db.session.commit()
        
        return jsonify({
            'success': True,
            'swapped': False,
            'dome': {
                'id': dome.id,
                'grid_row': dome.grid_row,
                'grid_col': dome.grid_col
            }
        })

@app.route('/swap_domes/<int:dome_id1>/<int:dome_id2>', methods=['POST'])
@login_required
def swap_domes(dome_id1, dome_id2):
    dome1 = Dome.query.filter_by(id=dome_id1, user_id=current_user.id).first()
    dome2 = Dome.query.filter_by(id=dome_id2, user_id=current_user.id).first()
    
    if not dome1 or not dome2:
        return jsonify(success=False, error="Dome not found"), 404
    
    # Swap positions
    dome1.grid_row, dome2.grid_row = dome2.grid_row, dome1.grid_row
    dome1.grid_col, dome2.grid_col = dome2.grid_col, dome1.grid_col
    
    db.session.commit()
    
    return jsonify({
        'success': True,
        'dome1': {'id': dome1.id, 'grid_row': dome1.grid_row, 'grid_col': dome1.grid_col},
        'dome2': {'id': dome2.id, 'grid_row': dome2.grid_row, 'grid_col': dome2.grid_col}
    })

@app.route('/update_dome_grid/<int:dome_id>', methods=['POST'])
@login_required
def update_dome_grid(dome_id):
    try:
        dome = db.session.get(Dome, dome_id)
        if not dome:
            return jsonify({'error': 'Dome not found'}), 404
        
        data = request.get_json()
        rows = data.get('rows')
        cols = data.get('cols')
        
        if not rows or not cols:
            return jsonify({'error': 'Rows and cols are required'}), 400
        
        # Validate grid size
        if rows < 1 or cols < 1 or rows > 1000 or cols > 1000:
            return jsonify({'error': 'Grid size must be between 1x1 and 1000x1000'}), 400
        
        # Check if any trees would be out of bounds
        out_of_bounds_trees = db.session.query(Tree).filter(
            Tree.dome_id == dome_id,
            Tree.user_id == current_user.id,
            db.or_(Tree.row >= rows, Tree.col >= cols)
        ).all()
        
        if out_of_bounds_trees:
            tree_names = [tree.name for tree in out_of_bounds_trees]
            return jsonify({
                'error': f'Cannot resize: Trees would be out of bounds: {", ".join(tree_names)}'
            }), 400
        
        # Update dome grid size
        dome.internal_rows = rows
        dome.internal_cols = cols
        db.session.commit()
        
        return jsonify({'success': True})
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Server error: {str(e)}'}), 500

# ============= IMAGE UPLOAD ROUTES =============

@app.route('/upload_tree_image/<int:tree_id>', methods=['POST'])
@login_required
def upload_tree_image(tree_id):
    try:
        print(f"📤 Uploading image for tree {tree_id}")
        
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            # Create secure filename with timestamp
            import time
            timestamp = int(time.time())
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            filename = f"tree_{tree_id}_{timestamp}_{name}{ext}"
            
            # Get upload folder from config or use default
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
            
            # Ensure uploads directory exists
            os.makedirs(upload_folder, exist_ok=True)
            
            # Save file
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            print(f"💾 File saved to: {filepath}")
            
            # Update tree image URL
            image_url = f"/uploads/{filename}"
            
            try:
                # Remove old image file if exists
                if hasattr(tree, 'image_url') and tree.image_url:
                    old_filename = tree.image_url.split('/')[-1]
                    old_filepath = os.path.join(upload_folder, old_filename)
                    if os.path.exists(old_filepath):
                        os.remove(old_filepath)
                        print(f"🗑️ Removed old image: {old_filepath}")
                
                tree.image_url = image_url
                db.session.commit()
                print("✅ Updated tree image_url")
                    
            except Exception as e:
                print(f"⚠️ Error updating database: {e}")
                # Fallback to raw SQL if needed
                try:
                    db.session.execute(
                        'UPDATE tree SET image_url = :image_url WHERE id = :tree_id',
                        {'image_url': image_url, 'tree_id': tree_id}
                    )
                    db.session.commit()
                    print("✅ Updated tree image_url via raw SQL")
                except Exception as sql_error:
                    print(f"❌ SQL update failed: {sql_error}")
            
            return jsonify({
                'success': True,
                'image_url': image_url,
                'filename': filename,
                'message': 'Tree image uploaded successfully'
            })
                
        else:
                return jsonify({'success': False, 'error': 'Invalid file type. Please use PNG, JPG, JPEG, or GIF'}), 400
                
    except Exception as e:
        print(f"❌ Upload error: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Upload failed: {str(e)}'}), 500

@app.route('/remove_tree_image/<int:tree_id>', methods=['POST'])
@login_required
def remove_tree_image(tree_id):
    try:
        print(f"🗑️ Removing image for tree {tree_id}")
        
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        # Remove image file if exists
        if hasattr(tree, 'image_url') and tree.image_url:
            filename = tree.image_url.split('/')[-1]
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
            filepath = os.path.join(upload_folder, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"🗑️ Removed image file: {filepath}")
            
            # Clear image URL from database
            tree.image_url = None
            db.session.commit()
            print("✅ Cleared tree image_url")
        
        return jsonify({
            'success': True,
            'message': 'Tree image removed successfully'
        })
        
    except Exception as e:
        print(f"❌ Remove error: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Remove failed: {str(e)}'}), 500

@app.route('/upload_dome_image/<int:dome_id>', methods=['POST'])
@login_required 
def upload_dome_image(dome_id):
    try:
        print(f"📤 Uploading image for dome {dome_id}")
        
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': 'No image file provided'}), 400
        
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'No file selected'}), 400
        
        if file and allowed_file(file.filename):
            # Create secure filename with timestamp
            import time
            timestamp = int(time.time())
            filename = secure_filename(file.filename)
            name, ext = os.path.splitext(filename)
            filename = f"dome_{dome_id}_{timestamp}_{name}{ext}"
            
            # Get upload folder from config or use default
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
            
            # Ensure uploads directory exists
            os.makedirs(upload_folder, exist_ok=True)
            
            # Save file
            filepath = os.path.join(upload_folder, filename)
            file.save(filepath)
            print(f"💾 File saved to: {filepath}")
            
            # Update dome image URL
            image_url = f"/uploads/{filename}"
            
            try:
                # Remove old image file if exists
                if hasattr(dome, 'image_url') and dome.image_url:
                    old_filename = dome.image_url.split('/')[-1]
                    old_filepath = os.path.join(upload_folder, old_filename)
                    if os.path.exists(old_filepath):
                        os.remove(old_filepath)
                        print(f"🗑️ Removed old image: {old_filepath}")
                
                dome.image_url = image_url
                db.session.commit()
                print("✅ Updated dome image_url")
                    
            except Exception as e:
                print(f"⚠️ Error updating database: {e}")
                # Fallback to raw SQL if needed
                try:
                    db.session.execute(
                        'UPDATE dome SET image_url = :image_url WHERE id = :dome_id',
                        {'image_url': image_url, 'dome_id': dome_id}
                    )
                    db.session.commit()
                    print("✅ Updated dome image_url via raw SQL")
                except Exception as sql_error:
                    print(f"❌ SQL update failed: {sql_error}")
            
            return jsonify({
                'success': True,
                'image_url': image_url,
                'filename': filename,
                'message': 'Dome image uploaded successfully'
            })
                
        else:
            return jsonify({'success': False, 'error': 'Invalid file type. Please use PNG, JPG, JPEG, or GIF'}), 400
            
    except Exception as e:
        print(f"❌ Upload error: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Upload failed: {str(e)}'}), 500

@app.route('/remove_dome_image/<int:dome_id>', methods=['POST'])
@login_required
def remove_dome_image(dome_id):
    try:
        print(f"🗑️ Removing image for dome {dome_id}")
        
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        # Remove image file if exists
        if hasattr(dome, 'image_url') and dome.image_url:
            filename = dome.image_url.split('/')[-1]
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
            filepath = os.path.join(upload_folder, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"🗑️ Removed image file: {filepath}")
            
            # Clear image URL from database
            dome.image_url = None
            db.session.commit()
            print("✅ Cleared dome image_url")
        
        return jsonify({
            'success': True,
            'message': 'Dome image removed successfully'
        })
        
    except Exception as e:
        print(f"❌ Remove error: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Remove failed: {str(e)}'}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    try:
        upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
        
        response = make_response(send_from_directory(upload_folder, filename))
        
        # Add headers to prevent caching issues
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response
    except Exception as e:
        print(f"❌ Error serving file {filename}: {e}")
        return jsonify({'error': 'File not found'}), 404

# ============= QR CODE ROUTES =============

@app.route('/generate_qr/<int:tree_id>', methods=['POST'])
@login_required
def generate_qr(tree_id):
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'error': 'Tree not found'}), 404
        
        data = request.get_json()
        tree_url = data.get('url') if data else None
        
        if not tree_url:
            tree_url = f"{request.url_root}tree_info/{tree_id}"
        
        # Generate QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
        qr.add_data(tree_url)
        qr.make(fit=True)
        
        qr_img = qr.make_image(fill_color="black", back_color="white")
        
        img_buffer = io.BytesIO()
        qr_img.save(img_buffer, format='PNG')
        img_buffer.seek(0)
        
        qr_base64 = base64.b64encode(img_buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'qr_code': qr_base64,
            'url': tree_url,
            'tree_name': tree.name
        })
        
    except Exception as e:
        print(f"Error generating QR code: {e}")
        return jsonify({'error': f'Failed to generate QR code: {str(e)}'}), 500

# ============= API ROUTES =============

@app.route('/api/trees/<int:dome_id>')
@login_required
def get_trees_api(dome_id):
    try:
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'error': 'Dome not found'}), 404
        
        trees = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()
        
        trees_data = []
        for tree in trees:
            tree_dict = {
                'id': tree.id,
                'name': tree.name,
                'row': tree.row,
                'col': tree.col,
                'dome_id': tree.dome_id
            }
            
            # Include image URL if available
            if hasattr(tree, 'image_url') and tree.image_url:
                tree_dict['image_url'] = tree.image_url
            
            # Include other attributes if available
            if hasattr(tree, 'info') and tree.info:
                tree_dict['info'] = tree.info
            if hasattr(tree, 'life_days') and tree.life_days is not None:
                tree_dict['life_days'] = tree.life_days
                
            trees_data.append(tree_dict)
        
        return jsonify({
            'success': True,
            'trees': trees_data,
            'dome': {
                'id': dome.id,
                'name': dome.name,
                'rows': dome.internal_rows,
                'cols': dome.internal_cols
            }
        })
        
    except Exception as e:
        print(f"Error getting trees: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/tree/<int:tree_id>')
@login_required
def get_single_tree_api(tree_id):
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify({'success': False, 'error': 'Tree not found'}), 404
        
        # Force refresh from database
        db.session.refresh(tree)
        
        tree_data = {
            'id': tree.id,
            'name': tree.name,
            'row': tree.row,
            'col': tree.col,
            'dome_id': tree.dome_id
        }
        
        # Include image URL if available
        if hasattr(tree, 'image_url') and tree.image_url:
            tree_data['image_url'] = tree.image_url
            print(f"✅ API returning image_url: {tree.image_url}")
        else:
            print(f"⚠️ No image_url found for tree {tree_id}")
        
        # Include other attributes if available
        if hasattr(tree, 'info') and tree.info:
            tree_data['info'] = tree.info
        if hasattr(tree, 'life_days') and tree.life_days is not None:
            tree_data['life_days'] = tree.life_days
            
        return jsonify({
            'success': True,
            'tree': tree_data
        })
        
    except Exception as e:
        print(f"❌ Error getting tree: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/dome/<int:dome_id>')
@login_required
def get_single_dome_api(dome_id):
    try:
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found'}), 404
        
        dome_data = {
            'id': dome.id,
            'name': dome.name,
            'grid_row': dome.grid_row,
            'grid_col': dome.grid_col,
            'internal_rows': dome.internal_rows,
            'internal_cols': dome.internal_cols
        }
        
        # Include image URL if available
        if hasattr(dome, 'image_url') and dome.image_url:
            dome_data['image_url'] = dome.image_url
            
        return jsonify({
            'success': True,
            'dome': dome_data
        })
        
    except Exception as e:
        print(f"Error getting dome: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

# ============= TREE MANAGEMENT =============

@app.route('/add_tree', methods=['POST'])
@login_required
def add_tree():
    try:
        data = request.json
        name = data.get('name', 'ต้นใหม่')
        row = data.get('row', 0)
        col = data.get('col', 0)
        dome_id = data.get('dome_id')
        
        # Validate dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify(success=False, error="Dome not found"), 404
        
        # Validate position
        if row >= dome.internal_rows or col >= dome.internal_cols:
            return jsonify(success=False, error="Position out of bounds"), 400
        
        # Check if position is occupied
        existing = Tree.query.filter_by(dome_id=dome_id, row=row, col=col, user_id=current_user.id).first()
        if existing:
            return jsonify(success=False, error="Position occupied"), 400
        
        # Create new tree
        tree = Tree(
            name=name,
            row=row,
            col=col,
            dome_id=dome_id,
            user_id=current_user.id,
            info='',
            life_days=0
        )
        
        db.session.add(tree)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'tree': {
                'id': tree.id,
                'name': tree.name,
                'row': tree.row,
                'col': tree.col,
                'dome_id': tree.dome_id,
                'info': tree.info,
                'life_days': tree.life_days
            }
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"Error adding tree: {e}")
        return jsonify(success=False, error=str(e)), 500

@app.route('/update_tree/<int:tree_id>', methods=['POST'])
@login_required
def update_tree(tree_id):
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify(success=False, error="Tree not found"), 404
        
        data = request.json
        tree.name = data.get('name', tree.name)
        tree.info = data.get('info', tree.info)
        tree.life_days = data.get('life_days', tree.life_days)
        
        db.session.commit()
        
        return jsonify(success=True)
        
    except Exception as e:
        db.session.rollback()
        print(f"Error updating tree: {e}")
        return jsonify(success=False, error=str(e)), 500

@app.route('/delete_tree/<int:tree_id>', methods=['DELETE'])
@login_required
def delete_tree(tree_id):
    try:
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify(success=False, error="Tree not found"), 404
        
        # Remove image file if exists
        if hasattr(tree, 'image_url') and tree.image_url:
            filename = tree.image_url.split('/')[-1]
            upload_folder = current_app.config.get('UPLOAD_FOLDER', 'uploads')
            filepath = os.path.join(upload_folder, filename)
            if os.path.exists(filepath):
                os.remove(filepath)
                print(f"🗑️ Removed image file: {filepath}")
        
        db.session.delete(tree)
        db.session.commit()
        
        return jsonify(success=True)
        
    except Exception as e:
        db.session.rollback()
        print(f"Error deleting tree: {e}")
        return jsonify(success=False, error=str(e)), 500

@app.route('/move_tree/<int:tree_id>', methods=['POST'])
@login_required
def move_tree(tree_id):
    try:
        data = request.json
        tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()
        if not tree:
            return jsonify(success=False, error="Tree not found"), 404
        
        new_row = data.get('row')
        new_col = data.get('col')
        
        # Validate new position
        dome = Dome.query.filter_by(id=tree.dome_id, user_id=current_user.id).first()
        if new_row >= dome.internal_rows or new_col >= dome.internal_cols:
            return jsonify(success=False, error="Position out of bounds"), 400
        
        # Check if position is occupied
        existing = Tree.query.filter(
            Tree.id != tree_id,
            Tree.dome_id == tree.dome_id,
            Tree.row == new_row,
            Tree.col == new_col,
            Tree.user_id == current_user.id
        ).first()
        
        if existing:
            # Swap positions
            existing.row, tree.row = tree.row, new_row
            existing.col, tree.col = tree.col, new_col
        else:
            # Move to empty position
            tree.row = new_row
            tree.col = new_col
        
        db.session.commit()
        return jsonify(success=True)
        
    except Exception as e:
        db.session.rollback()
        print(f"Error moving tree: {e}")
        return jsonify(success=False, error=str(e)), 500

# ============= GRID SETTINGS =============

@app.route('/update_grid_settings', methods=['POST'])
@login_required
def update_grid_settings():
    try:
        data = request.json
        rows = data.get('rows', 5)
        cols = data.get('cols', 5)
        
        # Validate grid size
        if rows < 1 or cols < 1 or rows > 50 or cols > 50:
            return jsonify(success=False, error="Grid size must be between 1x1 and 50x50"), 400
        
        # Check if any domes would be out of bounds
        out_of_bounds_domes = Dome.query.filter(
            Dome.user_id == current_user.id,
            db.or_(Dome.grid_row >= rows, Dome.grid_col >= cols)
        ).all()
        
        if out_of_bounds_domes:
            dome_names = [dome.name for dome in out_of_bounds_domes]
            return jsonify({
                'success': False,
                'error': f'Cannot resize: Domes would be out of bounds: {", ".join(dome_names)}'
            }), 400
        
        # Update grid settings
        grid = GridSettings.query.first()
        if not grid:
            grid = GridSettings()
            db.session.add(grid)
        
        grid.rows = rows
        grid.cols = cols
        db.session.commit()
        
        return jsonify(success=True)
        
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500

# ============= ERROR HANDLERS =============

@app.errorhandler(404)
def not_found_error(error):
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    db.session.rollback()
    return render_template('errors/500.html'), 500

# ============= MAIN APPLICATION =============

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)