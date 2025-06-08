from flask_sqlalchemy import SQLAlchemy
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
    
    # Relationships
    farms = db.relationship('Farm', backref='owner', lazy=True, cascade='all, delete-orphan')
    domes = db.relationship('Dome', backref='owner', lazy=True, cascade='all, delete-orphan')
    trees = db.relationship('Tree', backref='owner', lazy=True, cascade='all, delete-orphan')
    grid_settings = db.relationship('GridSettings', backref='user', lazy=True, cascade='all, delete-orphan')
    
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
    
    def __repr__(self):
        return f'<User {self.username}>'

class GridSettings(db.Model):
    __tablename__ = 'grid_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    rows = db.Column(db.Integer, default=5)
    cols = db.Column(db.Integer, default=5)
    grid_type = db.Column(db.String(20), default='dome')  # 'farm' or 'dome'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)  # Per-user settings
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<GridSettings {self.grid_type} {self.rows}x{self.cols}>'

class Farm(db.Model):
    __tablename__ = 'farm'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    grid_row = db.Column(db.Integer, nullable=False)  # Farm's position on main farm grid
    grid_col = db.Column(db.Integer, nullable=False)  # Farm's position on main farm grid
    image_url = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    # ✅ NEW: Dome grid size columns (for the grid inside this farm that contains domes)
    dome_grid_rows = db.Column(db.Integer, default=5)  # How many rows in this farm's dome grid
    dome_grid_cols = db.Column(db.Integer, default=5)  # How many cols in this farm's dome grid
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    domes = db.relationship('Dome', backref='farm', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Farm {self.name}>'
    
    def get_dome_count(self):
        """Get the number of domes in this farm"""
        return len(self.domes)
    
    def get_dome_grid_size(self):
        """Get the dome grid size for this farm"""
        return {
            'rows': self.dome_grid_rows or 5,
            'cols': self.dome_grid_cols or 5
        }
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
    farm_id = db.Column(db.Integer, db.ForeignKey('farm.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    trees = db.relationship('Tree', backref='dome', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Dome {self.name}>'
    
    def get_tree_count(self):
        """Get the number of trees in this dome"""
        return len(self.trees)
    
    def get_tree_at_position(self, row, col):
        """Get tree at specific position"""
        for tree in self.trees:
            if tree.internal_row == row and tree.internal_col == col:
                return tree
        return None

class Tree(db.Model):
    __tablename__ = 'tree'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    
    # Use internal_row and internal_col for tree positions within domes
    internal_row = db.Column(db.Integer, default=0)
    internal_col = db.Column(db.Integer, default=0)
    
    info = db.Column(db.Text, nullable=True)
    life_days = db.Column(db.Integer, default=0)
    image_url = db.Column(db.String(200), nullable=True)
    dome_id = db.Column(db.Integer, db.ForeignKey('dome.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<Tree {self.name}>'
    
    def get_life_stage(self):
        """Get the life stage of the tree based on life_days"""
        if self.life_days < 30:
            return "Young"
        elif self.life_days < 90:
            return "Mature"
        else:
            return "Old"
    
    def get_life_stage_color(self):
        """Get color for the life stage"""
        stage = self.get_life_stage()
        if stage == "Young":
            return "#4CAF50"  # Green
        elif stage == "Mature":
            return "#FF9800"  # Orange
        else:
            return "#F44336"  # Red
    
    def get_position_string(self):
        """Get position as a string"""
        return f"({self.internal_row}, {self.internal_col})"