from flask import Flask, render_template, redirect, url_for, request, flash, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import json
import datetime
import requests
import firebase_admin
from firebase_admin import credentials, firestore

# -----------------------
# App & Firebase Config
# -----------------------
app = Flask(__name__)
app.secret_key = "supersecretkey"

# Initialize Firebase
cred = credentials.Certificate("firebase-key.json")
firebase_admin.initialize_app(cred)
db = firestore.client()

# Upload folder configuration
UPLOAD_FOLDER = "uploads"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# USDA API Configuration – replace with your actual key
USDA_API_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
USDA_API_KEY = "rH6W7FJaafmZnZ3UOIrmro1lop2tx5UfMpwmGqdY"

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_nutritional_info(search_query):
    params = {
        "query": search_query,
        "pageSize": 1,
        "api_key": USDA_API_KEY
    }
    response = requests.get(USDA_API_URL, params=params)
    if response.status_code == 200:
        data = response.json()
        if 'foods' in data and len(data['foods']) > 0:
            food_item = data['foods'][0]
            nutrients = []
            for nutrient in food_item.get('foodNutrients', []):
                nutrients.append({
                    "name": nutrient.get("nutrientName"),
                    "value": nutrient.get("value"),
                    "unit": nutrient.get("unitName")
                })
            return nutrients
    return None

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# -----------------------
# Firebase Authentication Routes ======================================================================================
# -----------------------
@app.route('/')
def home():
    return redirect(url_for('login'))
#========================================================================================================================    

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        # Admin Login Check
        if email == "admin@gmail.com" and password == "admin123":
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        # User Login Check in Firebase
        users_ref = db.collection('users').where('email', '==', email).stream()
        for user in users_ref:
            user_data = user.to_dict()
            if check_password_hash(user_data['password'], password):
                session['user'] = user.id
                session['email'] = user_data['email']
                return redirect(url_for('user_dashboard'))
        flash('Invalid credentials. Please try again.', 'danger')
        return redirect(url_for('login'))
    return render_template('login.html')
#========================================================================================================================
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']
        if password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return redirect(url_for('register'))
        hashed_password = generate_password_hash(password)
        db.collection('users').add({'email': email, 'password': hashed_password})
        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')
#========================================================================================================================
@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']
        new_password = request.form['password']
        confirm_password = request.form['confirm_password']

        if new_password != confirm_password:
            flash('Passwords do not match!', 'danger')
            return redirect(url_for('forgot_password'))

        # Hash the new password
        hashed_password = generate_password_hash(new_password)

        # Query Firestore to check if the email exists
        users_ref = db.collection('users').where('email', '==', email).stream()
        user_list = [user for user in users_ref]

        if not user_list:
            flash('This email is not registered. Please check and try again.', 'danger')
            return redirect(url_for('forgot_password'))

        # If the email is found, update the password
        for user in user_list:
            db.collection('users').document(user.id).update({'password': hashed_password})

        flash('Password updated successfully! You can now log in with your new password.', 'success')
        return redirect(url_for('login'))

    return render_template('forgotpassword.html')
#========================================================================================================================
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'admin' not in session:
        flash('Unauthorized Access!', 'danger')
        return redirect(url_for('login'))
    current_hour = datetime.datetime.now().hour
    if current_hour < 12:
        greeting = "Good Morning"
    elif current_hour < 17:
        greeting = "Good Afternoon"
    elif current_hour < 21:
        greeting = "Good Evening"
    else:
        greeting = "Good Night"
    return render_template('admin_dashboard.html', greeting=greeting)
#========================================================================================================================
import datetime

@app.route('/user_dashboard')
def user_dashboard():
    if 'user' not in session:
        flash('You must be logged in to view this page.', 'danger')
        return redirect(url_for('login'))
    email = session.get('email')
    username = "User"
    users_ref = db.collection('users').where('email', '==', email).stream()
    for user in users_ref:
        username = user.to_dict().get('email', 'User')
    # Dynamic greeting based on current time
    current_hour = datetime.datetime.now().hour
    if current_hour < 12:
        greeting = "Good Morning"
    elif current_hour < 17:
        greeting = "Good Afternoon"
    elif current_hour < 21:
        greeting = "Good Evening"
    else:
        greeting = "Good Night"
    return render_template('user_dashboard.html', username=username, greeting=greeting)


#========================================================================================================================
@app.route('/personal-details', methods=['GET'])
def personal_details():
    if 'user' not in session:
        flash('You must be logged in to view this page.', 'danger')
        return redirect(url_for('login'))
    user_ref = db.collection('users').document(session['user'])
    user_data = user_ref.get()
    user = user_data.to_dict() if user_data.exists else {}
    return render_template('personal_details.html', user=user)
#==========================================================================================================================
@app.route('/history', methods=['GET'])
def history():
    if 'user' not in session:
        flash('You must be logged in to view history.', 'danger')
        return redirect(url_for('login'))
    
    # Get filter parameters from query string
    date_filter = request.args.get('date')  # Expected format: YYYY-MM-DD
    food_filter = request.args.get('food')  # Substring to search for in food_name
    
    history_ref = db.collection('history')
    
    # If a date filter is provided, add a where clause
    if date_filter:
        history_ref = history_ref.where('date', '==', date_filter)
    
    # Order the results by timestamp descending
    docs = history_ref.order_by('timestamp', direction=firestore.Query.DESCENDING).stream()
    
    # Build the list and if a food filter is provided, filter the items in Python
    history_items = []
    for doc in docs:
        item = doc.to_dict()
        if food_filter:
            if food_filter.lower() not in item.get('food_name', '').lower():
                continue
        history_items.append(item)
    
    return render_template('history.html', history=history_items)


#==========================================================================================================================
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# -----------------------
# Nutritional Info & Image Upload Feature=====================================================================================
# -----------------------
@app.route('/upload_food', methods=['GET', 'POST'])
def upload_food():
    if 'user' not in session:
        flash('You must be logged in to use this feature.', 'danger')
        return redirect(url_for('login'))
    result = None
    image_path = None
    if request.method == 'POST':
        # Validate file upload
        if "image" not in request.files:
            flash("No file uploaded", "danger")
            return redirect(request.url)
        file = request.files["image"]
        if file.filename == "" or not allowed_file(file.filename):
            flash("Invalid file format", "danger")
            return redirect(request.url)
        
        # Get form inputs: food name, category, and quantity (in grams)
        food_name_input = request.form.get("food_name")
        food_category = request.form.get("food_category")
        quantity_input = request.form.get("quantity")
        if not food_name_input:
            flash("Please enter the food name.", "danger")
            return redirect(request.url)
        if not quantity_input:
            flash("Please enter the quantity (in grams).", "danger")
            return redirect(request.url)
        try:
            quantity = float(quantity_input)
            if quantity <= 0:
                raise ValueError
        except ValueError:
            flash("Please enter a valid quantity (a positive number).", "danger")
            return redirect(request.url)
        
        # Construct search query: combine category (if not "Other") with food name
        if food_category and food_category.lower() != "other":
            search_query = f"{food_category} {food_name_input}"
        else:
            search_query = food_name_input
        
        # Save uploaded image
        filename = secure_filename(file.filename)
        file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(file_path)
        image_path = filename
        
        # Query USDA API with the search query
        nutrients = get_nutritional_info(search_query)
        if nutrients is None:
            flash("Nutritional information not found for: " + search_query, "danger")
            return redirect(request.url)
        
        # Scale nutrient values from per 100g to the user's quantity
        scaled_nutrients = []
        for nutrient in nutrients:
            try:
                base_value = float(nutrient["value"])
                scaled_value = base_value * (quantity / 100)
                scaled_value = round(scaled_value, 2)
            except (ValueError, TypeError):
                scaled_value = nutrient["value"]
            scaled_nutrients.append({
                "name": nutrient["name"],
                "value": scaled_value,
                "unit": nutrient["unit"]
            })
        
        result = {
            "food_name": food_name_input,
            "search_query": search_query,
            "nutrients": nutrients,               # Base values per 100g
            "scaled_nutrients": scaled_nutrients,   # Values for the entered quantity
            "quantity": quantity,
            "filename": filename
        }
        # Add timestamp, date, and username to the result record
        result['timestamp'] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        result['date'] = datetime.datetime.now().strftime("%Y-%m-%d")
        result['username'] = session.get('email')
        # Save record to Firestore history collection~
        db.collection('history').add(result)
        
        return render_template("result.html", result=result, image_path=image_path)
    return render_template("upload_food.html", result=result, image_path=image_path)
#========================================================================================================================
#admin details
#========================================================================================================================
@app.route('/client_view')
def client_view():
    # Optionally, restrict this view to admin only:
    if 'admin' not in session:
        flash('Unauthorized Access!', 'danger')
        return redirect(url_for('login'))
    
    users = []
    # Query all user documents from the "users" collection.
    users_ref = db.collection('users').stream()
    for doc in users_ref:
        user_data = doc.to_dict()
        user_data['id'] = doc.id  # store document ID for reference
        users.append(user_data)
    
    return render_template('client_view.html', users=users)

#========================================================================================================================
@app.route('/remove_user/<user_id>', methods=['POST'])
def remove_user(user_id):
    # Optionally, restrict removal to admin users only.
    if 'admin' not in session:
        flash('Unauthorized access.', 'danger')
        return redirect(url_for('login'))
    try:
        db.collection('users').document(user_id).delete()
        flash('User removed successfully.', 'success')
    except Exception as e:
        flash(f'Error removing user: {e}', 'danger')
    return redirect(url_for('client_view'))
#========================================================================================================================
@app.route('/client_view_history')
def client_view_history():
    if 'admin' not in session:
        flash('Unauthorized Access!', 'danger')
        return redirect(url_for('login'))
    
    users_history = {}
    docs = db.collection('history').stream()
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        username = data.get('username', 'Unknown')
        if username not in users_history:
            users_history[username] = []
        users_history[username].append(data)
    
    # Convert to list of tuples sorted by username
    users_history = sorted(users_history.items(), key=lambda x: x[0])
    
    return render_template('client_view_history.html', users_history=users_history)

@app.route('/client_view_history/<username>')
def client_view_history_user(username):
    if 'admin' not in session:
        flash('Unauthorized Access!', 'danger')
        return redirect(url_for('login'))
    docs = db.collection('history').where('username', '==', username).stream()
    history_items = []
    for doc in docs:
        data = doc.to_dict()
        data['id'] = doc.id
        history_items.append(data)
    # Sort by timestamp descending
    history_items.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return render_template('client_view_history_user.html', username=username, history=history_items)

@app.route('/remove_history/<history_id>', methods=['POST'])
def remove_history(history_id):
    if 'admin' not in session:
        flash('Unauthorized Access!', 'danger')
        return redirect(url_for('login'))
    try:
        username = request.form.get('username')
        db.collection('history').document(history_id).delete()
        flash('History record removed successfully.', 'success')
    except Exception as e:
        flash(f'Error removing history record: {e}', 'danger')
    return redirect(url_for('client_view_history_user', username=username))
#========================================================================================================================

if __name__ == '__main__':
    app.run(debug=True)
