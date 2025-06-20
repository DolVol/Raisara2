# Enhanced Drag Area API Endpoints for Cross-Dome Copy/Paste Functionality
# Add these endpoints to your app.py file

from flask import jsonify, request
from flask_login import login_required, current_user
from models import db, DragArea, DragAreaTree, Tree, Dome
from datetime import datetime
import json

# ============= ENHANCED DRAG AREA API ENDPOINTS =============

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