# Missing Authentication Routes to add to app.py

# Add these routes at the end of app.py

@app.route('/api/auth/status')
def auth_status():
    """Check authentication status"""
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

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    """Handle forgot password requests"""
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            email = data.get('email', '').strip()
            
            if not email:
                return jsonify({'success': False, 'error': 'Email is required'}), 400
            
            # Find user by email
            user = User.query.filter_by(email=email).first()
            
            if user:
                try:
                    # Generate reset token
                    token = user.generate_reset_token()
                    db.session.commit()
                    
                    # Send reset email
                    send_reset_email(email, token, user.username)
                    print(f"Password reset request for: {email}")
                    
                    return jsonify({
                        'success': True, 
                        'message': 'Password reset email sent. Please check your inbox.'
                    })
                    
                except Exception as email_error:
                    print(f"❌ Error sending reset email: {email_error}")
                    db.session.rollback()
                    
                    # If email fails, show the reset link in console
                    reset_url = f"{request.url_root}reset_password?token={token}"
                    print(f"Password reset requested for: {email} ({user.username})")
                    print(f"Reset URL: {reset_url}")
                    
                    return jsonify({
                        'success': True, 
                        'message': 'Password reset email sent. Please check your inbox.'
                    })
            else:
                # Don't reveal if email exists or not for security
                return jsonify({
                    'success': True, 
                    'message': 'If that email exists, a reset link has been sent.'
                })
                
        except Exception as e:
            print(f"❌ Forgot password error: {e}")
            return jsonify({'success': False, 'error': 'Password reset failed'}), 500
    
    # GET request - show the forgot password form
    return render_template('auth/forgot_password.html')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    """Handle password reset with token"""
    token = request.args.get('token') or request.form.get('token')
    
    if request.method == 'POST':
        try:
            data = request.get_json() if request.is_json else request.form
            
            token = data.get('token')
            new_password = data.get('password', '')
            confirm_password = data.get('confirm_password', '')
            
            if not token or not new_password:
                return jsonify({'success': False, 'error': 'Token and password are required'}), 400
            
            if len(new_password) < 6:
                return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
            
            if new_password != confirm_password:
                return jsonify({'success': False, 'error': 'Passwords do not match'}), 400
            
            # Find user with valid token
            user = User.query.filter_by(reset_token=token).first()
            
            if not user or not user.verify_reset_token(token):
                return jsonify({'success': False, 'error': 'Invalid or expired reset token'}), 400
            
            # Update password
            user.set_password(new_password)
            user.clear_reset_token()
            db.session.commit()
            
            print(f"Password reset successful for: {user.email}")
            
            return jsonify({
                'success': True, 
                'message': 'Password reset successful. You can now log in with your new password.'
            })
            
        except Exception as e:
            print(f"❌ Reset password error: {e}")
            db.session.rollback()
            return jsonify({'success': False, 'error': 'Password reset failed'}), 500
    
    # GET request - show the reset password form
    return render_template('auth/reset_password.html', token=token)

@app.route('/')
def index():
    """Home page - redirect to farms if logged in, otherwise to login"""
    if current_user.is_authenticated:
        return redirect(url_for('farms'))
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
    print("🚀 Starting Flask server...")
    print("📍 Server will be available at: http://127.0.0.1:5000")
    print("🌐 Grid 1: http://127.0.0.1:5000/grid/1")
    print("🌐 Grid 2: http://127.0.0.1:5000/grid/2")