from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash, check_password_hash
import secrets
import json
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
    last_login = db.Column(db.DateTime, nullable=True)
    previous_login = db.Column(db.DateTime, nullable=True)
    login_count = db.Column(db.Integer, default=0)    
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
    def update_last_login(self):
        """Update last login timestamp"""
        self.previous_login = self.last_login
        self.last_login = datetime.utcnow()
        self.login_count = (self.login_count or 0) + 1
        
        # Update all user's trees with current reference time
        for tree in self.trees:
            # This will trigger recalculation of life days
            tree.updated_at = datetime.utcnow()
    
    def get_days_since_last_login(self):
        """Get number of days since last login"""
        if not self.last_login:
            return 0
        
        time_diff = datetime.utcnow() - self.last_login
        return time_diff.days    
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

class Farm(db.Model):
    __tablename__ = 'farm'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    grid_row = db.Column(db.Integer, nullable=False)
    grid_col = db.Column(db.Integer, nullable=False)
    image_url = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Farm password protection fields
    password_hash = db.Column(db.String(200), nullable=True)
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)
    
    # Relationships
    domes = db.relationship('Dome', backref='farm', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<Farm {self.name}>'
    
    def get_dome_count(self):
        """Get the number of domes in this farm"""
        return len(self.domes)
    
    def set_password(self, password):
        """Set farm password"""
        if password:
            self.password_hash = generate_password_hash(password)
        else:
            self.password_hash = None
    
    def check_password(self, password):
        """Check farm password"""
        if not self.password_hash:
            return True  # No password set
        return check_password_hash(self.password_hash, password)
    
    def has_password(self):
        """Check if farm has a password set"""
        return bool(self.password_hash)
    
    def generate_reset_token(self):
        """Generate password reset token for farm"""
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
        return self.reset_token
    
    def verify_reset_token(self, token):
        """Verify farm password reset token"""
        if not self.reset_token or not self.reset_token_expires:
            return False
        if self.reset_token != token:
            return False
        if datetime.utcnow() > self.reset_token_expires:
            return False
        return True
    
    def clear_reset_token(self):
        """Clear farm password reset token"""
        self.reset_token = None
        self.reset_token_expires = None

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
    
    # ✅ FIXED: Single trees relationship definition
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

    def get_empty_positions(self):
        """Get list of empty positions in the dome"""
        occupied_positions = set()
        for tree in self.trees:
            occupied_positions.add((tree.internal_row, tree.internal_col))
        
        empty_positions = []
        for row in range(self.internal_rows):
            for col in range(self.internal_cols):
                if (row, col) not in occupied_positions:
                    empty_positions.append({'row': row, 'col': col})
        
        return empty_positions

    def get_occupancy_rate(self):
        """Get occupancy rate as percentage"""
        total_positions = self.internal_rows * self.internal_cols
        occupied_positions = len(self.trees)
        return (occupied_positions / total_positions * 100) if total_positions > 0 else 0

    def can_resize_to(self, new_rows, new_cols):
        """Check if dome can be resized without affecting trees"""
        for tree in self.trees:
            if tree.internal_row >= new_rows or tree.internal_col >= new_cols:
                return False, f"Tree '{tree.name}' at ({tree.internal_row}, {tree.internal_col}) would be outside new bounds"
        return True, "Resize is safe"

    def to_dict(self):
        """Convert dome to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'name': self.name,
            'grid_row': self.grid_row,
            'grid_col': self.grid_col,
            'internal_rows': self.internal_rows,
            'internal_cols': self.internal_cols,
            'image_url': self.image_url,
            'user_id': self.user_id,
            'farm_id': self.farm_id,
            'tree_count': self.get_tree_count(),
            'occupancy_rate': round(self.get_occupancy_rate(), 1),
            'empty_positions': len(self.get_empty_positions()),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class Tree(db.Model):
    __tablename__ = 'tree'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    internal_row = db.Column(db.Integer, default=0)
    internal_col = db.Column(db.Integer, default=0)
    breed = db.Column(db.String(100)) 
    info = db.Column(db.Text, nullable=True)
    paste_metadata = db.Column(db.Text, nullable=True)
    life_days = db.Column(db.Integer, default=0)
    image_url = db.Column(db.String(200), nullable=True)
    dome_id = db.Column(db.Integer, db.ForeignKey('dome.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    planted_date = db.Column(db.DateTime, default=datetime.utcnow)  # When tree was actually planted
    life_day_offset = db.Column(db.Integer, default=0)  # Manual adjustment to life days
    is_paused = db.Column(db.Boolean, default=False)  # Allow pausing life day counting
    paused_at = db.Column(db.DateTime, nullable=True)  # When counting was paused
    total_paused_days = db.Column(db.Integer, default=0)
    # ✅ Plant type and cutting functionality
    plant_type = db.Column(db.String(20), default='mother', nullable=False)  # 'mother' or 'cutting'
    cutting_notes = db.Column(db.Text)  # Notes about cutting process
    mother_plant_id = db.Column(db.Integer, db.ForeignKey('tree.id'), nullable=True)  # For tracking mother-cutting relationships
    # Self-referential relationship for mother-cutting
    mother_plant = db.relationship('Tree', remote_side=[id], backref='direct_cuttings')
    
    def __repr__(self):
        return f'<Tree {self.name}>'
    
    def get_actual_life_days(self, reference_date=None):
        """Calculate actual life days based on planted date and current time"""
        try:
            if reference_date is None:
                reference_date = datetime.utcnow()
            
            if not self.planted_date:
                # Fallback to created_at if planted_date is not set
                planted_date = self.created_at or datetime.utcnow()
            else:
                planted_date = self.planted_date
            
            # Calculate base days since planting
            time_diff = reference_date - planted_date
            base_days = time_diff.days
            
            # Subtract paused days
            paused_days = self.total_paused_days or 0
            
            # Add manual offset
            offset = self.life_day_offset or 0
            
            # Calculate final life days
            actual_life_days = max(0, base_days - paused_days + offset)
            
            return actual_life_days
            
        except Exception as e:
            print(f"❌ Error calculating life days for tree {self.id}: {e}")
            return self.life_days or 0    
    def get_paste_metadata(self):
        """Get parsed paste metadata"""
        if self.paste_metadata:
            try:
                return json.loads(self.paste_metadata)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    
    def set_paste_metadata(self, metadata):
        """Set paste metadata as JSON"""
        if metadata:
            self.paste_metadata = json.dumps(metadata)
        else:
            self.paste_metadata = None    
    def get_life_stage(self, reference_date=None):
        """Get life stage based on actual life days"""
        actual_days = self.get_actual_life_days(reference_date)
        
        if actual_days < 7:
            return "Seedling"
        elif actual_days < 30:
            return "Young"
        elif actual_days < 90:
            return "Mature"
        elif actual_days < 365:
            return "Adult"
        else:
            return "Ancient"
    
    def get_life_stage_color(self, reference_date=None):
        """Get color for life stage"""
        stage = self.get_life_stage(reference_date)
        colors = {
            "Seedling": "#90EE90",  # Light green
            "Young": "#32CD32",     # Lime green
            "Mature": "#228B22",    # Forest green
            "Adult": "#006400",     # Dark green
            "Ancient": "#8B4513"    # Saddle brown
        }
        return colors.get(stage, "#32CD32")
    
    def get_age_category(self, reference_date=None):
        """Get age category for statistics - FIXED: Only one method, accepts reference_date"""
        actual_days = self.get_actual_life_days(reference_date)
        
        if actual_days < 7:
            return "seedling"
        elif actual_days < 30:
            return "young"
        elif actual_days < 90:
            return "mature"
        elif actual_days < 365:
            return "old"
        else:
            return "ancient"    
    
    def get_position_string(self):
        """Get position as a string"""
        return f"({self.internal_row}, {self.internal_col})"
    
    def pause_life_counting(self):
        """Pause life day counting"""
        if not self.is_paused:
            self.is_paused = True
            self.paused_at = datetime.utcnow()
            return True
        return False   
    
    def resume_life_counting(self):
        """Resume life day counting"""
        if self.is_paused and self.paused_at:
            # Add paused time to total
            paused_duration = datetime.utcnow() - self.paused_at
            self.total_paused_days = (self.total_paused_days or 0) + paused_duration.days
            
            self.is_paused = False
            self.paused_at = None
            return True
        return False 
    
    def adjust_life_days(self, adjustment):
        """Manually adjust life days (positive or negative)"""
        self.life_day_offset = (self.life_day_offset or 0) + adjustment
        return self.get_actual_life_days()
    
    def is_position_valid(self, dome):
        """Check if tree position is valid within dome bounds"""
        return (0 <= self.internal_row < dome.internal_rows and 
                0 <= self.internal_col < dome.internal_cols)

    # ✅ REMOVED: Duplicate get_age_category method that didn't accept reference_date
    # The method above handles both cases (with and without reference_date)
    
    def get_drag_areas(self):
        """Get all drag areas this tree belongs to"""
        return [dat.drag_area for dat in self.drag_area_associations]
    
    def is_in_drag_area(self, drag_area_id):
        """Check if tree is in a specific drag area"""
        return any(dat.drag_area_id == drag_area_id for dat in self.drag_area_associations)
    
    def get_regular_areas(self):
        """Get all regular areas this tree belongs to"""
        return self.regular_areas

    def is_in_regular_area(self, regular_area_id):
        """Check if tree is in a specific regular area"""
        return any(area.id == regular_area_id for area in self.regular_areas)
    
    # ✅ Plant type methods
    def is_mother_plant(self):
        """Check if this tree is a mother plant"""
        return self.plant_type == 'mother'

    def is_cutting(self):
        """Check if this tree is a cutting"""
        return self.plant_type == 'cutting'

    def get_mother_tree(self):
        """Get the mother tree if this is a cutting - FIXED to use mother_plant relationship"""
        if self.is_cutting() and self.mother_plant_id:
            return self.mother_plant
        return None

    def get_cutting_trees(self):
        """Get all cutting trees if this is a mother plant - FIXED to use direct_cuttings relationship"""
        if self.is_mother_plant():
            return self.direct_cuttings
        return []

    def get_cutting_count(self):
        """Get number of cuttings from this mother plant"""
        return len(self.get_cutting_trees())

    def get_plant_type_display(self):
        """Get display text for plant type"""
        if self.plant_type == 'mother':
            return f"🌳 Mother Plant ({self.get_cutting_count()} cuttings)"
        elif self.plant_type == 'cutting':
            mother = self.get_mother_tree()
            if mother:
                return f"🌿 Cutting from {mother.name}"
            else:
                return "🌿 Cutting (mother unknown)"
        return "🌱 Unknown Type"
    def is_pasted_tree(self):
        """Check if this tree was created from a paste operation"""
        paste_meta = self.get_paste_metadata()
        return bool(paste_meta.get('paste_timestamp'))
    
    def get_original_tree_id(self):
        """Get the original tree ID this tree was copied from"""
        paste_meta = self.get_paste_metadata()
        return paste_meta.get('original_tree_id')
    
    def was_relationship_preserved(self):
        """Check if plant relationship was preserved during paste"""
        paste_meta = self.get_paste_metadata()
        return paste_meta.get('relationship_preserved', False)
    
    def get_original_mother_id(self):
        """Get the original mother tree ID before paste"""
        paste_meta = self.get_paste_metadata()
        return paste_meta.get('original_mother_id')
    def get_plant_lineage(self):
        """Get the plant lineage information"""
        lineage = {
            'type': self.plant_type,
            'is_mother': self.is_mother_plant(),
            'is_cutting': self.is_cutting(),
            'mother': None,
            'cuttings': [],
            'generation': 0
        }
        
        if self.is_cutting():
            mother = self.get_mother_tree()
            if mother:
                lineage['mother'] = {
                    'id': mother.id,
                    'name': mother.name,
                    'breed': mother.breed
                }
                # If mother is also a cutting, this is generation 2+
                if mother.is_cutting():
                    lineage['generation'] = 2  # Could be calculated recursively
                else:
                    lineage['generation'] = 1
        
        if self.is_mother_plant():
            cuttings = self.get_cutting_trees()
            lineage['cuttings'] = [
                {
                    'id': cutting.id,
                    'name': cutting.name,
                    'breed': cutting.breed,
                    'created_at': cutting.created_at.isoformat() if cutting.created_at else None
                }
                for cutting in cuttings
            ]
        
        return lineage
    
    def to_dict(self, reference_date=None):
        """Convert to dictionary with calculated life days and paste metadata"""
        try:
            actual_life_days = self.get_actual_life_days(reference_date)
            paste_meta = self.get_paste_metadata()
            
            base_dict = {
                'id': self.id,
                'name': self.name,
                'breed': self.breed or '',
                'internal_row': self.internal_row,
                'internal_col': self.internal_col,
                'info': self.info,
                'life_days': actual_life_days,
                'stored_life_days': self.life_days,
                'image_url': self.image_url,
                'dome_id': self.dome_id,
                'user_id': self.user_id,
                'plant_type': self.plant_type,
                'cutting_notes': self.cutting_notes,
                'mother_plant_id': self.mother_plant_id,
                'planted_date': self.planted_date.isoformat() if self.planted_date else None,
                'life_day_offset': self.life_day_offset or 0,
                'is_paused': self.is_paused,
                'total_paused_days': self.total_paused_days or 0,
                'life_stage': self.get_life_stage(reference_date),
                'life_stage_color': self.get_life_stage_color(reference_date),
                'age_category': self.get_age_category(reference_date),
                'position_string': self.get_position_string(),
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None,
                'is_mother': self.is_mother_plant(),
                'is_cutting': self.is_cutting(),
                'has_mother': bool(self.mother_plant_id),
                'cutting_count': self.get_cutting_count() if self.is_mother_plant() else 0,
                
                # ✅ NEW: Paste metadata
                'paste_metadata': paste_meta,
                'is_pasted': self.is_pasted_tree(),
                'original_tree_id': self.get_original_tree_id(),
                'relationship_preserved': self.was_relationship_preserved(),
                'original_mother_id': self.get_original_mother_id()
            }
            
            return base_dict
            
        except Exception as e:
            print(f"❌ Error in Tree.to_dict(): {e}")
            # Return basic dictionary on error (same as your existing error handling)
            return {
                'id': self.id,
                'name': self.name,
                'breed': self.breed or '',
                'internal_row': self.internal_row,
                'internal_col': self.internal_col,
                'info': self.info or '',
                'life_days': self.life_days or 0,
                'image_url': self.image_url,
                'dome_id': self.dome_id,
                'user_id': self.user_id,
                'plant_type': self.plant_type,
                'cutting_notes': self.cutting_notes or '',
                'mother_plant_id': self.mother_plant_id,
                'life_stage': 'Unknown',
                'age_category': 'unknown',
                'position_string': f"({self.internal_row}, {self.internal_col})",
                'created_at': self.created_at.isoformat() if self.created_at else None,
                'updated_at': self.updated_at.isoformat() if self.updated_at else None,
                'is_mother': False,
                'is_cutting': False,
                'has_mother': False,
                'cutting_count': 0,
                'paste_metadata': {},
                'is_pasted': False,
                'original_tree_id': None,
                'relationship_preserved': False,
                'original_mother_id': None
            }
class PlantRelationship(db.Model):
    """Model for tracking mother plant to cutting relationships"""
    __tablename__ = 'plant_relationship'
    
    id = db.Column(db.Integer, primary_key=True)
    mother_tree_id = db.Column(db.Integer, db.ForeignKey('tree.id', ondelete='CASCADE'), nullable=False)
    cutting_tree_id = db.Column(db.Integer, db.ForeignKey('tree.id', ondelete='CASCADE'), nullable=False)
    cutting_date = db.Column(db.DateTime, default=datetime.utcnow)
    notes = db.Column(db.Text, nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    dome_id = db.Column(db.Integer, db.ForeignKey('dome.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # ✅ FIXED: Clean relationships without conflicting backrefs
    mother_tree = db.relationship('Tree', foreign_keys=[mother_tree_id], 
                                 backref=db.backref('mother_cuttings', lazy=True, cascade='all, delete-orphan'))
    cutting_tree = db.relationship('Tree', foreign_keys=[cutting_tree_id], 
                                  backref=db.backref('cutting_mother', uselist=False))
    user = db.relationship('User', foreign_keys=[user_id])
    dome = db.relationship('Dome', foreign_keys=[dome_id])
    
    # Unique constraint - each cutting can only have one mother
    __table_args__ = (
        db.UniqueConstraint('cutting_tree_id', name='unique_cutting_mother'),
    )
    
    def __repr__(self):
        return f'<PlantRelationship mother_id={self.mother_tree_id} cutting_id={self.cutting_tree_id}>'
    
    def get_cutting_age_days(self):
        """Get how many days since the cutting was taken"""
        if self.cutting_date:
            return (datetime.utcnow() - self.cutting_date).days
        return 0
    
    def get_cutting_age_string(self):
        """Get human-readable cutting age"""
        days = self.get_cutting_age_days()
        if days == 0:
            return "Today"
        elif days == 1:
            return "1 day ago"
        elif days < 7:
            return f"{days} days ago"
        elif days < 30:
            weeks = days // 7
            return f"{weeks} week{'s' if weeks > 1 else ''} ago"
        elif days < 365:
            months = days // 30
            return f"{months} month{'s' if months > 1 else ''} ago"
        else:
            years = days // 365
            return f"{years} year{'s' if years > 1 else ''} ago"
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'mother_tree_id': self.mother_tree_id,
            'cutting_tree_id': self.cutting_tree_id,
            'cutting_date': self.cutting_date.isoformat() if self.cutting_date else None,
            'notes': self.notes,
            'user_id': self.user_id,
            'dome_id': self.dome_id,
            'cutting_age_days': self.get_cutting_age_days(),
            'cutting_age_string': self.get_cutting_age_string(),
            'mother_tree_name': self.mother_tree.name if self.mother_tree else None,
            'cutting_tree_name': self.cutting_tree.name if self.cutting_tree else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class GridSettings(db.Model):
    __tablename__ = 'grid_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    rows = db.Column(db.Integer, default=10)
    cols = db.Column(db.Integer, default=10)
    grid_type = db.Column(db.String(20), default='dome')  # 'dome', 'farm', 'farm_X_dome'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def __repr__(self):
        return f'<GridSettings {self.grid_type}: {self.rows}x{self.cols}>'

class DragArea(db.Model):
    __tablename__ = 'drag_area'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(20), nullable=False, default='#007bff')
    dome_id = db.Column(db.Integer, db.ForeignKey('dome.id'), nullable=False)
    min_row = db.Column(db.Integer, nullable=False)
    max_row = db.Column(db.Integer, nullable=False)
    min_col = db.Column(db.Integer, nullable=False)
    max_col = db.Column(db.Integer, nullable=False)
    width = db.Column(db.Integer, nullable=False)
    height = db.Column(db.Integer, nullable=False)
    visible = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # ✅ NEW: Enhanced fields for plant relationships and empty cells support
    relationship_metadata = db.Column(db.Text, nullable=True)  # JSON string for plant relationship data
    cells_data = db.Column(db.Text, nullable=True)  # JSON string for cells data (including empty cells)
    supports_empty_cells = db.Column(db.Boolean, default=False)  # Flag for empty cells support
    total_cells = db.Column(db.Integer, default=0)  # Total number of cells in area
    empty_count = db.Column(db.Integer, default=0)  # Number of empty cells
    area_type = db.Column(db.String(50), default='drag_area')  # Type of area ('drag_area', 'pasted_area', etc.)
    paste_timestamp = db.Column(db.DateTime, nullable=True)  # When area was pasted (if applicable)
    paste_metadata = db.Column(db.Text, nullable=True)  # JSON string for paste operation metadata
    
    # Relationships
    dome = db.relationship('Dome', backref=db.backref('drag_areas', lazy=True, cascade='all, delete-orphan'))
    drag_area_trees = db.relationship('DragAreaTree', backref='drag_area', lazy=True, cascade='all, delete-orphan')
    
    def __repr__(self):
        return f'<DragArea {self.name} ({self.min_row},{self.min_col})-({self.max_row},{self.max_col})>'
    
    @property
    def tree_count(self):
        """Get number of trees in this drag area"""
        return len(self.drag_area_trees)
    
    @property
    def cell_count(self):
        """Get total number of cells in this area"""
        return self.width * self.height
    
    def get_tree_ids(self):
        """Get list of tree IDs in this area"""
        return [dat.tree_id for dat in self.drag_area_trees]
    
    def get_trees(self):
        """Get list of actual tree objects in this area"""
        return [dat.tree for dat in self.drag_area_trees if dat.tree]
    
    def contains_position(self, row, col):
        """Check if a position is within this area"""
        return (self.min_row <= row <= self.max_row and 
                self.min_col <= col <= self.max_col)
    
    def get_relative_position(self, row, col):
        """Get relative position within the area"""
        if self.contains_position(row, col):
            return {
                'relative_row': row - self.min_row,
                'relative_col': col - self.min_col
            }
        return None
    
    # ✅ NEW: Enhanced methods for plant relationships and empty cells
    def get_relationship_metadata(self):
        """Get parsed relationship metadata"""
        if self.relationship_metadata:
            try:
                return json.loads(self.relationship_metadata)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    
    def set_relationship_metadata(self, metadata):
        """Set relationship metadata as JSON"""
        if metadata:
            self.relationship_metadata = json.dumps(metadata)
        else:
            self.relationship_metadata = None
    
    def get_cells_data(self):
        """Get parsed cells data"""
        if self.cells_data:
            try:
                return json.loads(self.cells_data)
            except (json.JSONDecodeError, TypeError):
                return []
        return []
    
    def set_cells_data(self, cells):
        """Set cells data as JSON"""
        if cells:
            self.cells_data = json.dumps(cells)
        else:
            self.cells_data = None
    
    def get_paste_metadata(self):
        """Get parsed paste metadata"""
        if self.paste_metadata:
            try:
                return json.loads(self.paste_metadata)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    
    def set_paste_metadata(self, metadata):
        """Set paste metadata as JSON"""
        if metadata:
            self.paste_metadata = json.dumps(metadata)
        else:
            self.paste_metadata = None
    
    def get_plant_relationship_stats(self):
        """Get plant relationship statistics from metadata"""
        metadata = self.get_relationship_metadata()
        return {
            'mothers': metadata.get('actual_mothers', 0),
            'cuttings': metadata.get('actual_cuttings', 0),
            'independent': metadata.get('actual_independent', 0),
            'preserved_relationships': metadata.get('actual_preserved', 0),
            'broken_relationships': metadata.get('actual_broken', 0),
            'has_relationships': metadata.get('actual_mothers', 0) > 0 or metadata.get('actual_cuttings', 0) > 0
        }
    
    def get_mother_trees(self):
        """Get all mother trees in this area"""
        return [tree for tree in self.get_trees() if tree.is_mother_plant()]
    
    def get_cutting_trees(self):
        """Get all cutting trees in this area"""
        return [tree for tree in self.get_trees() if tree.is_cutting()]
    
    def get_independent_trees(self):
        """Get all independent trees in this area"""
        return [tree for tree in self.get_trees() if not tree.is_mother_plant() and not tree.is_cutting()]
    
    def get_complete_relationships(self):
        """Get cutting trees that have their mother trees in the same area"""
        complete_relationships = []
        mother_ids = set(tree.id for tree in self.get_mother_trees())
        
        for cutting in self.get_cutting_trees():
            if cutting.mother_plant_id and cutting.mother_plant_id in mother_ids:
                complete_relationships.append({
                    'cutting': cutting,
                    'mother': next(tree for tree in self.get_mother_trees() if tree.id == cutting.mother_plant_id)
                })
        
        return complete_relationships
    
    def get_orphaned_cuttings(self):
        """Get cutting trees that don't have their mother trees in the same area"""
        orphaned_cuttings = []
        mother_ids = set(tree.id for tree in self.get_mother_trees())
        
        for cutting in self.get_cutting_trees():
            if cutting.mother_plant_id and cutting.mother_plant_id not in mother_ids:
                orphaned_cuttings.append(cutting)
        
        return orphaned_cuttings
    
    def calculate_actual_empty_count(self):
        """Calculate actual number of empty cells in the area"""
        total_cells = self.cell_count
        occupied_cells = self.tree_count
        return total_cells - occupied_cells
    
    def update_cell_counts(self):
        """Update total_cells and empty_count based on current state"""
        self.total_cells = self.cell_count
        self.empty_count = self.calculate_actual_empty_count()
    
    def is_pasted_area(self):
        """Check if this area was created from a paste operation"""
        return bool(self.paste_timestamp)
    
    def get_paste_age_days(self):
        """Get number of days since this area was pasted"""
        if self.paste_timestamp:
            return (datetime.utcnow() - self.paste_timestamp).days
        return None
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization with enhanced data"""
        base_dict = {
            'id': self.id,
            'name': self.name,
            'color': self.color,
            'dome_id': self.dome_id,
            'minRow': self.min_row,
            'maxRow': self.max_row,
            'minCol': self.min_col,
            'maxCol': self.max_col,
            'width': self.width,
            'height': self.height,
            'visible': self.visible,
            'tree_count': self.tree_count,
            'cell_count': self.cell_count,
            'tree_ids': self.get_tree_ids(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if hasattr(self, 'updated_at') and self.updated_at else None,
            
            # ✅ NEW: Enhanced fields
            'supports_empty_cells': self.supports_empty_cells,
            'total_cells': self.total_cells or self.cell_count,
            'empty_count': self.empty_count or self.calculate_actual_empty_count(),
            'area_type': self.area_type,
            'is_pasted': self.is_pasted_area(),
            'paste_timestamp': self.paste_timestamp.isoformat() if self.paste_timestamp else None,
            'paste_age_days': self.get_paste_age_days(),
            
            # ✅ NEW: Plant relationship data
            'relationship_stats': self.get_plant_relationship_stats(),
            'plant_summary': {
                'mothers': len(self.get_mother_trees()),
                'cuttings': len(self.get_cutting_trees()),
                'independent': len(self.get_independent_trees()),
                'complete_relationships': len(self.get_complete_relationships()),
                'orphaned_cuttings': len(self.get_orphaned_cuttings())
            },
            
            # ✅ NEW: Cells and metadata
            'cells_data': self.get_cells_data(),
            'relationship_metadata': self.get_relationship_metadata(),
            'paste_metadata': self.get_paste_metadata()
        }
        
        return base_dict

class DragAreaTree(db.Model):
    __tablename__ = 'drag_area_tree'
    
    id = db.Column(db.Integer, primary_key=True)
    drag_area_id = db.Column(db.Integer, db.ForeignKey('drag_area.id'), nullable=False)
    tree_id = db.Column(db.Integer, db.ForeignKey('tree.id'), nullable=False)
    relative_row = db.Column(db.Integer, nullable=False)
    relative_col = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    tree = db.relationship('Tree', backref=db.backref('drag_area_associations', lazy=True))
    
    # Unique constraint to prevent duplicate tree-area associations
    __table_args__ = (
        db.UniqueConstraint('drag_area_id', 'tree_id', name='unique_drag_area_tree'),
    )
    
    def __repr__(self):
        return f'<DragAreaTree area_id={self.drag_area_id} tree_id={self.tree_id} pos=({self.relative_row},{self.relative_col})>'
    
    def get_absolute_position(self):
        """Get absolute position of tree in dome"""
        if self.drag_area and self.tree:
            return {
                'row': self.drag_area.min_row + self.relative_row,
                'col': self.drag_area.min_col + self.relative_col
            }
        return None
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        abs_pos = self.get_absolute_position()
        return {
            'id': self.id,
            'drag_area_id': self.drag_area_id,
            'tree_id': self.tree_id,
            'relative_row': self.relative_row,
            'relative_col': self.relative_col,
            'absolute_row': abs_pos['row'] if abs_pos else None,
            'absolute_col': abs_pos['col'] if abs_pos else None,
            'tree_name': self.tree.name if self.tree else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

# Association table for regular areas and trees
regular_area_trees = db.Table('regular_area_trees',
    db.Column('regular_area_id', db.Integer, db.ForeignKey('regular_area.id'), primary_key=True),
    db.Column('tree_id', db.Integer, db.ForeignKey('tree.id'), primary_key=True)
)

class RegularArea(db.Model):
    """Model for regular selection areas (selection box areas)"""
    __tablename__ = 'regular_area'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    color = db.Column(db.String(20), nullable=False, default='#007bff')
    dome_id = db.Column(db.Integer, db.ForeignKey('dome.id'), nullable=False)
    min_row = db.Column(db.Integer, nullable=False)
    max_row = db.Column(db.Integer, nullable=False)
    min_col = db.Column(db.Integer, nullable=False)
    max_col = db.Column(db.Integer, nullable=False)
    visible = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    dome = db.relationship('Dome', backref=db.backref('regular_areas', lazy=True, cascade='all, delete-orphan'))
    cells = db.relationship('RegularAreaCell', backref='regular_area', lazy=True, cascade='all, delete-orphan')
    trees = db.relationship('Tree', secondary=regular_area_trees, lazy='subquery',
                           backref=db.backref('regular_areas', lazy=True))
    
    def __repr__(self):
        return f'<RegularArea {self.name} ({self.min_row},{self.min_col})-({self.max_row},{self.max_col})>'
    
    @property
    def width(self):
        """Get width of the area"""
        return self.max_col - self.min_col + 1
    
    @property
    def height(self):
        """Get height of the area"""
        return self.max_row - self.min_row + 1
    
    @property
    def cell_count(self):
        """Get total number of cells in this area"""
        return len(self.cells)
    
    @property
    def tree_count(self):
        """Get number of trees in this regular area"""
        return len(self.trees)
    
    def contains_position(self, row, col):
        """Check if a position is within this area"""
        return (self.min_row <= row <= self.max_row and 
                self.min_col <= col <= self.max_col)
    
    def get_relative_position(self, row, col):
        """Get relative position within the area"""
        if self.contains_position(row, col):
            return {
                'relative_row': row - self.min_row,
                'relative_col': col - self.min_col
            }
        return None
    
    def get_trees_in_area(self):
        """Get all trees that fall within this area's boundaries"""
        trees_in_area = []
        for tree in self.dome.trees:
            if self.contains_position(tree.internal_row, tree.internal_col):
                trees_in_area.append(tree)
        return trees_in_area
    
    def sync_trees_with_area(self):
        """Sync the trees relationship with actual trees in the area boundaries"""
        current_trees = set(self.trees)
        area_trees = set(self.get_trees_in_area())
        
        # Add trees that are in the area but not in the relationship
        for tree in area_trees - current_trees:
            self.trees.append(tree)
        
        # Remove trees that are in the relationship but not in the area
        for tree in current_trees - area_trees:
            self.trees.remove(tree)
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'name': self.name,
            'color': self.color,
            'dome_id': self.dome_id,
            'minRow': self.min_row,
            'maxRow': self.max_row,
            'minCol': self.min_col,
            'maxCol': self.max_col,
            'width': self.width,
            'height': self.height,
            'visible': self.visible,
            'cell_count': self.cell_count,
            'tree_count': self.tree_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

class RegularAreaCell(db.Model):
    """Model for individual cells within regular areas"""
    __tablename__ = 'regular_area_cell'
    
    id = db.Column(db.Integer, primary_key=True)
    regular_area_id = db.Column(db.Integer, db.ForeignKey('regular_area.id'), nullable=False)
    row = db.Column(db.Integer, nullable=False)
    col = db.Column(db.Integer, nullable=False)
    relative_row = db.Column(db.Integer, nullable=False)
    relative_col = db.Column(db.Integer, nullable=False)
    is_selected = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Unique constraint to prevent duplicate cells in same area
    __table_args__ = (
        db.UniqueConstraint('regular_area_id', 'row', 'col', name='unique_regular_area_cell'),
    )
    
    def __repr__(self):
        return f'<RegularAreaCell area_id={self.regular_area_id} pos=({self.row},{self.col})>'
    
    def get_tree_at_position(self):
        """Get tree at this cell's position"""
        if self.regular_area and self.regular_area.dome:
            return self.regular_area.dome.get_tree_at_position(self.row, self.col)
        return None
    
    def is_occupied(self):
        """Check if this cell has a tree"""
        return self.get_tree_at_position() is not None
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        tree = self.get_tree_at_position()
        return {
            'id': self.id,
            'regular_area_id': self.regular_area_id,
            'row': self.row,
            'col': self.col,
            'relative_row': self.relative_row,
            'relative_col': self.relative_col,
            'is_selected': self.is_selected,
            'is_occupied': self.is_occupied(),
            'tree_id': tree.id if tree else None,
            'tree_name': tree.name if tree else None,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

class TreeBreed(db.Model):
    """Model for managing tree breeds"""
    __tablename__ = 'tree_breed'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=True)  # ✅ ADD THIS
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    farm_id = db.Column(db.Integer, db.ForeignKey('farm.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)  # ✅ ADD THIS
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    user = db.relationship('User', backref=db.backref('tree_breeds', lazy=True, cascade='all, delete-orphan'))
    farm = db.relationship('Farm', backref=db.backref('tree_breeds', lazy=True, cascade='all, delete-orphan'))
    
    def __repr__(self):
        return f'<TreeBreed {self.name}>'
    
    # ✅ ADD THESE METHODS
    def get_tree_count(self):
        """Get number of trees using this breed"""
        if self.farm_id:
            return Tree.query.join(Dome).filter(
                Tree.breed == self.name,
                Tree.user_id == self.user_id,
                Dome.farm_id == self.farm_id
            ).count()
        else:
            return Tree.query.filter_by(breed=self.name, user_id=self.user_id).count()
    
    def get_mother_count(self):
        """Get number of mother plants using this breed"""
        if self.farm_id:
            return Tree.query.join(Dome).filter(
                Tree.breed == self.name,
                Tree.user_id == self.user_id,
                Tree.plant_type == 'mother',
                Dome.farm_id == self.farm_id
            ).count()
        else:
            return Tree.query.filter_by(
                breed=self.name, 
                user_id=self.user_id, 
                plant_type='mother'
            ).count()
    
    def get_cutting_count(self):
        """Get number of cuttings using this breed"""
        if self.farm_id:
            return Tree.query.join(Dome).filter(
                Tree.breed == self.name,
                Tree.user_id == self.user_id,
                Tree.plant_type == 'cutting',
                Dome.farm_id == self.farm_id
            ).count()
        else:
            return Tree.query.filter_by(
                breed=self.name, 
                user_id=self.user_id, 
                plant_type='cutting'
            ).count()
    
    def can_be_deleted(self):
        """Check if breed can be safely deleted"""
        tree_count = self.get_tree_count()
        return tree_count == 0
    
    def to_dict(self):
        """Convert to dictionary for JSON serialization"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'user_id': self.user_id,
            'farm_id': self.farm_id,
            'is_active': self.is_active,
            'tree_count': self.get_tree_count(),
            'mother_count': self.get_mother_count(),
            'cutting_count': self.get_cutting_count(),
            'can_be_deleted': self.can_be_deleted(),
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None
        }

# ✅ Additional utility functions for the models

def get_user_statistics(user_id):
    """Get comprehensive statistics for a user"""
    user = db.session.get(User, user_id)
    if not user:
        return None
    
    stats = {
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'created_at': user.created_at.isoformat() if user.created_at else None
        },
        'farms': {
            'total': len(user.farms),
            'with_password': sum(1 for farm in user.farms if farm.has_password())
        },
        'domes': {
            'total': len(user.domes),
            'total_capacity': sum(dome.internal_rows * dome.internal_cols for dome in user.domes),
            'average_size': round(sum(dome.internal_rows * dome.internal_cols for dome in user.domes) / len(user.domes), 1) if user.domes else 0
        },
        'trees': {
            'total': len(user.trees),
            'mothers': len([tree for tree in user.trees if tree.plant_type == 'mother']),
            'cuttings': len([tree for tree in user.trees if tree.plant_type == 'cutting']),
            'by_age': {
                'seedling': len([tree for tree in user.trees if tree.get_age_category() == 'seedling']),
                'young': len([tree for tree in user.trees if tree.get_age_category() == 'young']),
                'mature': len([tree for tree in user.trees if tree.get_age_category() == 'mature']),
                'old': len([tree for tree in user.trees if tree.get_age_category() == 'old']),
                'ancient': len([tree for tree in user.trees if tree.get_age_category() == 'ancient'])
            }
        },
        'breeds': {
            'total': len(user.tree_breeds),
            'active': len([breed for breed in user.tree_breeds if breed.is_active])
        },
        'plant_relationships': {
            'total': PlantRelationship.query.filter_by(user_id=user_id).count(),
            'recent': PlantRelationship.query.filter_by(user_id=user_id).filter(
                PlantRelationship.cutting_date >= datetime.utcnow() - timedelta(days=30)
            ).count()
        }
    }
    
    return stats

def get_dome_statistics(dome_id, user_id):
    """Get comprehensive statistics for a dome"""
    dome = Dome.query.filter_by(id=dome_id, user_id=user_id).first()
    if not dome:
        return None
    
    trees = dome.trees
    total_capacity = dome.internal_rows * dome.internal_cols
    
    stats = {
        'dome': dome.to_dict(),
        'capacity': {
            'total': total_capacity,
            'occupied': len(trees),
            'available': total_capacity - len(trees),
            'occupancy_rate': round((len(trees) / total_capacity * 100), 1) if total_capacity > 0 else 0
        },
        'trees': {
            'total': len(trees),
            'mothers': len([tree for tree in trees if tree.plant_type == 'mother']),
            'cuttings': len([tree for tree in trees if tree.plant_type == 'cutting']),
            'by_breed': {},
            'by_age': {
                'seedling': len([tree for tree in trees if tree.get_age_category() == 'seedling']),
                'young': len([tree for tree in trees if tree.get_age_category() == 'young']),
                'mature': len([tree for tree in trees if tree.get_age_category() == 'mature']),
                'old': len([tree for tree in trees if tree.get_age_category() == 'old']),
                'ancient': len([tree for tree in trees if tree.get_age_category() == 'ancient'])
            }
        },
        'areas': {
            'drag_areas': len(dome.drag_areas),
            'regular_areas': len(dome.regular_areas)
        },
        'relationships': {
            'total': PlantRelationship.query.filter_by(dome_id=dome_id).count(),
            'recent': PlantRelationship.query.filter_by(dome_id=dome_id).filter(
                PlantRelationship.cutting_date >= datetime.utcnow() - timedelta(days=30)
            ).count()
        }
    }
    
    # Calculate breed distribution
    for tree in trees:
        breed = tree.breed or 'Unknown'
        if breed not in stats['trees']['by_breed']:
            stats['trees']['by_breed'][breed] = 0
        stats['trees']['by_breed'][breed] += 1
    
    return stats

def get_farm_statistics(farm_id, user_id):
    """Get comprehensive statistics for a farm"""
    farm = Farm.query.filter_by(id=farm_id, user_id=user_id).first()
    if not farm:
        return None
    
    # Get all domes in this farm
    domes = Dome.query.filter_by(farm_id=farm_id, user_id=user_id).all()
    
    # Get all trees in this farm
    all_trees = []
    for dome in domes:
        all_trees.extend(dome.trees)
    
    total_capacity = sum(dome.internal_rows * dome.internal_cols for dome in domes)
    
    stats = {
        'farm': farm.to_dict(),
        'domes': {
            'total': len(domes),
            'total_capacity': total_capacity,
            'average_size': round(total_capacity / len(domes), 1) if domes else 0
        },
        'capacity': {
            'total': total_capacity,
            'occupied': len(all_trees),
            'available': total_capacity - len(all_trees),
            'occupancy_rate': round((len(all_trees) / total_capacity * 100), 1) if total_capacity > 0 else 0
        },
        'trees': {
            'total': len(all_trees),
            'mothers': len([tree for tree in all_trees if tree.plant_type == 'mother']),
            'cuttings': len([tree for tree in all_trees if tree.plant_type == 'cutting']),
            'by_breed': {},
            'by_age': {
                'seedling': len([tree for tree in all_trees if tree.get_age_category() == 'seedling']),
                'young': len([tree for tree in all_trees if tree.get_age_category() == 'young']),
                'mature': len([tree for tree in all_trees if tree.get_age_category() == 'mature']),
                'old': len([tree for tree in all_trees if tree.get_age_category() == 'old']),
                'ancient': len([tree for tree in all_trees if tree.get_age_category() == 'ancient'])
            }
        },
        'breeds': {
            'total': TreeBreed.query.filter_by(farm_id=farm_id, user_id=user_id).count(),
            'active': TreeBreed.query.filter_by(farm_id=farm_id, user_id=user_id, is_active=True).count()
        },
        'relationships': {
            'total': PlantRelationship.query.filter(
                PlantRelationship.user_id == user_id,
                PlantRelationship.dome_id.in_([dome.id for dome in domes])
            ).count(),
            'recent': PlantRelationship.query.filter(
                PlantRelationship.user_id == user_id,
                PlantRelationship.dome_id.in_([dome.id for dome in domes]),
                PlantRelationship.cutting_date >= datetime.utcnow() - timedelta(days=30)
            ).count()
        }
    }
    
    # Calculate breed distribution
    for tree in all_trees:
        breed = tree.breed or 'Unknown'
        if breed not in stats['trees']['by_breed']:
            stats['trees']['by_breed'][breed] = 0
        stats['trees']['by_breed'][breed] += 1
    
    return stats

def validate_tree_position(dome_id, row, col, exclude_tree_id=None):
    """Validate if a tree position is valid and available"""
    dome = db.session.get(Dome, dome_id)
    if not dome:
        return False, "Dome not found"
    
    # Check bounds
    if not (0 <= row < dome.internal_rows and 0 <= col < dome.internal_cols):
        return False, f"Position ({row}, {col}) is outside dome bounds (0-{dome.internal_rows-1}, 0-{dome.internal_cols-1})"
    
    # Check if position is occupied
    existing_tree = Tree.query.filter_by(
        dome_id=dome_id,
        internal_row=row,
        internal_col=col
    ).first()
    
    if existing_tree and (not exclude_tree_id or existing_tree.id != exclude_tree_id):
        return False, f"Position ({row}, {col}) is already occupied by tree '{existing_tree.name}'"
    
    return True, "Position is valid and available"

def get_available_positions(dome_id, count=None):
    """Get list of available positions in a dome"""
    dome = db.session.get(Dome, dome_id)
    if not dome:
        return []
    
    occupied_positions = set()
    for tree in dome.trees:
        occupied_positions.add((tree.internal_row, tree.internal_col))
    
    available_positions = []
    for row in range(dome.internal_rows):
        for col in range(dome.internal_cols):
            if (row, col) not in occupied_positions:
                available_positions.append({'row': row, 'col': col})
                if count and len(available_positions) >= count:
                    return available_positions
    
    return available_positions

def cleanup_orphaned_relationships():
    """Clean up orphaned plant relationships where trees no longer exist"""
    orphaned_relationships = db.session.query(PlantRelationship).filter(
        ~PlantRelationship.mother_tree_id.in_(db.session.query(Tree.id)) |
        ~PlantRelationship.cutting_tree_id.in_(db.session.query(Tree.id))
    ).all()
    
    for relationship in orphaned_relationships:
        db.session.delete(relationship)
    
    db.session.commit()
    return len(orphaned_relationships)

class ClipboardData(db.Model):
    """Model for storing clipboard data in backend for cross-grid persistence"""
    __tablename__ = 'clipboard_data'
    
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    clipboard_type = db.Column(db.String(50), nullable=False)  # 'drag_area', 'single_tree', 'selection'
    name = db.Column(db.String(200), nullable=False)
    source_dome_id = db.Column(db.Integer, db.ForeignKey('dome.id'), nullable=True)
    source_farm_id = db.Column(db.Integer, db.ForeignKey('farm.id'), nullable=True)
    
    # Clipboard content as JSON
    clipboard_content = db.Column(db.Text, nullable=False)  # JSON string containing all clipboard data
    
    # Metadata
    width = db.Column(db.Integer, default=1)
    height = db.Column(db.Integer, default=1)
    tree_count = db.Column(db.Integer, default=0)
    has_relationships = db.Column(db.Boolean, default=False)
    has_images = db.Column(db.Boolean, default=False)
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=True)  # Optional expiration
    
    # Status
    is_active = db.Column(db.Boolean, default=True)
    access_count = db.Column(db.Integer, default=0)  # Track how many times it's been accessed
    
    # Relationships
    user = db.relationship('User', backref=db.backref('clipboard_data', lazy=True, cascade='all, delete-orphan'))
    source_dome = db.relationship('Dome', foreign_keys=[source_dome_id])
    source_farm = db.relationship('Farm', foreign_keys=[source_farm_id])
    
    def __repr__(self):
        return f'<ClipboardData {self.clipboard_type}: {self.name} (User: {self.user_id})>'
    
    def get_clipboard_content(self):
        """Get parsed clipboard content"""
        if self.clipboard_content:
            try:
                return json.loads(self.clipboard_content)
            except (json.JSONDecodeError, TypeError):
                return {}
        return {}
    
    def set_clipboard_content(self, content):
        """Set clipboard content as JSON"""
        if content:
            self.clipboard_content = json.dumps(content)
            # Update metadata from content
            self.update_metadata_from_content(content)
        else:
            self.clipboard_content = None
    
    def update_metadata_from_content(self, content):
        """Update metadata fields from clipboard content"""
        try:
            self.width = content.get('width', 1)
            self.height = content.get('height', 1)
            self.tree_count = content.get('tree_count', 0)
            
            # Check for relationships
            summary = content.get('summary', {})
            if summary:
                plant_rels = summary.get('plant_relationships', {})
                self.has_relationships = (
                    plant_rels.get('mother_trees', 0) > 0 or 
                    plant_rels.get('cutting_trees', 0) > 0
                )
                self.has_images = summary.get('has_images', 0) > 0
            else:
                # Fallback: check trees data directly
                trees_data = content.get('trees', []) or content.get('trees_data', [])
                self.has_relationships = any(
                    tree.get('plant_type') in ['mother', 'cutting'] or tree.get('mother_plant_id')
                    for tree in trees_data
                )
                self.has_images = any(
                    tree.get('image_url') and tree.get('image_url').startswith('data:image/')
                    for tree in trees_data
                )
                
        except Exception as e:
            print(f"⚠️ Error updating clipboard metadata: {e}")
    
    def is_expired(self):
        """Check if clipboard data has expired"""
        if self.expires_at:
            return datetime.utcnow() > self.expires_at
        return False
    
    def increment_access_count(self):
        """Increment access count when clipboard is used"""
        self.access_count = (self.access_count or 0) + 1
        self.updated_at = datetime.utcnow()
    
    def get_age_days(self):
        """Get age of clipboard data in days"""
        if self.created_at:
            return (datetime.utcnow() - self.created_at).days
        return 0
    
    def get_source_info(self):
        """Get source information"""
        source_info = {
            'dome_id': self.source_dome_id,
            'dome_name': self.source_dome.name if self.source_dome else None,
            'farm_id': self.source_farm_id,
            'farm_name': self.source_farm.name if self.source_farm else None
        }
        return source_info
    
    def can_be_accessed_by(self, user_id):
        """Check if clipboard can be accessed by a user"""
        return self.user_id == user_id and self.is_active and not self.is_expired()
    
    def to_dict(self, include_content=True):
        """Convert to dictionary for JSON serialization"""
        base_dict = {
            'id': self.id,
            'user_id': self.user_id,
            'clipboard_type': self.clipboard_type,
            'name': self.name,
            'source_dome_id': self.source_dome_id,
            'source_farm_id': self.source_farm_id,
            'width': self.width,
            'height': self.height,
            'tree_count': self.tree_count,
            'has_relationships': self.has_relationships,
            'has_images': self.has_images,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'expires_at': self.expires_at.isoformat() if self.expires_at else None,
            'is_active': self.is_active,
            'access_count': self.access_count,
            'age_days': self.get_age_days(),
            'is_expired': self.is_expired(),
            'source_info': self.get_source_info()
        }
        
        if include_content:
            base_dict['clipboard_content'] = self.get_clipboard_content()
        
        return base_dict
    
    @classmethod
    def get_active_clipboard(cls, user_id):
        """Get the most recent active clipboard for a user"""
        return cls.query.filter_by(
            user_id=user_id,
            is_active=True
        ).filter(
            (cls.expires_at.is_(None)) | (cls.expires_at > datetime.utcnow())
        ).order_by(cls.updated_at.desc()).first()
    
    @classmethod
    def cleanup_expired(cls):
        """Clean up expired clipboard data"""
        expired_count = cls.query.filter(
            cls.expires_at.isnot(None),
            cls.expires_at <= datetime.utcnow()
        ).update({'is_active': False})
        
        db.session.commit()
        return expired_count
    
    @classmethod
    def cleanup_old_inactive(cls, days_old=30):
        """Clean up old inactive clipboard data"""
        cutoff_date = datetime.utcnow() - timedelta(days=days_old)
        old_count = cls.query.filter(
            cls.is_active == False,
            cls.updated_at < cutoff_date
        ).delete()
        
        db.session.commit()
        return old_count