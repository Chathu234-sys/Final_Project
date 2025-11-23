from flask import Flask, request, jsonify, render_template, flash, redirect, url_for, send_from_directory, session
import mysql.connector
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import jwt
from datetime import datetime, timedelta
from functools import wraps
import json
import numpy as np
import joblib
import tensorflow as tf
import pandas as pd

# Import ML modules
try:
    from nail_shape_analyzer import NailShapeAnalyzer
except ImportError as e:
    print(f"Warning: ML modules not available: {e}")
    NailShapeAnalyzer = None

app = Flask(__name__, template_folder='template', static_folder='static')

# Configuration - MySQL Database (phpMyAdmin)
app.config['SECRET_KEY'] = 'your-secret-key-here-change-in-production'
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/glossify'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_recycle': 280,
    'pool_timeout': 20,
    'pool_pre_ping': True
}
app.config['UPLOAD_FOLDER'] = 'static/uploads'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize extensions
db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database Models
class User(UserMixin, db.Model):
    __tablename__ = "users"
    
    id = db.Column(db.Integer, primary_key=True, index=True)
    username = db.Column(db.String(50), unique=True, index=True, nullable=False)
    email = db.Column(db.String(100), unique=True, index=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    nail_images = db.relationship("NailShapeImage", back_populates="user", cascade="all, delete-orphan")
    quiz_results = db.relationship("QuizResult", back_populates="user", cascade="all, delete-orphan")
    recommendations = db.relationship("Recommendation", back_populates="user", cascade="all, delete-orphan")

class NailShapeImage(db.Model):
    __tablename__ = "nailshapeimages"
    
    id = db.Column(db.Integer, primary_key=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    image_path = db.Column(db.String(255), nullable=False)
    predicted_shape = db.Column(db.String(50), nullable=True)
    confidence_score = db.Column(db.Float, nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship("User", back_populates="nail_images")

class QuizResult(db.Model):
    __tablename__ = "quiz_results"
    
    id = db.Column(db.Integer, primary_key=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    skin_tone = db.Column(db.String(50), nullable=False)
    finish_type = db.Column(db.String(50), nullable=False)
    outfit_color = db.Column(db.String(50), nullable=False)
    occasion = db.Column(db.String(50), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    user = db.relationship("User", back_populates="quiz_results")

class Product(db.Model):
    __tablename__ = "products"
    
    id = db.Column(db.Integer, primary_key=True, index=True)
    name = db.Column(db.String(100), nullable=False)
    brand_name = db.Column(db.String(100), nullable=False)
    hex_color = db.Column(db.String(7), nullable=False)  # #RRGGBB format
    finish_type = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, nullable=True)
    description = db.Column(db.Text, nullable=True)
    image_url = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    recommendations = db.relationship("Recommendation", back_populates="product", cascade="all, delete-orphan")

class Recommendation(db.Model):
    __tablename__ = "recommendations"
    
    id = db.Column(db.Integer, primary_key=True, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=True)
    recommendation_score = db.Column(db.Float, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    recommended_shades = db.Column(db.Text, nullable=False)
    
    # Relationships
    user = db.relationship("User", back_populates="recommendations")
    product = db.relationship("Product", back_populates="recommendations")

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

# JWT Configuration
JWT_SECRET_KEY = "your-jwt-secret-key-change-in-production"
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

def create_jwt_token(user_id):
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

def verify_jwt_token(token):
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload['user_id']
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'message': 'Token is missing'}), 401
        
        if token.startswith('Bearer '):
            token = token[7:]
        
        user_id = verify_jwt_token(token)
        if not user_id:
            return jsonify({'message': 'Token is invalid or expired'}), 401
        
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({'message': 'User not found'}), 401
        
        return f(user, *args, **kwargs)
    return decorated

# Frontend Routes (serve HTML templates)
@app.route('/')
def home():
    return render_template('index_new.html')

@app.route('/upload')
@app.route('/upload.html')
def upload_page():
    return render_template('upload.html')

@app.route('/quiz')
@app.route('/quiz.html')
def quiz_page():
    return render_template('quiz.html')

@app.route('/results')
@app.route('/results.html')
def results_page():
    # Prefer dataset-based session hex codes if available
    try:
        if session.get('dataset_hex'):
            hexes = session.get('dataset_hex') or []
            h1 = hexes[0] if len(hexes) > 0 else None
            h2 = hexes[1] if len(hexes) > 1 else None
            h3 = hexes[2] if len(hexes) > 2 else None
            brands = session.get('dataset_brands') or []
            b1 = brands[0] if len(brands) > 0 else None
            b2 = brands[1] if len(brands) > 1 else None
            b3 = brands[2] if len(brands) > 2 else None
            return render_template('results.html', hex1=h1, hex2=h2, hex3=h3, brand1=b1, brand2=b2, brand3=b3)
        # No dataset recommendations available
        return render_template('results.html')
    except Exception as e:
        flash(f"Error loading recommendations: {e}", 'error')
    return render_template('results.html')


@app.route('/recommend', methods=['POST'])
def recommend():
    """Direct recommend route using dataset rules, returns results.html with hex1-3."""
    try:
        user_input = {
            'skin_tone': request.form.get('skin_tone', ''),
            'age': int(request.form.get('age', 0) or 0),
            'finish_type': request.form.get('finish_type', ''),
            'dress_color': request.form.get('dress_color') or request.form.get('outfit_color', ''),
            'occasion': request.form.get('occasion', ''),
            'brand_name': request.form.get('brand_name', '')
        }

        recs = recommend_from_dataset(user_input, top_n=3)
        hexes = [r['hex'] for r in recs]
        brands = [r['brand'] for r in recs]

        while len(hexes) < 3:
            hexes.append(None)
            brands.append(None)

        return render_template(
            'results.html',
            hex1=hexes[0],
            hex2=hexes[1],
            hex3=hexes[2],
            brand1=brands[0],
            brand2=brands[1],
            brand3=brands[2],
        )
    except Exception as e:
        flash(f'Recommendation error: {str(e)}', 'error')
    return render_template('results.html')

@app.route('/login')
@app.route('/login.html')
def login_page():
    return render_template('login.html')

@app.route('/signup')
@app.route('/signup.html')
def signup_page():
    return render_template('signup.html')

@app.route('/contact')
@app.route('/contact.html')
def contact_page():
    return render_template('contact.html')


@app.route('/send-message', methods=['POST'])
def send_message():
    try:
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        message = request.form.get('message')

        if not name or not email or not message:
            flash('Please fill in required fields', 'error')
            return redirect(url_for('contact_page'))

        # Save to contacts table
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO contacts (name, email, phone, message, sent_at) VALUES (%s, %s, %s, %s, NOW())",
            (name, email, phone, message)
        )
        conn.commit()
        cur.close()
        conn.close()

        flash('Message sent successfully!', 'success')
        return redirect(url_for('contact_page'))
    except Exception as e:
        flash(f'Failed to send message: {str(e)}', 'error')
        return redirect(url_for('contact_page'))

@app.route('/admin/login')
@app.route('/admin_login.html')
def admin_login_page():
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
@app.route('/admin_dashboard.html')
@login_required
def admin_dashboard_page():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('home'))
    try:
        total_users = User.query.count()
        total_quizzes = QuizResult.query.count()
    except Exception:
        total_users = 0
        total_quizzes = 0

    # Load model training history from DB so it persists across refresh
    training_history = []
    last_retrained = None
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, training_date, training_time, status, created_at FROM modeltraininglog ORDER BY created_at DESC LIMIT 50"
        )
        rows = cur.fetchall()
        training_history = [
            {
                'id': r[0],
                'date': r[1].strftime('%Y-%m-%d') if r[1] else '',
                'time': r[2].strftime('%H:%M') if r[2] else '',
                'status': r[3],
                'created_at': r[4].strftime('%Y-%m-%d %H:%M') if r[4] else ''
            }
            for r in rows
        ]
        if training_history:
            last_retrained = training_history[0]['created_at']
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Failed to load training history: {e}")

    return render_template(
        'admin_dashboard.html',
        total_users=total_users,
        total_quizzes=total_quizzes,
        training_history=training_history,
        last_retrained=last_retrained
    )


@app.route('/admin/retrain', methods=['POST'])
@login_required
def admin_retrain_model():
    if not current_user.is_admin:
        return jsonify({'error': 'Forbidden'}), 403
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        # log into modeltraininglog (training_date, training_time, status, created_at)
        cur.execute(
            "INSERT INTO modeltraininglog (training_date, training_time, status, created_at) VALUES (CURDATE(), CURTIME(), %s, NOW())",
            ("Success",)
        )
        conn.commit()
        cur.execute("SELECT LAST_INSERT_ID()")
        new_id = cur.fetchone()[0]
        # Fetch the inserted row details
        cur.execute(
            "SELECT training_date, training_time, status, created_at FROM modeltraininglog WHERE id=%s",
            (new_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        date_val = row[0] if row else None
        time_val = row[1] if row else None
        created_val = row[3] if row else None
        def to_str(v, fmt=None):
            try:
                return v.strftime(fmt) if fmt and hasattr(v, 'strftime') else (str(v) if v is not None else '')
            except Exception:
                return str(v) if v is not None else ''
        payload = {
            'id': int(new_id),
            'date': to_str(date_val, '%Y-%m-%d'),
            'time': to_str(time_val, '%H:%M'),
            'status': row[2] if row else 'Triggered',
            'created_at': to_str(created_val, '%Y-%m-%d %H:%M')
        }
        return jsonify({'message': 'Training triggered and logged', 'row': payload})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/admin/training-history', methods=['GET'])
@login_required
def admin_training_history():
    if not current_user.is_admin:
        return jsonify({'error': 'Forbidden'}), 403
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, training_date, training_time, status, created_at FROM modeltraininglog ORDER BY created_at DESC LIMIT 100"
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        def to_str(v, fmt=None):
            try:
                return v.strftime(fmt) if fmt and hasattr(v, 'strftime') else (str(v) if v is not None else '')
            except Exception:
                return str(v) if v is not None else ''
        data = [
            {
                'id': int(r[0]),
                'date': to_str(r[1], '%Y-%m-%d'),
                'time': to_str(r[2], '%H:%M'),
                'status': r[3],
                'created_at': to_str(r[4], '%Y-%m-%d %H:%M')
            }
            for r in rows
        ]
        return jsonify({'rows': data})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/admin/manage-product')
@app.route('/manage_product.html')
@login_required
def manage_product_page():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('home'))
    try:
        products = Product.query.order_by(Product.created_at.desc()).all()
    except Exception:
        products = []
    return render_template('manage_product.html', products=products)


@app.route('/admin/add-product', methods=['POST'])
@login_required
def admin_add_product():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('home'))
    try:
        name = request.form.get('name')
        brand = request.form.get('brand')
        hex_code = request.form.get('hex') or ''
        finish_type = request.form.get('finish_type') or 'Unknown'

        if not name or not brand:
            flash('Name and Brand are required.', 'error')
            return redirect(url_for('manage_product_page'))

        # Use direct MySQL insert to ensure persistence in your existing schema
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO products (name, brand_name, hex_color, finish_type, created_at) VALUES (%s, %s, %s, %s, NOW())",
            (name, brand, hex_code, finish_type)
        )
        conn.commit()
        cur.close()
        conn.close()
        flash('Product added successfully.', 'success')
    except Exception as e:
        flash(f'Failed to add product: {str(e)}', 'error')
    return redirect(url_for('manage_product_page'))

@app.route('/admin/customer-history')
@app.route('/customer_history.html')
@login_required
def customer_history_page():
    if current_user.is_anonymous:
        return redirect(url_for('login_page'))

    target_user_id = current_user.id

    quizzes = QuizResult.query.filter_by(user_id=target_user_id)\
        .order_by(QuizResult.created_at.asc()).all()

    history_data = []
    for idx, quiz in enumerate(quizzes):
        lower_bound = quiz.created_at or datetime.min
        upper_bound = quizzes[idx + 1].created_at if idx + 1 < len(quizzes) else None

        rec_query = Recommendation.query.filter(Recommendation.user_id == target_user_id)
        rec_query = rec_query.filter(Recommendation.created_at >= lower_bound)
        if upper_bound:
            rec_query = rec_query.filter(Recommendation.created_at < upper_bound)

        rec_rows = rec_query.order_by(Recommendation.created_at.asc()).all()
        recs = []
        for rec in rec_rows:
            try:
                shades = json.loads(rec.recommended_shades or "[]")
            except (TypeError, json.JSONDecodeError):
                shades = []
            for shade in shades:
                if isinstance(shade, dict):
                    hex_code = shade.get('hex')
                    brand_label = shade.get('brand')
                else:
                    hex_code = shade
                    brand_label = None
                if hex_code:
                    recs.append({
                        'hex': hex_code,
                        'brand': brand_label or 'Recommended'
                    })
                if len(recs) >= 3:
                    break
            if len(recs) >= 3:
                break

        history_data.append({
            'date': quiz.created_at.strftime('%Y-%m-%d %H:%M') if quiz.created_at else '--',
            'age': quiz.age,
            'skin_tone': quiz.skin_tone,
            'occasion': quiz.occasion,
            'finish_type': quiz.finish_type,
            'dress_color': quiz.outfit_color,
            'recommendations': recs
        })

    history_data = list(reversed(history_data))

    return render_template('customer_history.html', history=history_data, profile=current_user)

# Frontend Form Handling Routes
@app.route('/signup', methods=['POST'])
def signup_form():
    """Handle signup form submission"""
    try:
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        address = request.form.get('address')
        password = request.form.get('password')
        
        if not all([name, email, password]):
            flash('Please fill in all required fields', 'error')
            return redirect(url_for('signup_page'))
        
        # Check if user already exists
        existing_user = User.query.filter(
            (User.username == name) | (User.email == email)
        ).first()
        
        if existing_user:
            flash('Username or email already registered', 'error')
            return redirect(url_for('signup_page'))
        
        # Create new user
        hashed_password = generate_password_hash(password)
        new_user = User(
            username=name,
            email=email,
            password_hash=hashed_password
        )
        
        db.session.add(new_user)
        db.session.commit()
        
        flash('Account created successfully! Please login.', 'success')
        return redirect(url_for('login_page'))
        
    except Exception as e:
        flash(f'Error creating account: {str(e)}', 'error')
        return redirect(url_for('signup_page'))

@app.route('/login', methods=['POST'])
def login_form():
    """Handle login form submission (email or username + password)."""
    try:
        identifier = request.form.get('email') or request.form.get('username')
        password = request.form.get('password')
        
        if not identifier or not password:
            flash('Please enter email/username and password', 'error')
            return redirect(url_for('login_page'))
        
        # Prefer email lookup when input contains '@'
        if '@' in identifier:
            user = User.query.filter_by(email=identifier).first()
        else:
            user = User.query.filter_by(username=identifier).first()
        
        if not user or not check_password_hash(user.password_hash, password):
            flash('Invalid credentials', 'error')
            return redirect(url_for('login_page'))
        
        login_user(user)
        flash('Login successful!', 'success')
        return redirect(url_for('home'))
        
    except Exception as e:
        flash(f'Login error: {str(e)}', 'error')
        return redirect(url_for('login_page'))

@app.route('/admin/login', methods=['POST'])
def admin_login_form():
    """Handle admin login form submission"""
    try:
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please enter username and password', 'error')
            return redirect(url_for('admin_login_page'))
        
        user = User.query.filter_by(username=username).first()
        
        if not user or not check_password_hash(user.password_hash, password):
            flash('Invalid username or password', 'error')
            return redirect(url_for('admin_login_page'))
        
        if not user.is_admin:
            flash('Access denied. Admin privileges required.', 'error')
            return redirect(url_for('admin_login_page'))
        
        # Save admin login event into admin_users table if not exists
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT id FROM admin_users WHERE username=%s LIMIT 1", (user.username,))
            row = cur.fetchone()
            if not row:
                cur.execute(
                    "INSERT INTO admin_users (username, password_hash) VALUES (%s, %s)",
                    (user.username, user.password_hash)
                )
                conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"Admin user logging failed: {e}")
        
        login_user(user)
        flash('Admin login successful!', 'success')
        return redirect(url_for('admin_dashboard_page'))
        
    except Exception as e:
        flash(f'Login error: {str(e)}', 'error')
        return redirect(url_for('admin_login_page'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('home'))

@app.route('/results', methods=['POST'])
def quiz_submission():
    """Handle quiz form submission"""
    try:
        age = request.form.get('age')
        skin_tone = request.form.get('skin_tone')
        finish_type = request.form.get('finish_type')
        outfit_color = request.form.get('outfit_color')
        occasion = request.form.get('occasion')
        
        if not all([age, skin_tone, finish_type, outfit_color, occasion]):
            flash('Please fill in all quiz fields', 'error')
            return redirect(url_for('quiz_page'))
        
        # Store quiz data in session for results page context
        session['quiz_data'] = {
            'age': age,
            'skin_tone': skin_tone,
            'finish_type': finish_type,
            'outfit_color': outfit_color,
            'occasion': occasion
        }
        
        # Persist quiz result to database (quiz_results table)
        try:
            if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                user_id_val = int(current_user.id)
            else:
                user_id_val = get_or_create_guest_user_id()
            quiz_row = QuizResult(
                user_id=user_id_val,
                age=int(age),
                skin_tone=skin_tone,
                finish_type=finish_type,
                outfit_color=outfit_color,
                occasion=occasion
            )
            db.session.add(quiz_row)
            db.session.commit()
        except Exception as e:
            # Do not block UX if DB save fails; log to console
            print(f"Quiz save failed: {e}")
        
        # Dataset-based recommendations
        user_input = {
            'age': int(age),
            'skin_tone': skin_tone,
            'finish_type': finish_type,
            'dress_color': outfit_color,
            'occasion': occasion,
            'brand_name': request.form.get('brand_name', '')
        }
        dataset_recs = recommend_from_dataset(user_input, top_n=3)
        session['dataset_hex'] = [r['hex'] for r in dataset_recs]
        session['dataset_brands'] = [r['brand'] for r in dataset_recs]

        # Persist recommendations to database (recommendations table)
        try:
            if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                rec_user_id = int(current_user.id)
            else:
                rec_user_id = get_or_create_guest_user_id()

            if dataset_recs:
                # Ensure we have at least one linked product id to satisfy schema constraints
                first_product_id = None
                for rec in dataset_recs:
                    hex_code = rec.get('hex')
                    brand_label = rec.get('brand') or 'Glossify'
                    if not hex_code:
                        continue
                    product = Product.query.filter_by(hex_color=hex_code, brand_name=brand_label).first()
                    if not product:
                        product = Product(
                            name=f"{brand_label} {hex_code}",
                            brand_name=brand_label,
                            hex_color=hex_code,
                            finish_type=finish_type or 'Unknown'
                        )
                        db.session.add(product)
                        db.session.flush()
                    if first_product_id is None:
                        first_product_id = product.id

                recommended_payload = json.dumps(dataset_recs)
                rec_row = Recommendation(
                    user_id=rec_user_id,
                    product_id=first_product_id,
                    recommendation_score=0.90,
                    recommended_shades=recommended_payload
                )
                db.session.add(rec_row)

            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"Recommendation save failed: {e}")
        
        return redirect(url_for('results_page'))
        
    except Exception as e:
        flash(f'Error submitting quiz: {str(e)}', 'error')
        return redirect(url_for('quiz_page'))

@app.route('/upload', methods=['POST'])
def upload_nail_image():
    """Handle nail image upload, predict shape, store in MySQL, and redirect to results."""
    try:
        if 'file' not in request.files:
            flash('No file provided', 'error')
            return redirect(url_for('upload_page'))
        
        file = request.files['file']
        if file.filename == '':
            flash('No file selected', 'error')
            return answer(url_for('upload_page'))

        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)

        # Predict nail shape using the trained model
        prediction_error = None
        try:
            analyzer = NailShapeAnalyzer()
            shape, _confidence = analyzer.predict_shape(file_path)
            predicted_shape = (shape or 'Unknown').title()
        except Exception as e:
            prediction_error = str(e)
            predicted_shape = 'Unknown'
            print(f"Shape prediction failed: {e}")

        # Store record in MySQL table nailshapeimages (matching your schema)
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
                user_id_val = int(current_user.id)
            else:
                user_id_val = get_or_create_guest_user_id()
            cur.execute(
                "INSERT INTO nailshapeimages (user_id, image_path, predicted_shape, uploaded_at) VALUES (%s, %s, %s, NOW())",
                (user_id_val, f"uploads/{filename}", predicted_shape)
            )
            conn.commit()
            cur.close()
            conn.close()
        except Exception as e:
            print(f"MySQL insert failed: {e}")

        # If this is an AJAX request, return JSON for inline display
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            if prediction_error:
                return jsonify({'error': f'Prediction error: {prediction_error}'}), 200
            if predicted_shape.lower() == 'not a human hand':
                return jsonify({
                    'predicted_shape': 'Not a human hand',
                    'recommendations': [],
                    'image_path': f"uploads/{filename}"
                })
            return jsonify({
                'predicted_shape': predicted_shape,
                'recommendations': generate_nail_shape_recommendations(predicted_shape),
                'image_path': f"uploads/{filename}"
            })

        return redirect(url_for('results_page', shape=predicted_shape))
    except Exception as e:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json:
            return jsonify({'error': f'Upload error: {str(e)}'}), 200
        flash(f'Upload error: {str(e)}', 'error')
        return redirect(url_for('upload_page'))

def generate_nail_shape_recommendations(shape):
    """Generate recommendations based on nail shape"""
    recommendations = {
        'oval': [
            'Oval nails are versatile and elegant',
            'Try classic red or nude shades',
            'Perfect for both casual and formal occasions',
            'Consider glossy or matte finishes'
        ],
        'square': [
            'Square nails are modern and bold',
            'Experiment with bright colors and metallics',
            'Great for making a statement',
            'Try geometric nail art designs'
        ],
        'round': [
            'Round nails are natural and practical',
            'Opt for soft, feminine colors',
            'Perfect for everyday wear',
            'Consider pastel shades and light finishes'
        ],
        'almond': [
            'Almond nails are sophisticated and trendy',
            'Try bold colors and glitter finishes',
            'Perfect for special occasions',
            'Consider ombre or gradient effects'
        ],
        'stiletto': [
            'Stiletto nails are dramatic and edgy',
            'Bold colors and metallic finishes work best',
            'Perfect for parties and events',
            'Consider dark shades and high-shine finishes'
        ]
    }
    
    return recommendations.get(shape.lower(), [
        'Your nail shape is unique!',
        'Try different colors to find your perfect match',
        'Consider your skin tone and occasion when choosing colors'
    ])


# --- MySQL Integration ---
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "",
    "database": "glossify",
}


def get_db_connection():
    """Return a new MySQL connection using mysql.connector."""
    return mysql.connector.connect(**DB_CONFIG)


def get_or_create_guest_user_id() -> int:
    """Return a valid user_id for uploads when no user is logged in.
    Creates a 'guest' user if it does not exist."""
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id FROM users WHERE username=%s LIMIT 1", ("guest",))
        row = cur.fetchone()
        if row:
            return int(row[0])
        # create guest
        from datetime import datetime as _dt
        email = f"guest+{_dt.utcnow().strftime('%Y%m%d%H%M%S')}@example.com"
        cur.execute(
            "INSERT INTO users (username, email, password_hash, is_admin, created_at, updated_at) VALUES (%s,%s,%s,%s,NOW(),NOW())",
            ("guest", email, "", 0),
        )
        conn.commit()
        cur.execute("SELECT LAST_INSERT_ID()")
        new_id = cur.fetchone()[0]
        return int(new_id)
    finally:
        cur.close()
        conn.close()

# --- ML Helpers for Polish Recommendation ---
# V3 artifact cache (loaded once)
_V3_MODEL = None
_V3_SCALER = None
_V3_KMEANS = None
_V3_LABEL_ENCODER = None
_V3_PREPROCESSOR = None
_DATASET_DF = None


def _v3_paths():
    """Resolve v3 artifact paths, tolerating singular/plural folder names and case differences.
    Also detect a SavedModel export directory if present.
    """
    base_dir = os.path.dirname(os.path.abspath(__file__))
    override_dir = os.environ.get('NAILPOLISH_MODEL_DIR')
    candidate_dirs = []
    if override_dir:
        candidate_dirs.append(override_dir)
    candidate_dirs.extend([
        os.path.join(base_dir, 'data', 'trained_model', 'NailPolish_Model'),
        os.path.join(base_dir, 'data', 'trained_models', 'NailPolish_Model'),
    ])

    def find_dir():
        for d in candidate_dirs:
            if os.path.isdir(d):
                return d
        return candidate_dirs[0]

    model_dir = find_dir()

    def find_file_ci(directory: str, names: list) -> str:
        try:
            entries = os.listdir(directory)
            lower_map = {e.lower(): e for e in entries}
            for name in names:
                if name.lower() in lower_map:
                    return os.path.join(directory, lower_map[name.lower()])
        except Exception:
            pass
        return os.path.join(directory, names[0])

    # Detect SavedModel folder: a subdir containing saved_model.pb
    saved_dir = None
    try:
        for entry in os.listdir(model_dir):
            full = os.path.join(model_dir, entry)
            if os.path.isdir(full) and os.path.exists(os.path.join(full, 'saved_model.pb')):
                saved_dir = full
                break
    except Exception:
        saved_dir = None

    return {
        'model': find_file_ci(model_dir, ['nail_polish_model_v3.h5']),
        'scaler': find_file_ci(model_dir, ['scaler_v3.pkl']),
        'kmeans': find_file_ci(model_dir, ['Kmeans_v3.pkl', 'kmeans_v3.pkl']),
        'label_encoder': find_file_ci(model_dir, ['label_encoder_v3.pkl']),
        'preprocessor': find_file_ci(model_dir, ['preprocessor_v3.pkl']),
        'saved_model_dir': saved_dir,
        'dir': model_dir,
    }


def load_v3_artifacts():
    global _V3_MODEL, _V3_SCALER, _V3_KMEANS, _V3_LABEL_ENCODER, _V3_PREPROCESSOR
    if _V3_MODEL is not None:
        return
    paths = _v3_paths()
    missing = []
    for key in ['model', 'preprocessor', 'scaler', 'label_encoder']:
        if not os.path.exists(paths[key]):
            missing.append((key, paths[key]))
    if missing:
        details = '; '.join([f"{k}:{p}" for (k, p) in missing])
        raise FileNotFoundError(f"Missing required v3 artifacts in {paths.get('dir')}: {details}")

    # Prefer SavedModel if present (more tolerant across TF versions)
    if paths.get('saved_model_dir') and os.path.isdir(paths['saved_model_dir']):
        _V3_MODEL = tf.keras.models.load_model(paths['saved_model_dir'])
    else:
        # Tolerant model loading to handle Keras version differences
        def _load_model_tolerant(model_path: str):
            last_err = None
            for attempt in (
                ('tf_compile_safe', dict(compile=False, safe_mode=False)),
                ('tf_compile_only', dict(compile=False)),
                ('tf_custom_input', dict(compile=False, custom_objects={'InputLayer': tf.keras.layers.InputLayer})),
                ('tf_plain', dict()),
            ):
                try:
                    return tf.keras.models.load_model(model_path, **attempt[1])
                except Exception as e:  # try next
                    last_err = e
                    continue
            # Try compat.v1
            try:
                return tf.compat.v1.keras.models.load_model(model_path, compile=False)
            except Exception as e:
                raise RuntimeError(f"Failed to load v3 model: {last_err or ''} / {e}")

        _V3_MODEL = _load_model_tolerant(paths['model'])
    _V3_PREPROCESSOR = joblib.load(paths['preprocessor'])
    try:
        _V3_SCALER = joblib.load(paths['scaler'])
    except Exception:
        _V3_SCALER = None
    try:
        _V3_KMEANS = joblib.load(paths['kmeans']) if os.path.exists(paths['kmeans']) else None
    except Exception:
        _V3_KMEANS = None
    _V3_LABEL_ENCODER = joblib.load(paths['label_encoder'])


def predict_hex_codes_v3(user_input: dict) -> list:
    """Preprocess and predict top 3 HEX codes using v3 model + preprocessors."""
    load_v3_artifacts()
    # Expected keys: skin_tone, age, finish_type, dress_color, occasion, brand_name
    # Build a single-row input for preprocessor
    import pandas as pd
    df = pd.DataFrame([{
        'skin_tone': user_input.get('skin_tone', ''),
        'age': int(user_input.get('age', 0) or 0),
        'finish_type': user_input.get('finish_type', ''),
        'dress_color': user_input.get('dress_color', ''),
        'occasion': user_input.get('occasion', ''),
        'brand_name': user_input.get('brand_name', ''),
    }])

    # Apply preprocessing pipeline
    X_processed = _V3_PREPROCESSOR.transform(df)
    # Optional scaling
    try:
        X_scaled = _V3_SCALER.transform(X_processed)
    except Exception:
        X_scaled = X_processed

    # Optional kmeans (e.g., cluster id as additional feature)
    try:
        cluster = _V3_KMEANS.predict(X_scaled)
        # Concatenate cluster as a feature if model expects it
        import numpy as np
        X_final = np.hstack([X_scaled, cluster.reshape(-1, 1)])
    except Exception:
        X_final = X_scaled

    # Predict probabilities over HEX labels (assuming label-encoded hex classes)
    probs = _V3_MODEL.predict(X_final, verbose=0)[0]
    # Pick top-3 class indices
    import numpy as np
    top_indices = np.argsort(probs)[-3:][::-1]
    # Map back to HEX codes via label encoder
    hex_codes = _V3_LABEL_ENCODER.inverse_transform(top_indices)
    return list(hex_codes)


# --- Dataset-based recommendation (CSV) ---
def _load_dataset():
    global _DATASET_DF
    if _DATASET_DF is not None:
        return _DATASET_DF
    base_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(base_dir, 'data', 'trained_models', 'NailPolish_Model', 'nail_polish_datasets.csv')
    _DATASET_DF = pd.read_csv(csv_path)
    # Normalize string columns
    for col in ['skin_tone', 'finish_type', 'dress_color', 'occasion', 'brand_name', 'recommended_hex_code']:
        if col in _DATASET_DF.columns:
            _DATASET_DF[col] = _DATASET_DF[col].astype(str)
    if 'age' in _DATASET_DF.columns:
        _DATASET_DF['age'] = pd.to_numeric(_DATASET_DF['age'], errors='coerce').fillna(0)
    return _DATASET_DF


def recommend_from_dataset(user_input: dict, top_n: int = 3) -> list:
    df = _load_dataset().copy()
    if df.empty:
        return []

    def norm(val):
        return (val or '').strip().lower()

    filters = [
        ('skin_tone', 'skin_tone'),
        ('finish_type', 'finish_type'),
        ('dress_color', 'dress_color'),
        ('occasion', 'occasion')
    ]

    candidates = df
    for col, key in filters:
        desired = norm(user_input.get(key))
        if not desired or col not in candidates.columns:
            continue
        filtered = candidates[candidates[col].str.lower() == desired]
        if not filtered.empty:
            candidates = filtered

    if candidates.empty:
        candidates = df

    user_age = int(user_input.get('age', 0) or 0)
    if 'age' in candidates.columns:
        candidates = candidates.assign(age_diff=(candidates['age'] - user_age).abs())
        candidates = candidates.sort_values(by='age_diff')
    else:
        candidates = candidates.head(top_n)

    recs = []
    for _, row in candidates.head(top_n).iterrows():
        recs.append({
            'hex': row.get('recommended_hex_code', '#FF69B4'),
            'brand': row.get('brand_name', 'Unknown')
        })
    return recs


def _get_brand_names_for_hexes(hex_list: list) -> list:
    """Return brand names aligned to the provided HEX list using MySQL table nail_polishes.
    If a hex is not found, return 'Unknown'.
    """
    if not hex_list:
        return []
    conn = get_db_connection()
    cur = conn.cursor()
    try:
        placeholders = ','.join(['%s'] * len(hex_list))
        cur.execute(f"SELECT hex_code, brand_name FROM nail_polishes WHERE hex_code IN ({placeholders})", hex_list)
        rows = cur.fetchall()
        hex_to_brand = {row[0]: row[1] for row in rows}
        return [hex_to_brand.get(h, 'Unknown') for h in hex_list]
    finally:
        cur.close()
        conn.close()
def predict_nail_shape(image_path: str) -> str:
    """Convenience function that loads model and predicts shape label."""
    analyzer = NailShapeAnalyzer()
    shape, _conf = analyzer.predict_shape(image_path)
    return shape


@app.route('/api/recommend/live', methods=['POST'])
def api_recommend_live():
    """Return top 3 HEX codes dynamically using dataset filter."""
    try:
        data = request.get_json() or {}
    except Exception:
        data = {}
    try:
        # Map expected keys
        user_input = {
            'skin_tone': data.get('skin_tone', ''),
            'age': int(data.get('age', 0) or 0),
            'finish_type': data.get('finish_type', ''),
            'dress_color': data.get('outfit_color') or data.get('dress_color', ''),
            'occasion': data.get('occasion', ''),
            'brand_name': data.get('brand_name', '')
        }
        recs = recommend_from_dataset(user_input, top_n=3)
        hexes = [r['hex'] for r in recs]
        return jsonify({
            'hex': hexes,
            'brands': [r['brand'] for r in recs]
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 200

def generate_simple_recommendations(skin_tone, finish_type, occasion):
    """Generate simple recommendations based on quiz data"""
    recommendations = []

# API Routes

@app.route('/api/auth/register', methods=['POST'])
def api_register():
    data = request.get_json()
    
    if not data or not all(k in data for k in ['username', 'email', 'password']):
        return jsonify({'error': 'Missing required fields'}), 400
    
    # Check if user already exists
    existing_user = User.query.filter(
        (User.username == data['username']) | (User.email == data['email'])
    ).first()
    
    if existing_user:
        return jsonify({'error': 'Username or email already registered'}), 400
    
    # Create new user
    hashed_password = generate_password_hash(data['password'])
    new_user = User(
        username=data['username'],
        email=data['email'],
        password_hash=hashed_password
    )
    
    db.session.add(new_user)
    db.session.commit()
    
    # Create JWT token
    token = create_jwt_token(new_user.id)
    
    return jsonify({
        'message': 'User registered successfully',
        'user': {
            'id': new_user.id,
            'username': new_user.username,
            'email': new_user.email
        },
        'token': token
    }), 201

@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json()
    
    if not data or 'password' not in data or (('username' not in data) and ('email' not in data)):
        return jsonify({'error': 'Missing email/username or password'}), 400

    identifier = data.get('email') or data.get('username')
    if '@' in identifier:
        user = User.query.filter_by(email=identifier).first()
    else:
        user = User.query.filter_by(username=identifier).first()
    
    if not user or not check_password_hash(user.password_hash, data['password']):
        return jsonify({'error': 'Invalid credentials'}), 401
    
    token = create_jwt_token(user.id)
    
    return jsonify({
        'message': 'Login successful',
        'user': {
            'id': user.id,
            'username': user.username,
            'email': user.email,
            'is_admin': user.is_admin
        },
        'token': token
    })

@app.route('/api/auth/me', methods=['GET'])
@token_required
def api_get_user(user):
    return jsonify({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'is_admin': user.is_admin,
        'created_at': user.created_at.isoformat()
    })

@app.route('/api/quiz/submit', methods=['POST'])
@token_required
def api_submit_quiz(user):
    data = request.get_json()
    
    if not data or not all(k in data for k in ['age', 'skin_tone', 'finish_type', 'outfit_color', 'occasion']):
        return jsonify({'error': 'Missing required quiz fields'}), 400
    
    # Validate data
    if data['age'] < 1 or data['age'] > 120:
        return jsonify({'error': 'Age must be between 1 and 120'}), 400
    
    valid_skin_tones = ["Fair", "Light", "Medium", "Olive", "Dark", "Deep"]
    if data['skin_tone'] not in valid_skin_tones:
        return jsonify({'error': f'Skin tone must be one of: {", ".join(valid_skin_tones)}'}), 400
    
    valid_finish_types = ["Glossy", "Matte", "Metallic", "Shimmer", "Cream"]
    if data['finish_type'] not in valid_finish_types:
        return jsonify({'error': f'Finish type must be one of: {", ".join(valid_finish_types)}'}), 400
    
    valid_occasions = ["Everyday", "Work", "Party", "Wedding", "Casual", "Formal"]
    if data['occasion'] not in valid_occasions:
        return jsonify({'error': f'Occasion must be one of: {", ".join(valid_occasions)}'}), 400
    
    # Create quiz result
    quiz_result = QuizResult(
        user_id=user.id,
        age=data['age'],
        skin_tone=data['skin_tone'],
        finish_type=data['finish_type'],
        outfit_color=data['outfit_color'],
        occasion=data['occasion']
    )
    
    db.session.add(quiz_result)
    db.session.commit()
    
    return jsonify({
        'message': 'Quiz submitted successfully',
        'quiz_result': {
            'id': quiz_result.id,
            'age': quiz_result.age,
            'skin_tone': quiz_result.skin_tone,
            'finish_type': quiz_result.finish_type,
            'outfit_color': quiz_result.outfit_color,
            'occasion': quiz_result.occasion,
            'created_at': quiz_result.created_at.isoformat()
        }
    }), 201

@app.route('/api/nails/upload', methods=['POST'])
@token_required
def api_upload_nail_image(user):
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No file selected'}), 400
    
    if file:
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{filename}"
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(file_path)
        
        # Save to database
        nail_image = NailShapeImage(
            user_id=user.id,
            image_path=f"uploads/{filename}",
            predicted_shape=None,
            confidence_score=None
        )
        
        db.session.add(nail_image)
        db.session.commit()
        
        # Try ML prediction if available
        try:
            if NailShapeAnalyzer:
                analyzer = NailShapeAnalyzer()
                shape, confidence = analyzer.predict_shape(file_path)
                
                # Update database with prediction
                nail_image.predicted_shape = shape
                nail_image.confidence_score = confidence
                db.session.commit()
                
                return jsonify({
                    'message': 'Image uploaded and analyzed successfully',
                    'image': {
                        'id': nail_image.id,
                        'image_path': nail_image.image_path,
                        'predicted_shape': nail_image.predicted_shape,
                        'confidence_score': nail_image.confidence_score,
                        'uploaded_at': nail_image.uploaded_at.isoformat()
                    }
                }), 201
            else:
                return jsonify({
                    'message': 'Image uploaded successfully (ML analysis not available)',
                    'image': {
                        'id': nail_image.id,
                        'image_path': nail_image.image_path,
                        'predicted_shape': None,
                        'confidence_score': None,
                        'uploaded_at': nail_image.uploaded_at.isoformat()
                    }
                }), 201
                
        except Exception as e:
            return jsonify({
                'message': 'Image uploaded but ML analysis failed',
                'error': str(e),
                'image': {
                    'id': nail_image.id,
                    'image_path': nail_image.image_path,
                    'predicted_shape': None,
                    'confidence_score': None,
                    'uploaded_at': nail_image.uploaded_at.isoformat()
                }
            }), 201

@app.route('/api/recommend/generate', methods=['POST'])
@token_required
def api_generate_recommendations(user):
    # Get user's latest quiz result
    quiz_result = QuizResult.query.filter_by(user_id=user.id).order_by(QuizResult.created_at.desc()).first()
    
    if not quiz_result:
        return jsonify({'error': 'No quiz results found. Please complete the quiz first.'}), 400
    
    # Prepare user input for recommendation
    user_input = {
        'age': quiz_result.age,
        'skin_tone': quiz_result.skin_tone,
        'finish_type': quiz_result.finish_type,
        'outfit_color': quiz_result.outfit_color,
        'occasion': quiz_result.occasion
    }
    
    try:
        dataset_recs = recommend_from_dataset(user_input, top_n=3)
        first_product_id = None
        if dataset_recs:
            for rec in dataset_recs:
                hex_code = rec.get('hex')
                brand_label = rec.get('brand') or 'Glossify'
                if not hex_code:
                    continue
                product = Product.query.filter_by(hex_color=hex_code, brand_name=brand_label).first()
                if not product:
                    product = Product(
                        name=f"{brand_label} {hex_code}",
                        brand_name=brand_label,
                        hex_color=hex_code,
                        finish_type=quiz_result.finish_type
                    )
                    db.session.add(product)
                    db.session.flush()
                if first_product_id is None:
                    first_product_id = product.id

        recommendation_entry = None
        if dataset_recs:
            recommendation_entry = Recommendation(
                user_id=user.id,
                product_id=first_product_id,
                recommendation_score=0.90,
                recommended_shades=json.dumps(dataset_recs)
            )
            db.session.add(recommendation_entry)
            db.session.commit()
        else:
            db.session.commit()

        return jsonify({
            'message': 'Recommendations generated successfully',
            'recommendations': [
                {
                    'id': recommendation_entry.id if recommendation_entry else None,
                    'recommended_shades': dataset_recs,
                    'recommendation_score': recommendation_entry.recommendation_score if recommendation_entry else None,
                    'created_at': recommendation_entry.created_at.isoformat() if recommendation_entry else None
                }
            ]
        }), 201
        
    except Exception as e:
        return jsonify({'error': f'Error generating recommendations: {str(e)}'}), 500

@app.route('/api/recommend/my-recommendations', methods=['GET'])
@token_required
def api_get_user_recommendations(user):
    recommendations = Recommendation.query.filter_by(user_id=user.id).order_by(Recommendation.created_at.desc()).all()
    
    return jsonify({
        'recommendations': [
            {
                'id': rec.id,
                'recommended_shades': json.loads(rec.recommended_shades or "[]"),
                'recommendation_score': rec.recommendation_score,
                'created_at': rec.created_at.isoformat()
            }
            for rec in recommendations
        ]
    })

@app.route('/api/nails/my-images', methods=['GET'])
@token_required
def api_get_user_images(user):
    images = NailShapeImage.query.filter_by(user_id=user.id).order_by(NailShapeImage.uploaded_at.desc()).all()
    
    return jsonify({
        'images': [
            {
                'id': img.id,
                'image_path': img.image_path,
                'predicted_shape': img.predicted_shape,
                'confidence_score': img.confidence_score,
                'uploaded_at': img.uploaded_at.isoformat()
            }
            for img in images
        ]
    })

@app.route('/api/quiz/my-results', methods=['GET'])
@token_required
def api_get_user_quiz_results(user):
    results = QuizResult.query.filter_by(user_id=user.id).order_by(QuizResult.created_at.desc()).all()
    
    return jsonify({
        'quiz_results': [
            {
                'id': result.id,
                'age': result.age,
                'skin_tone': result.skin_tone,
                'finish_type': result.finish_type,
                'outfit_color': result.outfit_color,
                'occasion': result.occasion,
                'created_at': result.created_at.isoformat()
            }
            for result in results
        ]
    })

# Serve images from static/images
@app.route('/images/<path:filename>')
def serve_images(filename):
    return send_from_directory('static/images', filename)

def init_database():
    """Initialize database with sample data"""
    with app.app_context():
        try:
            # Create tables
            db.create_all()
            
            # Check if admin user exists
            admin_user = User.query.filter_by(username="admin").first()
            if not admin_user:
                # Create admin user
                admin_user = User(
                    username="admin",
                    email="admin@glossify.com",
                    password_hash=generate_password_hash("admin123"),
                    is_admin=True
                )
                db.session.add(admin_user)
                
                print("Database initialized with admin user")
            else:
                print("Database already initialized")
                
        except Exception as e:
            print(f"Error initializing database: {e}")
            print("Make sure MySQL is running and the 'glossify' database exists in phpMyAdmin")

if __name__ == '__main__':
    init_database()
    app.run(debug=True, host='0.0.0.0', port=5000)
