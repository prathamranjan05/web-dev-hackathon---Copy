# app.py
from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
from app.models import db, User, Vendor, Review, Bookmark
import os
import jinja2
import json # Ensure json module is imported
from math import radians, sin, cos, sqrt, atan2 # For distance calculation
from flask_cors import CORS

# Determine the template path dynamically for better portability
template_path = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
print("TEMPLATE PATH →", template_path)
app = Flask(__name__, template_folder=template_path)
CORS(app,supports_credentials=True)


print("TEMPLATE FOLDER:", app.jinja_loader.searchpath)

# IMPORTANT: Change this to a strong, random key in production
app.secret_key = 'your_super_secret_key_for_flask_session_security'

# DB config
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///street_vendors.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

with app.app_context():
    db.create_all()

# Haversine formula to calculate distance between two lat/lon points
def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371 # Radius of Earth in kilometers

    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)

    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lon1_rad

    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = R * c
    return distance

@app.route('/')
def index():
    # Redirect to the registration page by default
    return redirect(url_for('register'))

@app.route('/register', methods=['GET', 'POST'])
def register():
    """
    Handles initial phone number submission and role selection.
    If phone exists, it logs them in; otherwise, proceeds to Firebase verification.
    """
    if request.method == 'POST':
        phone = request.form['phone']
        role = request.form['role'] # 'user' or 'vendor'

        # Check for existing phone number for the selected role
        existing_entity = None
        if role == 'user':
            existing_entity = User.query.filter_by(phone=phone).first()
        elif role == 'vendor':
            existing_entity = Vendor.query.filter_by(phone=phone).first()
        else:
            flash("Invalid role selected.", "error")
            return render_template('register.html')

        if existing_entity:
            # If entity exists, log them in directly
            if role == 'user':
                session['user_id'] = existing_entity.id
                session['role'] = 'user'
                flash("User logged in successfully!", "success")
                return redirect(url_for('user_dashboard'))
            elif role == 'vendor':
                session['vendor_id'] = existing_entity.id
                session['role'] = 'vendor'
                flash("Vendor logged in successfully!", "success")
                return redirect(url_for('vendor_live_tracking'))
        else:
            # If entity does not exist, proceed to Firebase verification for new registration
            session['phone_to_verify'] = phone
            session['role_to_verify'] = role
            flash("Please verify your phone number to continue with registration.", "info")
            return redirect(url_for('verify_phone_firebase'))
    
    return render_template('register.html')

@app.route('/verify-phone-firebase')
def verify_phone_firebase():
    """
    Renders the page where Firebase Phone Authentication (reCAPTCHA, OTP input) occurs.
    """
    phone = session.get('phone_to_verify')
    role = session.get('role_to_verify')
    if not phone or not role:
        flash("No phone number or role to verify. Please register first.", "error")
        return redirect(url_for('register'))
    
    # Pass the phone number and role to the template so JavaScript can use it
    return render_template('verify_phone_firebase.html', phone=phone, role=role)

@app.route('/firebase-auth-success', methods=['POST'])
def firebase_auth_success():
    """
    Endpoint called by client-side JavaScript after successful Firebase phone authentication.
    It receives the Firebase UID, phone number, and role, then creates or updates the User/Vendor record.
    """
    try:
        data = request.get_json()
        firebase_uid = data.get('uid')
        phone_number = data.get('phoneNumber')
        role = data.get('role')

        if not firebase_uid or not phone_number or not role:
            return jsonify({'status': 'error', 'message': 'Missing Firebase UID, phone number, or role'}), 400

        if role == 'user':
            entity = User.query.filter_by(firebase_uid=firebase_uid).first()
            if not entity:
                entity = User(phone=phone_number, firebase_uid=firebase_uid)
                db.session.add(entity)
                db.session.commit()
                flash("User registration successful! Please set up your profile.", "success")
                session['user_id'] = entity.id
                session['role'] = 'user'
                return jsonify({'status': 'success', 'redirect_url': url_for('user_profile_setup')})
            else:
                # This case should ideally not be hit if the /register route handles existing users correctly
                # But as a fallback, if a Firebase UID already exists, just log them in.
                flash("User login successful!", "success")
                session['user_id'] = entity.id
                session['role'] = 'user'
                return jsonify({'status': 'success', 'redirect_url': url_for('user_dashboard')})
        
        elif role == 'vendor':
            entity = Vendor.query.filter_by(firebase_uid=firebase_uid).first()
            if not entity:
                entity = Vendor(phone=phone_number, firebase_uid=firebase_uid)
                db.session.add(entity)
                db.session.commit()
                flash("Vendor registration successful! Please set up your shop details.", "success")
                session['vendor_id'] = entity.id
                session['role'] = 'vendor'
                return jsonify({'status': 'success', 'redirect_url': url_for('vendor_profile_setup')})
            else:
                # Fallback for existing vendor Firebase UID
                flash("Vendor login successful!", "success")
                session['vendor_id'] = entity.id
                session['role'] = 'vendor'
                return jsonify({'status': 'success', 'redirect_url': url_for('vendor_live_tracking')}) # Redirect vendor to live tracking page

        else:
            return jsonify({'status': 'error', 'message': 'Invalid role provided'}), 400

    except Exception as e:
        print(f"Error in /firebase-auth-success: {e}")
        return jsonify({'status': 'error', 'message': 'An internal server error occurred.'}), 500

@app.route('/user-profile-setup', methods=['GET', 'POST'])
def user_profile_setup():
    """
    Allows users to set their food preferences, search radius, and initial location.
    """
    user_id = session.get('user_id')
    role = session.get('role')
    if not user_id or role != 'user':
        flash("Please log in as a user to set up your profile.", "error")
        return redirect(url_for('register'))

    user = User.query.get(user_id)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for('register'))

    if request.method == 'POST':
        # Get food_preferences from the hidden input created by JS
        food_preferences = request.form.get('food_preferences')
        search_radius = request.form.get('search_radius', type=int)
        latitude = request.form.get('latitude') # Retrieve as string
        longitude = request.form.get('longitude') # Retrieve as string

        # Explicitly convert to float, handling None
        latitude = float(latitude) if latitude is not None else None
        longitude = float(longitude) if longitude is not None else None

        user.food_preferences = food_preferences
        if search_radius:
            user.search_radius = search_radius
        if latitude is not None and longitude is not None:
            user.latitude = latitude
            user.longitude = longitude
        
        db.session.commit()
        flash("Profile updated successfully!", "success")
        return redirect(url_for('user_dashboard'))
    
    return render_template('user_profile_setup.html', user=user)

@app.route('/vendor-profile-setup', methods=['GET', 'POST'])
def vendor_profile_setup():
    """
    Allows vendors to set up their shop details, menu picture, and working hours.
    """
    vendor_id = session.get('vendor_id')
    role = session.get('role')
    if not vendor_id or role != 'vendor':
        flash("Please log in as a vendor to set up your profile.", "error")
        return redirect(url_for('register'))

    vendor = Vendor.query.get(vendor_id)
    if not vendor:
        flash("Vendor not found.", "error")
        return redirect(url_for('register'))

    if request.method == 'POST':
        vendor.shop_name = request.form.get('shop_name')
        # Reverted: No manual newline replacement here. Rely on Jinja's tojson for proper escaping.
        vendor.description = request.form.get('description') 

        # Get food_type from the hidden input created by JS
        vendor.food_type = request.form.get('food_type')
        vendor.working_hours_start = request.form.get('working_hours_start')
        vendor.working_hours_end = request.form.get('working_hours_end')

        # Handle menu picture upload
        # IMPORTANT: Only update menu_picture if a new file is provided.
        # Otherwise, retain the existing one.
        if 'menu_picture' in request.files:
            file = request.files['menu_picture']
            if file and file.filename != '':
                # Read the file as binary data if a new file is uploaded
                vendor.menu_picture = file.read()
            # If file field is present but empty (user didn't select new file),
            # we do nothing, thus preserving the existing vendor.menu_picture.
        
        db.session.commit()
        flash("Shop details updated successfully!", "success")
        return redirect(url_for('vendor_live_tracking')) # Redirect to live tracking after setup
    
    # Convert menu_picture BLOB to base64 for display in HTML when rendering GET request
    menu_picture_base64 = None
    if vendor.menu_picture:
        import base64
        menu_picture_base64 = base64.b64encode(vendor.menu_picture).decode('utf-8')

    return render_template('vendor_profile_setup.html', vendor=vendor, menu_picture_base64=menu_picture_base64)

@app.route('/user-dashboard')
def user_dashboard():
    """
    Displays a list of nearby vendors to the user.
    """
    user_id = session.get('user_id')
    role = session.get('role')
    if not user_id or role != 'user':
        flash("Please log in as a user to view the dashboard.", "error")
        return redirect(url_for('register'))

    user = User.query.get(user_id)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for('register'))

    all_vendors_data = [] # Changed name to avoid confusion with nearby_vendors_data
    # Fetch ALL vendors, regardless of online status
    all_vendors_db = Vendor.query.all() 

    if user.latitude is not None and user.longitude is not None:
        for vendor in all_vendors_db: # Loop through all vendors
            distance = 'N/A' # Default to N/A if vendor has no location
            if vendor.current_latitude is not None and vendor.current_longitude is not None:
                distance = calculate_distance(
                    user.latitude, user.longitude,
                    vendor.current_latitude, vendor.current_longitude
                )
                distance = round(distance, 2) # Round distance to 2 decimal places

            avg_rating = db.session.query(db.func.avg(Review.rating)).filter_by(vendor_id=vendor.id).scalar()
            
            # Reverted: No manual newline replacement here. Rely on Jinja's tojson for proper escaping.
            # description_for_js = vendor.description.replace('\n', '\\n') if vendor.description else None

            all_vendors_data.append({
                'id': vendor.id,
                'shop_name': vendor.shop_name,
                'description': vendor.description, # Pass raw description
                'food_type': vendor.food_type,
                'distance': distance,
                'rating': round(avg_rating, 1) if avg_rating else 'N/A',
                'latitude': vendor.current_latitude,
                'longitude': vendor.current_longitude,
                'working_hours_start': vendor.working_hours_start,
                'working_hours_end': vendor.working_hours_end,
                'is_bookmarked': Bookmark.query.filter_by(user_id=user.id, vendor_id=vendor.id).first() is not None,
                'is_online': vendor.is_online # Pass online status
            })
        
        # Sort by distance for display, but keep all in the list
        all_vendors_data.sort(key=lambda x: x['distance'] if isinstance(x['distance'], (int, float)) else float('inf'))
    else:
        flash("Please enable location services and set your location in your profile for accurate vendor listings and distances.", "warning")
        # If user location is not available, just list all vendors without distance/radius filter
        for vendor in all_vendors_db:
            avg_rating = db.session.query(db.func.avg(Review.rating)).filter_by(vendor_id=vendor.id).scalar()
            
            # Reverted: No manual newline replacement here. Rely on Jinja's tojson for proper escaping.
            # description_for_js = vendor.description.replace('\n', '\\n') if vendor.description else None

            all_vendors_data.append({
                'id': vendor.id,
                'shop_name': vendor.shop_name,
                'description': vendor.description, # Pass raw description
                'food_type': vendor.food_type,
                'distance': 'N/A',
                'rating': round(avg_rating, 1) if avg_rating else 'N/A',
                'latitude': vendor.current_latitude,
                'longitude': vendor.current_longitude,
                'working_hours_start': vendor.working_hours_start,
                'working_hours_end': vendor.working_hours_end,
                'is_bookmarked': Bookmark.query.filter_by(user_id=user.id, vendor_id=vendor.id).first() is not None,
                'is_online': vendor.is_online # Pass online status
            })

    # Pass user_location as a dictionary with lat/lng keys
    user_location_for_js = {'lat': user.latitude, 'lng': user.longitude}
    return render_template('user_dashboard.html', vendors=all_vendors_data, user_location=user_location_for_js)

@app.route('/vendor/<int:vendor_id>')
def vendor_detail(vendor_id):
    """
    Displays detailed information about a specific vendor.
    """
    user_id = session.get('user_id')
    role = session.get('role')
    if not user_id or role != 'user':
        flash("Please log in as a user to view vendor details.", "error")
        return redirect(url_for('register'))

    vendor = Vendor.query.get(vendor_id)
    if not vendor:
        flash("Vendor not found.", "error")
        return redirect(url_for('user_dashboard'))

    reviews = Review.query.filter_by(vendor_id=vendor.id).order_by(Review.timestamp.desc()).all()
    avg_rating = db.session.query(db.func.avg(Review.rating)).filter_by(vendor_id=vendor.id).scalar()
    
    is_bookmarked = False
    if user_id: # Check if a user is logged in to see if it's bookmarked
        is_bookmarked = Bookmark.query.filter_by(user_id=User.id, vendor_id=vendor.id).first() is not None

    # Convert menu_picture BLOB to base64 for display in HTML
    menu_picture_base64 = None
    if vendor.menu_picture:
        import base64
        menu_picture_base64 = base64.b64encode(vendor.menu_picture).decode('utf-8')

    return render_template('vendor_detail.html', 
                           vendor=vendor, 
                           reviews=reviews, 
                           avg_rating=round(avg_rating, 1) if avg_rating else 'N/A',
                           is_bookmarked=is_bookmarked,
                           menu_picture_base64=menu_picture_base64)

@app.route('/api/update-user-location', methods=['POST'])
def api_update_user_location():
    """API endpoint for users to update their location."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'Not logged in'}), 401
    
    data = request.get_json()
    # Corrected: Retrieve and then convert type
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    # Explicitly convert to float, handling None
    latitude = float(latitude) if latitude is not None else None
    longitude = float(longitude) if longitude is not None else None

    if latitude is None or longitude is None:
        return jsonify({'status': 'error', 'message': 'Missing latitude or longitude'}), 400

    user = User.query.get(user_id)
    if user:
        user.latitude = latitude
        user.longitude = longitude
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'User location updated'})
    return jsonify({'status': 'error', 'message': 'User not found'}), 404

@app.route('/api/update-vendor-location', methods=['POST'])
def api_update_vendor_location():
    """API endpoint for vendors to update their real-time location and online status."""
    vendor_id = session.get('vendor_id')
    if not vendor_id:
        return jsonify({'status': 'error', 'message': 'Not logged in as vendor'}), 401
    
    data = request.get_json()
    # Corrected: Retrieve and then convert type
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    is_online_val = data.get('is_online') # Get as string/bool from JSON

    # Explicitly convert to float, handling None
    latitude = float(latitude) if latitude is not None else None
    longitude = float(longitude) if longitude is not None else None
    # Convert to boolean. JSON boolean true/false will be parsed directly, but handle string "true"/"false" if needed.
    is_online = bool(is_online_val) if is_online_val is not None else None # Use is_online_val for clarity


    vendor = Vendor.query.get(vendor_id)
    if vendor:
        if latitude is not None and longitude is not None:
            vendor.current_latitude = latitude
            vendor.current_longitude = longitude
        # Only update is_online if it's explicitly provided in the payload
        if is_online is not None:
            vendor.is_online = is_online
        
        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Vendor location and status updated'})
    return jsonify({'status': 'error', 'message': 'Vendor not found'}), 404

@app.route('/api/bookmark-vendor', methods=['POST'])
def api_bookmark_vendor():
    """API endpoint for users to bookmark/unbookmark a vendor."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'Not logged in as user'}), 401
    
    data = request.get_json()
    vendor_id = data.get('vendor_id', type=int)
    action = data.get('action') # 'add' or 'remove'

    if not vendor_id or action not in ['add', 'remove']:
        return jsonify({'status': 'error', 'message': 'Missing vendor_id or invalid action'}), 400

    if action == 'add':
        existing_bookmark = Bookmark.query.filter_by(user_id=user_id, vendor_id=vendor_id).first()
        if not existing_bookmark:
            bookmark = Bookmark(user_id=user_id, vendor_id=vendor_id)
            db.session.add(bookmark)
            db.session.commit()
            return jsonify({'status': 'success', 'message': 'Vendor bookmarked'})
        return jsonify({'status': 'info', 'message': 'Vendor already bookmarked'})
    elif action == 'remove':
        bookmark = Bookmark.query.filter_by(user_id=user_id, vendor_id=vendor_id).first()
        if bookmark:
            db.session.delete(bookmark)
            db.session.commit()
            return jsonify({'status': 'success', 'message': 'Bookmark removed'})
        return jsonify({'status': 'info', 'message': 'Bookmark not found'})

@app.route('/api/submit-review', methods=['POST'])
def api_submit_review():
    """API endpoint for users to submit a review for a vendor."""
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'Not logged in as user'}), 401
    
    data = request.get_json()
    vendor_id = data.get('vendor_id', type=int)
    rating = data.get('rating', type=int)
    comment = data.get('comment')

    if not vendor_id or rating is None or not (1 <= rating <= 5):
        return jsonify({'status': 'error', 'message': 'Missing vendor_id or invalid rating (1-5)'}), 400

    # Optional: Prevent multiple reviews from the same user for the same vendor
    # existing_review = Review.query.filter_by(user_id=user_id, vendor_id=vendor_id).first()
    # if existing_review:
    #     return jsonify({'status': 'error', 'message': 'You have already reviewed this vendor.'}), 409

    review = Review(user_id=user_id, vendor_id=vendor_id, rating=rating, comment=comment)
    db.session.add(review)
    db.session.commit()
    return jsonify({'status': 'success', 'message': 'Review submitted successfully'})

@app.route('/vendor-live-tracking')
def vendor_live_tracking():
    """
    Page for vendors to enable/disable live location tracking.
    """
    vendor_id = session.get('vendor_id')
    role = session.get('role')
    if not vendor_id or role != 'vendor':
        flash("Please log in as a vendor to manage live tracking.", "error")
        return redirect(url_for('register'))
    
    vendor = Vendor.query.get(vendor_id)
    if not vendor:
        flash("Vendor not found.", "error")
        return redirect(url_for('register'))

    return render_template('vendor_live_tracking.html', vendor=vendor)


@app.route('/home')
def home():
    """
    Redirects based on user role or asks to register/login.
    """
    if 'user_id' in session and session.get('role') == 'user':
        return redirect(url_for('user_dashboard'))
    elif 'vendor_id' in session and session.get('role') == 'vendor':
        return redirect(url_for('vendor_live_tracking'))
    else:
        flash("Please register or log in.", "info")
        return redirect(url_for('register'))

@app.route('/logout')
def logout():
    """
    Logs the user/vendor out by clearing session.
    """
    session.pop('user_id', None)
    session.pop('vendor_id', None)
    session.pop('role', None)
    session.pop('phone_to_verify', None)
    session.pop('role_to_verify', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('register'))

@app.route('/test/')
def test():
    # A simple test route to render the register page
    return render_template('register.html')

if __name__ == '__main__':
    # Ensure debug is False in production
    app.run(debug=True)
