# Comparison: Current vs Enhanced Copy Function

# CURRENT FUNCTION (Limited)
def copy_drag_area_current(dome_id, area_id):
    """Current function - basic copy with minimal data"""
    # Only gets basic tree data
    # No relationship analysis
    # No backend storage
    # Limited metadata
    
    clipboard_data = {
        'id': drag_area.id,
        'name': drag_area.name,
        'type': 'dragArea',
        'trees': area_trees,  # Basic tree data only
        'summary': {
            'total_trees': len(area_trees),
            'breeds': list(set([tree['breed'] for tree in area_trees if tree['breed']])),
            # Missing relationship analysis
        }
    }
    # No database storage - only returns JSON

# ENHANCED FUNCTION (Complete)
def copy_drag_area_enhanced(dome_id, area_id):
    """Enhanced function - complete copy with full data preservation"""
    
    # 1. ENHANCED TREE DATA COLLECTION
    area_trees = []
    tree_ids = []
    
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
                'mother_plant_id': getattr(tree, 'mother_plant_id', None),  # CRITICAL
                'cutting_notes': getattr(tree, 'cutting_notes', ''),
                'created_at': tree.created_at.isoformat() if tree.created_at else None,
                'updated_at': tree.updated_at.isoformat() if tree.updated_at else None
            }
            area_trees.append(tree_data)
            tree_ids.append(tree.id)

    # 2. RELATIONSHIP ANALYSIS (Missing in current)
    mother_trees = [t for t in area_trees if t['plant_type'] == 'mother']
    cutting_trees = [t for t in area_trees if t['plant_type'] == 'cutting']
    
    preserved_relationships = []
    broken_relationships = []
    
    for cutting in cutting_trees:
        if cutting['mother_plant_id']:
            mother_in_area = any(t['id'] == cutting['mother_plant_id'] for t in area_trees)
            if mother_in_area:
                preserved_relationships.append({
                    'mother_id': cutting['mother_plant_id'],
                    'cutting_id': cutting['id']
                })
            else:
                broken_relationships.append({
                    'cutting_id': cutting['id'],
                    'original_mother_id': cutting['mother_plant_id']
                })

    # 3. ENHANCED METADATA
    breeds = list(set([tree['breed'] for tree in area_trees if tree['breed']]))
    
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
        'source_farm_id': dome.farm_id,  # Additional context
        'clipboard_version': '3.0',  # Version tracking
        'clipboard_source': 'backend_enhanced',
        'summary': {
            'total_trees': len(area_trees),
            'breeds': breeds,
            'breed_count': len(breeds),
            'has_images': len([tree for tree in area_trees if tree['image_url']]),
            'plant_relationships': {  # ENHANCED RELATIONSHIP DATA
                'mother_trees': len(mother_trees),
                'cutting_trees': len(cutting_trees),
                'preserved_relationships': len(preserved_relationships),
                'broken_relationships': len(broken_relationships),
                'complete_relationships': preserved_relationships,
                'broken_relationships_detail': broken_relationships
            }
        },
        'relationship_metadata': {  # RELATIONSHIP RESTORATION DATA
            'mother_cutting_pairs': preserved_relationships,
            'broken_relationships': broken_relationships,
            'total_relationships': len(preserved_relationships) + len(broken_relationships)
        }
    }

    # 4. BACKEND STORAGE (Missing in current)
    ClipboardData.query.filter_by(user_id=current_user.id).delete()
    
    clipboard_entry = ClipboardData(
        user_id=current_user.id,
        data_type='drag_area',
        clipboard_data=json.dumps(clipboard_data),
        source_dome_id=dome_id,
        source_area_id=area_id,
        created_at=datetime.utcnow()
    )
    
    db.session.add(clipboard_entry)
    db.session.commit()

    return jsonify({
        'success': True,
        'clipboard_data': clipboard_data,
        'message': f'Drag area "{drag_area.name}" copied to backend clipboard',
        'stats': {  # ENHANCED STATISTICS
            'trees_copied': len(area_trees),
            'breeds_found': len(breeds),
            'relationships_preserved': len(preserved_relationships),
            'relationships_broken': len(broken_relationships)
        }
    })