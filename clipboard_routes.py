# ============= BACKEND CLIPBOARD MANAGEMENT ROUTES =============

@app.route('/api/clipboard/save', methods=['POST'])
@login_required
def save_clipboard_to_backend():
    """Save clipboard data to backend for cross-grid persistence"""
    try:
        data = request.get_json()
        
        clipboard_type = data.get('clipboard_type', 'drag_area')
        name = data.get('name', 'Unnamed Clipboard')
        source_dome_id = data.get('source_dome_id')
        source_farm_id = data.get('source_farm_id')
        clipboard_content = data.get('clipboard_content', {})
        expires_in_hours = data.get('expires_in_hours')  # Optional expiration
        
        if not clipboard_content:
            return jsonify({'success': False, 'error': 'No clipboard content provided'}), 400
        
        # Verify source dome ownership if provided
        if source_dome_id:
            dome = Dome.query.filter_by(id=source_dome_id, user_id=current_user.id).first()
            if not dome:
                return jsonify({'success': False, 'error': 'Source dome not found or access denied'}), 404
            source_farm_id = dome.farm_id  # Auto-set farm_id from dome
        
        # Verify source farm ownership if provided
        if source_farm_id:
            farm = Farm.query.filter_by(id=source_farm_id, user_id=current_user.id).first()
            if not farm:
                return jsonify({'success': False, 'error': 'Source farm not found or access denied'}), 404
        
        # Deactivate any existing active clipboard for this user
        ClipboardData.query.filter_by(user_id=current_user.id, is_active=True).update({'is_active': False})
        
        # Calculate expiration if specified
        expires_at = None
        if expires_in_hours:
            expires_at = datetime.utcnow() + timedelta(hours=expires_in_hours)
        
        # Create new clipboard entry
        clipboard_data = ClipboardData(
            user_id=current_user.id,
            clipboard_type=clipboard_type,
            name=name,
            source_dome_id=source_dome_id,
            source_farm_id=source_farm_id,
            expires_at=expires_at,
            is_active=True
        )
        
        # Set clipboard content (this will also update metadata)
        clipboard_data.set_clipboard_content(clipboard_content)
        
        db.session.add(clipboard_data)
        db.session.commit()
        
        print(f"✅ Saved clipboard to backend: {clipboard_data.name} (ID: {clipboard_data.id}) for user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Clipboard saved to backend successfully',
            'clipboard_id': clipboard_data.id,
            'clipboard_data': clipboard_data.to_dict(include_content=False)
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error saving clipboard to backend: {str(e)}")
        import traceback
        print(f"❌ Traceback: {traceback.format_exc()}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/clipboard/load', methods=['GET'])
@login_required
def load_clipboard_from_backend():
    """Load the most recent active clipboard data from backend"""
    try:
        # Get the most recent active clipboard for this user
        clipboard_data = ClipboardData.get_active_clipboard(current_user.id)
        
        if not clipboard_data:
            return jsonify({
                'success': False,
                'error': 'No active clipboard found',
                'has_clipboard': False
            })
        
        # Increment access count
        clipboard_data.increment_access_count()
        db.session.commit()
        
        print(f"✅ Loaded clipboard from backend: {clipboard_data.name} (ID: {clipboard_data.id}) for user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': 'Clipboard loaded from backend successfully',
            'has_clipboard': True,
            'clipboard_data': clipboard_data.to_dict(include_content=True)
        })
        
    except Exception as e:
        print(f"❌ Error loading clipboard from backend: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/clipboard/status', methods=['GET'])
@login_required
def get_clipboard_status():
    """Get clipboard status and metadata without full content"""
    try:
        clipboard_data = ClipboardData.get_active_clipboard(current_user.id)
        
        if not clipboard_data:
            return jsonify({
                'success': True,
                'has_clipboard': False,
                'clipboard_data': None
            })
        
        return jsonify({
            'success': True,
            'has_clipboard': True,
            'clipboard_data': clipboard_data.to_dict(include_content=False)
        })
        
    except Exception as e:
        print(f"❌ Error getting clipboard status: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/clipboard/clear', methods=['POST'])
@login_required
def clear_clipboard_backend():
    """Clear/deactivate current clipboard data"""
    try:
        # Deactivate all active clipboards for this user
        updated_count = ClipboardData.query.filter_by(
            user_id=current_user.id, 
            is_active=True
        ).update({'is_active': False})
        
        db.session.commit()
        
        print(f"✅ Cleared {updated_count} clipboard entries for user {current_user.id}")
        
        return jsonify({
            'success': True,
            'message': f'Cleared {updated_count} clipboard entries',
            'cleared_count': updated_count
        })
        
    except Exception as e:
        db.session.rollback()
        print(f"❌ Error clearing clipboard: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500