from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
from datetime import datetime, timedelta
import secrets

db = SQLAlchemy()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Reset token fields
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        print(f"Password set for user, hash: {self.password_hash[:20]}...")
    
    def check_password(self, password):
        try:
            result = check_password_hash(self.password_hash, password)
            print(f"Password check result: {result}")
            return result
        except Exception as e:
            print(f"Password check error: {e}")
            return False
    
    def generate_reset_token(self):
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        return self.reset_token

    def verify_reset_token(self, token):
        if not self.reset_token or not self.reset_token_expires:
            return False
        if datetime.utcnow() > self.reset_token_expires:
            return False
        return self.reset_token == token

    def clear_reset_token(self):
        self.reset_token = None
        self.reset_token_expires = None
        
    def get_database_name(self):
        return f"user_{self.id}_trees.db"

class GridSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    rows = db.Column(db.Integer, default=5)
    cols = db.Column(db.Integer, default=5)

class Dome(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    grid_row = db.Column(db.Integer, default=0)
    grid_col = db.Column(db.Integer, default=0)
    internal_rows = db.Column(db.Integer, default=10)
    internal_cols = db.Column(db.Integer, default=10)
    trees = db.relationship('Tree', backref='dome', cascade='all, delete-orphan')
    
    # ✅ ADD THIS LINE - Image URL for dome
    image_url = db.Column(db.String(200), nullable=True)
    
    # Deprecated fields (remove after migration)
    x = db.Column(db.Integer, default=0)
    y = db.Column(db.Integer, default=0)
    row = db.Column(db.Integer, default=0)
    col = db.Column(db.Integer, default=0)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref='domes')

class Row(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    dome_id = db.Column(db.Integer, db.ForeignKey('dome.id'))

class Tree(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    row = db.Column(db.Integer, default=0)
    col = db.Column(db.Integer, default=0)
    info = db.Column(db.Text)
    life_days = db.Column(db.Integer, default=0)
    
    # ✅ ADD THIS LINE - Image URL for tree
    image_url = db.Column(db.String(200), nullable=True)
    
    # Foreign keys
    dome_id = db.Column(db.Integer, db.ForeignKey('dome.id'))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', backref='trees')