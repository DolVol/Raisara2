# Add these routes to app.py before the if __name__ == '__main__': section

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

        # Get all trees in this area with full data including relationships
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
                    'mother_plant_id': getattr(tree, 'mother_plant_id', None),
                    'cutting_notes': getattr(tree, 'cutting_notes', ''),
                    'created_at': tree.created_at.isoformat() if tree.created_at else None,
                    'updated_at': tree.updated_at.isoformat() if tree.updated_at else None
                }
                area_trees.append(tree_data)
                tree_ids.append(tree.id)

        print(f"📦 Collected {len(area_trees)} trees from drag area")

        # Analyze relationships within the copied trees
        mother_trees = [t for t in area_trees if t['plant_type'] == 'mother']
        cutting_trees = [t for t in area_trees if t['plant_type'] == 'cutting']
        
        # Find relationships that will be preserved (both mother and cutting in the area)
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
            data_type='drag_area',
            clipboard_data=json.dumps(clipboard_data),
            source_dome_id=dome_id,
            source_area_id=area_id,
            created_at=datetime.utcnow()
        )
        
        db.session.add(clipboard_entry)
        db.session.commit()

        print(f"✅ Drag area '{clipboard_data['name']}' saved to backend clipboard")
        print(f"   📏 Area size: {clipboard_data['width']}x{clipboard_data['height']}")
        print(f"   🌳 Trees: {len(area_trees)}")
        print(f"   🧬 Breeds: {len(breeds)} ({', '.join(breeds) if breeds else 'None'})")
        print(f"   🔗 Relationships: {len(preserved_relationships)} preserved, {len(broken_relationships)} broken")

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
    """Paste a drag area from backend clipboard storage"""
    try:
        print(f"📋 Backend paste: Pasting to dome {dome_id}")
        
        # Verify dome ownership
        dome = Dome.query.filter_by(id=dome_id, user_id=current_user.id).first()
        if not dome:
            return jsonify({'success': False, 'error': 'Dome not found or access denied'}), 404

        # Get clipboard data from backend
        clipboard_entry = ClipboardData.query.filter_by(
            user_id=current_user.id,
            data_type='drag_area'
        ).order_by(ClipboardData.created_at.desc()).first()
        
        if not clipboard_entry:
            return jsonify({'success': False, 'error': 'No clipboard data found'}), 400

        # Parse clipboard data
        try:
            clipboard_data = json.loads(clipboard_entry.clipboard_data)
        except json.JSONDecodeError:
            return jsonify({'success': False, 'error': 'Invalid clipboard data format'}), 400

        # Get paste parameters
        data = request.get_json()
        paste_row = data.get('paste_row', 0)
        paste_col = data.get('paste_col', 0)
        new_name = data.get('name', f"{clipboard_data.get('name', 'Pasted Area')} Copy")
        create_trees = data.get('create_trees', True)

        print(f"📋 Pasting '{new_name}' at ({paste_row}, {paste_col})")

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

            # Second pass: Restore relationships
            relationships_restored = 0
            relationships_broken = 0
            
            for tree_data in trees_data:
                if tree_data.get('plant_type') == 'cutting' and tree_data.get('mother_plant_id'):
                    old_mother_id = tree_data['mother_plant_id']
                    old_cutting_id = tree_data['id']
                    
                    # Check if both trees were created
                    if old_mother_id in old_to_new_tree_mapping and old_cutting_id in old_to_new_tree_mapping:
                        new_mother_id = old_to_new_tree_mapping[old_mother_id]
                        new_cutting_id = old_to_new_tree_mapping[old_cutting_id]
                        
                        # Update the cutting tree's mother relationship
                        cutting_tree = Tree.query.get(new_cutting_id)
                        if cutting_tree:
                            cutting_tree.mother_plant_id = new_mother_id
                            relationships_restored += 1
                            print(f"🔗 Restored relationship: Tree {new_cutting_id} -> Mother {new_mother_id}")
                    else:
                        relationships_broken += 1
                        print(f"💔 Broken relationship: Could not restore mother-cutting link for '{tree_data['name']}'")

        db.session.commit()

        print(f"✅ Paste completed successfully")
        print(f"   📏 Area: {new_area.name} ({width}x{height})")
        print(f"   🌳 Trees created: {len(new_trees)}")
        print(f"   🔗 Relationships restored: {relationships_restored}")
        print(f"   💔 Relationships broken: {relationships_broken}")

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
                'relationships_restored': relationships_restored,
                'relationships_broken': relationships_broken,
                'source_dome': clipboard_data.get('source_dome_name', 'Unknown')
            }
        })

    except Exception as e:
        db.session.rollback()
        print(f"❌ Error in paste_drag_area_from_backend: {str(e)}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/get_clipboard_status', methods=['GET'])
@login_required
def get_clipboard_status():
    """Get current clipboard status from backend"""
    try:
        clipboard_entry = ClipboardData.query.filter_by(
            user_id=current_user.id,
            data_type='drag_area'
        ).order_by(ClipboardData.created_at.desc()).first()
        
        if not clipboard_entry:
            return jsonify({
                'success': True,
                'has_clipboard': False,
                'message': 'No clipboard data available'
            })

        # Parse clipboard data for summary
        try:
            clipboard_data = json.loads(clipboard_entry.clipboard_data)
            
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