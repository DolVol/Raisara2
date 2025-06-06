from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Now import other modules
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_login import LoginManager, login_user, logout_user, login_required, current_user,UserMixin
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

SQLALCHEMY_DATABASE_URI = 'sqlite:///db.sqlite3'
SQLALCHEMY_TRACK_MODIFICATIONS = False
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
# Initialize the tree life updater
DATABASE_URL = SQLALCHEMY_DATABASE_URI
# Configuration
SECRET_KEY = os.getenv('SECRET_KEY', 'fallback-secret-key')
MAIL_SERVER = 'smtp.gmail.com'
MAIL_PORT = 587
MAIL_USE_TLS = True
MAIL_USERNAME = os.getenv('MAIL_USERNAME')
MAIL_PASSWORD = os.getenv('MAIL_PASSWORD') 
print(f"Loaded MAIL_USERNAME: {MAIL_USERNAME}")
print(f"Loaded SECRET_KEY: {SECRET_KEY[:20]}...")

# Initialize Flask-Login
login_manager = LoginManager()
life_updater = TreeLifeUpdater(DATABASE_URL)
def create_app():
    app = Flask(__name__)
    
    # Use the loaded configuration
    app.config['SECRET_KEY'] = SECRET_KEY
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_USERNAME')
    # ... rest of your code ...
    mail.init_app(app)
    # Initialize extensions
    db.init_app(app)
    Migrate(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'
    
    # Create uploads directory
    os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)
    
    with app.app_context():
        db.create_all()
        initialize_defaults()
        
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

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            
            username = data.get('username', '').strip()
            password = data.get('password', '')
            remember = data.get('remember', False)
            
            print(f"Login attempt for: {username}")
            
            if not username or not password:
                return jsonify({'success': False, 'error': 'Username and password are required'}), 400
            
            # Find user by username or email
            user = User.query.filter(
                (User.username == username) | (User.email == username)
            ).first()
            
            print(f"User found: {user is not None}")
            
            if user and user.check_password(password):
                login_user(user, remember=remember)
                print(f"Login successful for user: {user.username}")
                return jsonify({'success': True, 'message': 'Login successful'})
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
# ============= MAIN ROUTES =============
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
@app.route('/')
@login_required
def index():
    grid = GridSettings.query.first()
    if not grid:
        grid = GridSettings()
        db.session.add(grid)
        db.session.commit()
    
    # Get only current user's domes
    domes = Dome.query.filter_by(user_id=current_user.id).order_by(Dome.grid_row, Dome.grid_col).all()  # <-- FIX THIS
    
    return render_template('index.html', 
                         grid_rows=grid.rows,
                         grid_cols=grid.cols,
                         domes=domes,
                         user=current_user)

# 3. FIX DOME_INFO ROUTE
@app.route('/dome_info/<int:dome_id>', methods=['GET'])
@login_required
def dome_info(dome_id):
    dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()  # <-- FIX THIS
    if not dome:
        return jsonify(success=False, error="Dome not found"), 404
    return render_template('dome_info.html', dome=dome)

@app.route('/grid/<int:dome_id>')
@login_required  # <-- ADD THIS
def view_grid(dome_id):
    dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()  # <-- FIX THIS
    if not dome:
        return jsonify(success=False, error="Dome not found"), 404
    
    # Get only current user's trees for this dome
    trees_query = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()  # <-- FIX THIS
    
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
@login_required  # <-- ADD THIS
def tree_info(tree_id):
    import time
    tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()  # <-- FIX THIS
    if not tree:
        return jsonify(success=False, error="Tree not found"), 404
    
    timestamp = int(time.time())
    return render_template('tree_info.html', tree=tree, timestamp=timestamp)

# ============= FILE SERVING =============

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    try:
        # Add cache control headers to ensure fresh images
        from flask import send_from_directory, make_response
        
        response = make_response(send_from_directory(app.config['UPLOAD_FOLDER'], filename))
        
        # Add headers to prevent caching issues
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        return response
    except Exception as e:
        print(f"❌ Error serving file {filename}: {e}")
        return jsonify({'error': 'File not found'}), 404

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
        user_id=current_user.id  # <-- FIXED: added comma and user_id
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
@login_required  # <-- ADD THIS
def update_dome_name(dome_id):
    dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()  # <-- FIX THIS
    if not dome:
        return jsonify(success=False, error="Dome not found"), 404
    
    data = request.json
    dome.name = data.get('name', dome.name)
    db.session.commit()
    
    return jsonify(success=True)

@app.route('/delete_dome/<int:dome_id>', methods=['DELETE'])
@login_required  # <-- ADD THIS
def delete_dome(dome_id):
    dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()  # <-- FIX THIS
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
@login_required  # <-- ADD THIS
def swap_domes(dome_id1, dome_id2):
    dome1 = Dome.query.filter_by(id=dome_id1, user_id=current_user.id).first()  # <-- FIX THIS
    dome2 = Dome.query.filter_by(id=dome_id2, user_id=current_user.id).first()  # <-- FIX THIS
    
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

@app.route('/upload_dome_image/<int:dome_id>', methods=['POST'])
@login_required 
def upload_dome_image(dome_id):
    try:
        print(f"📤 Uploading image for dome {dome_id}")
        
        dome = db.session.get(Dome, dome_id)
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
            
            # Ensure uploads directory exists
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            # Save file
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            print(f"💾 File saved to: {filepath}")
            
            # Update dome image URL using raw SQL to ensure it works
            image_url = f"/uploads/{filename}"
            
            try:
                # First try SQLAlchemy way
                if hasattr(dome, 'image_url'):
                    dome.image_url = image_url
                    db.session.commit()
                    print("✅ Updated dome image_url via SQLAlchemy")
                else:
                    # Fallback to raw SQL
                    import sqlite3
                    conn = sqlite3.connect('db.sqlite3')
                    cursor = conn.cursor()
                    
                    # Ensure column exists
                    try:
                        cursor.execute('ALTER TABLE dome ADD COLUMN image_url VARCHAR(200)')
                        conn.commit()
                        print("✅ Added image_url column to dome table")
                    except:
                        pass  # Column already exists
                    
                    # Update the image URL
                    cursor.execute('UPDATE dome SET image_url = ? WHERE id = ?', (image_url, dome_id))
                    conn.commit()
                    conn.close()
                    print("✅ Updated dome image_url via raw SQL")
                    
                    # Refresh SQLAlchemy session
                    db.session.expire(dome)
                    
            except Exception as e:
                print(f"⚠️ Error updating database: {e}")
                # Even if database update fails, file is saved, so return success
            
            # Verify the file exists
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                print(f"✅ File verified: {filename} ({file_size} bytes)")
                
                return jsonify({
                    'success': True,
                    'image_url': image_url,
                    'filename': filename,
                    'file_size': file_size,
                    'message': 'Image uploaded successfully'
                })
            else:
                return jsonify({'success': False, 'error': 'File save failed'}), 500
                
        else:
            return jsonify({'success': False, 'error': 'Invalid file type. Please use PNG, JPG, JPEG, or GIF'}), 400
            
    except Exception as e:
        print(f"❌ Upload error: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Upload failed: {str(e)}'}), 500

@app.route('/upload_tree_image/<int:tree_id>', methods=['POST'])
@login_required
def upload_tree_image(tree_id):
    try:
        print(f"📤 Uploading image for tree {tree_id}")
        
        tree = db.session.get(Tree, tree_id)
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
            
            # Ensure uploads directory exists
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            
            # Save file
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            print(f"💾 File saved to: {filepath}")
            
            # Update tree image URL using raw SQL to ensure it works
            image_url = f"/uploads/{filename}"
            
            try:
                # First try SQLAlchemy way
                if hasattr(tree, 'image_url'):
                    tree.image_url = image_url
                    db.session.commit()
                    print("✅ Updated tree image_url via SQLAlchemy")
                else:
                    # Fallback to raw SQL
                    import sqlite3
                    conn = sqlite3.connect('db.sqlite3')
                    cursor = conn.cursor()
                    
                    # Ensure columns exist
                    try:
                        cursor.execute('ALTER TABLE tree ADD COLUMN image_url VARCHAR(200)')
                        cursor.execute('ALTER TABLE tree ADD COLUMN info TEXT')
                        cursor.execute('ALTER TABLE tree ADD COLUMN life_days INTEGER DEFAULT 0')
                        conn.commit()
                        print("✅ Added missing columns to tree table")
                    except:
                        pass  # Columns already exist
                    
                    # Update the image URL
                    cursor.execute('UPDATE tree SET image_url = ? WHERE id = ?', (image_url, tree_id))
                    conn.commit()
                    conn.close()
                    print("✅ Updated tree image_url via raw SQL")
                    
                    # Refresh SQLAlchemy session
                    db.session.expire(tree)
                    
            except Exception as e:
                print(f"⚠️ Error updating database: {e}")
                # Even if database update fails, file is saved, so return success
            
            # Verify the file exists
            if os.path.exists(filepath):
                file_size = os.path.getsize(filepath)
                print(f"✅ File verified: {filename} ({file_size} bytes)")
                
                return jsonify({
                    'success': True,
                    'image_url': image_url,
                    'filename': filename,
                    'file_size': file_size,
                    'message': 'Image uploaded successfully'
                })
            else:
                return jsonify({'success': False, 'error': 'File save failed'}), 500
                
        else:
            return jsonify({'success': False, 'error': 'Invalid file type. Please use PNG, JPG, JPEG, or GIF'}), 400
            
    except Exception as e:
        print(f"❌ Upload error: {str(e)}")
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Upload failed: {str(e)}'}), 500

# ============= QR CODE GENERATION =============

@app.route('/generate_qr/<int:tree_id>', methods=['POST'])
def generate_qr(tree_id):
    try:
        import qrcode
        import io
        import base64
        from PIL import Image
        
        # Get the URL from request
        data = request.get_json()
        url = data.get('url', request.url_root + f'tree_info/{tree_id}')
        
        # Create QR code
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=4,
        )
        qr.add_data(url)
        qr.make(fit=True)
        
        # Create QR code image with custom colors
        img = qr.make_image(fill_color="#2e8b57", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        # Encode to base64
        qr_base64 = base64.b64encode(buffer.getvalue()).decode()
        
        return jsonify({
            'success': True,
            'qr_code': qr_base64,
            'url': url
        })
        
    except ImportError:
        return jsonify({
            'success': False,
            'error': 'QR code library not installed. Please install: pip install qrcode[pil]'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'Error generating QR code: {str(e)}'
        }), 500

# ============= TREE MANAGEMENT =============

@app.route('/add_tree/<int:dome_id>/<int:row>/<int:col>', methods=['POST'])
@login_required  # <-- ADD THIS
def add_tree_to_grid(dome_id, row, col):
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        name = data.get('name', '').strip()
        if not name:
            return jsonify({'error': 'Tree name is required'}), 400

        # Get the dome and check ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()  # <-- FIX THIS
        if not dome:
            return jsonify({'error': 'Dome not found'}), 404

        # Validate position bounds
        if row < 0 or row >= dome.internal_rows or col < 0 or col >= dome.internal_cols:
            error_msg = f'Position out of bounds. Valid range: 0-{dome.internal_rows-1}, 0-{dome.internal_cols-1}'
            return jsonify({'error': error_msg}), 400

        # Check if position is already occupied (filter by user)
        existing_tree = db.session.query(Tree).filter(
            Tree.dome_id == dome_id,
            Tree.row == row,
            Tree.col == col,
            Tree.user_id == current_user.id  # <-- ADD THIS
        ).first()
        
        if existing_tree:
            return jsonify({'error': 'Position already occupied by another tree'}), 400

        # Create new tree with user_id
        tree = Tree(
            name=name,
            dome_id=dome_id,
            row=row,
            col=col,
            user_id=current_user.id  # <-- FIX SYNTAX ERROR (was missing comma)
        )

        db.session.add(tree)
        db.session.commit()
        
        return jsonify({
            'id': tree.id,
            'name': tree.name,
            'row': tree.row,
            'col': tree.col,
            'dome_id': tree.dome_id
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/update_tree/<int:tree_id>', methods=['POST'])
@login_required  # <-- ADD THIS
def update_tree(tree_id):
    tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()  # <-- FIX THIS
    if not tree:
        return jsonify(success=False, error="Tree not found"), 404
    
    data = request.json
    
    # Update tree properties
    if 'name' in data:
        tree.name = data['name']
    if 'info' in data and hasattr(tree, 'info'):
        tree.info = data['info']
    if 'life_days' in data and hasattr(tree, 'life_days'):
        tree.life_days = data['life_days']
    
    try:
        db.session.commit()
        return jsonify(success=True)
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500

@app.route('/delete_tree/<int:tree_id>', methods=['DELETE'])
@login_required  # <-- ADD THIS
def delete_tree(tree_id):
    tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()  # <-- FIX THIS
    if not tree:
        return jsonify(success=False, error="Tree not found"), 404
    
    try:
        db.session.delete(tree)
        db.session.commit()
        return jsonify(success=True)
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500

@app.route('/move_tree/<int:tree_id>', methods=['POST'])
@login_required  # <-- ADD THIS
def move_tree(tree_id):
    tree = Tree.query.filter_by(id=tree_id, user_id=current_user.id).first()  # <-- FIX THIS
    if not tree:
        return jsonify(success=False, error="Tree not found"), 404
    
    data = request.json
    new_row = data.get('new_row')
    new_col = data.get('new_col')
    
    # Convert to integers
    try:
        new_row = int(new_row)
        new_col = int(new_col)
    except (ValueError, TypeError):
        return jsonify(success=False, error="Invalid position data"), 400
    
    # Validate new position
    if (new_row < 0 or new_row >= tree.dome.internal_rows or 
        new_col < 0 or new_col >= tree.dome.internal_cols):
        return jsonify(success=False, error="Position out of bounds"), 400
    
    # Check for existing tree (filter by user)
    existing = db.session.query(Tree).filter(
        Tree.id != tree_id,
        Tree.dome_id == tree.dome_id,
        Tree.row == new_row,
        Tree.col == new_col,
        Tree.user_id == current_user.id  # <-- ADD THIS
    ).first()
    
    if existing:
        return jsonify(success=False, error="Position occupied"), 400
    
    # Update position
    tree.row = new_row
    tree.col = new_col
    db.session.commit()
    
    return jsonify(success=True)

@app.route('/swap_trees/<int:tree1_id>/<int:tree2_id>', methods=['POST'])
@login_required  # <-- ADD THIS
def swap_trees(tree1_id, tree2_id):
    try:
        tree1 = Tree.query.filter_by(id=tree1_id, user_id=current_user.id).first()  # <-- FIX THIS
        tree2 = Tree.query.filter_by(id=tree2_id, user_id=current_user.id).first()  # <-- FIX THIS
        
        if not tree1 or not tree2:
            return jsonify({'error': 'One or both trees not found'}), 404
        
        if tree1.dome_id != tree2.dome_id:
            return jsonify({'error': 'Trees must be in the same dome'}), 400
        
        # Swap positions
        tree1.row, tree2.row = tree2.row, tree1.row
        tree1.col, tree2.col = tree2.col, tree1.col
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'tree1': {'id': tree1.id, 'row': tree1.row, 'col': tree1.col},
            'tree2': {'id': tree2.id, 'row': tree2.row, 'col': tree2.col}
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Server error: {str(e)}'}), 500

# ============= GRID SETTINGS =============

@app.route('/grid_size', methods=['GET', 'POST'])
def manage_grid():
    if request.method == 'POST':
        data = request.json
        grid = GridSettings.query.first()
        if not grid:
            grid = GridSettings()
            db.session.add(grid)
        grid.rows = data.get('rows', 5)
        grid.cols = data.get('cols', 5)
        db.session.commit()
        return jsonify(success=True)
    
    grid = GridSettings.query.first()
    if not grid:
        grid = GridSettings(rows=5, cols=5)
        db.session.add(grid)
        db.session.commit()
    return jsonify(rows=grid.rows, cols=grid.cols)

@app.route('/validate_position/<int:dome_id>', methods=['POST'])
def validate_position(dome_id):
    data = request.json
    dome = db.session.get(Dome, dome_id)
    other_domes = Dome.query.filter(Dome.id != dome_id).all()
    
    valid = True
    for d in other_domes:
        if d.grid_row == data['grid_row'] and d.grid_col == data['grid_col']:
            valid = False
            break
            
    return jsonify(valid=valid)

# ============= API ROUTES =============

@app.route('/api/trees/<int:dome_id>')
@login_required  # <-- ADD THIS
def get_trees_api(dome_id):
    dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()  # <-- FIX THIS
    if not dome:
        return jsonify({'error': 'Dome not found'}), 404
    
    trees_query = Tree.query.filter_by(dome_id=dome_id, user_id=current_user.id).all()  # <-- FIX THIS
    
    tree_data = []
    for tree in trees_query:
        tree_info = {
            'id': tree.id,
            'name': tree.name,
            'row': tree.row,
            'col': tree.col,
            'dome_id': tree.dome_id
        }
        if hasattr(tree, 'image_url') and tree.image_url:
            tree_info['image_url'] = tree.image_url
        if hasattr(tree, 'info') and tree.info:
            tree_info['info'] = tree.info
        if hasattr(tree, 'life_days') and tree.life_days is not None:
            tree_info['life_days'] = tree.life_days
        tree_data.append(tree_info)
    
    return jsonify({
        'success': True,
        'trees': tree_data,
        'dome': {
            'id': dome.id,
            'name': dome.name,
            'internal_rows': dome.internal_rows,
            'internal_cols': dome.internal_cols
        }
    })

# ============= UTILITY ROUTES =============

@app.route('/domes')
@login_required  # <-- ADD THIS
def get_domes():
    domes = Dome.query.filter_by(user_id=current_user.id).order_by(Dome.grid_row, Dome.grid_col).all()  # <-- FIX THIS
    return jsonify([{
        'id': d.id,
        'name': d.name,
        'grid_row': d.grid_row,
        'grid_col': d.grid_col,
        'internal_rows': d.internal_rows,
        'internal_cols': d.internal_cols
    } for d in domes])

@app.route('/clear_database', methods=['POST'])
def clear_database():
    """Clear all data from the database (for testing/reset purposes)"""
    try:
        Tree.query.delete()
        Dome.query.delete()
        db.session.commit()
        return jsonify(success=True, message="Database cleared successfully")
    except Exception as e:
        db.session.rollback()
        return jsonify(success=False, error=str(e)), 500
@app.route('/swap_trees_by_position/<int:dome_id>', methods=['POST'])
def swap_trees_by_position(dome_id):
    """Swap two trees by their positions"""
    try:
        data = request.json
        tree1_row = data.get('tree1_row')
        tree1_col = data.get('tree1_col')
        tree2_row = data.get('tree2_row')
        tree2_col = data.get('tree2_col')
        
        # Get both trees
        tree1 = db.session.query(Tree).filter(
            Tree.dome_id == dome_id,
            Tree.row == tree1_row,
            Tree.col == tree1_col
        ).first()
        
        tree2 = db.session.query(Tree).filter(
            Tree.dome_id == dome_id,
            Tree.row == tree2_row,
            Tree.col == tree2_col
        ).first()
        
        if not tree1 or not tree2:
            return jsonify({'success': False, 'error': 'One or both trees not found'}), 404
        
        # Swap positions
        tree1.row, tree2.row = tree2.row, tree1.row
        tree1.col, tree2.col = tree2.col, tree1.col
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'tree1': {'id': tree1.id, 'row': tree1.row, 'col': tree1.col},
            'tree2': {'id': tree2.id, 'row': tree2.row, 'col': tree2.col}
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'error': f'Server error: {str(e)}'}), 500
    
@app.route('/debug/images')
def debug_images():
    """Debug route to check image status"""
    try:
        # Check uploads folder
        uploads_path = app.config['UPLOAD_FOLDER']
        if not os.path.exists(uploads_path):
            return jsonify({'error': 'Uploads folder does not exist'})
        
        # List all files in uploads
        files = os.listdir(uploads_path)
        
        # Check database for image URLs
        import sqlite3
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name, image_url FROM tree WHERE image_url IS NOT NULL")
        trees_with_images = cursor.fetchall()
        
        cursor.execute("SELECT id, name, image_url FROM dome WHERE image_url IS NOT NULL")
        domes_with_images = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            'uploads_folder': uploads_path,
            'files_in_uploads': files,
            'trees_with_images': [{'id': t[0], 'name': t[1], 'image_url': t[2]} for t in trees_with_images],
            'domes_with_images': [{'id': d[0], 'name': d[1], 'image_url': d[2]} for d in domes_with_images]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)})
@app.route('/debug/fix_images', methods=['POST'])
def fix_images():
    """Debug route to fix image issues"""
    try:
        # Run the schema fix
        import sqlite3
        conn = sqlite3.connect('db.sqlite3')
        cursor = conn.cursor()
        
        # Ensure image columns exist
        try:
            cursor.execute('ALTER TABLE dome ADD COLUMN image_url VARCHAR(200)')
        except:
            pass
            
        try:
            cursor.execute('ALTER TABLE tree ADD COLUMN image_url VARCHAR(200)')
            cursor.execute('ALTER TABLE tree ADD COLUMN info TEXT')
            cursor.execute('ALTER TABLE tree ADD COLUMN life_days INTEGER DEFAULT 0')
        except:
            pass
        
        conn.commit()
        conn.close()
        
        # Create uploads folder
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        
        return jsonify({'success': True, 'message': 'Image system fixed'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})
if __name__ == '__main__':
    app.run(debug=True)