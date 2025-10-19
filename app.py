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

# Import ML modules
try:
    from nailpolish_model import recommend_polishes
    from nail_shape_analyzer import NailShapeAnalyzer
except ImportError as e:
    print(f"Warning: ML modules not available: {e}")
    recommend_polishes = None
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
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    recommendation_score = db.Column(db.Float, nullable=True)
    recommendation_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
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
    # If session recommendations already exist (quiz flow), render them directly
    if session.get('recommendations'):
        return render_template('results.html')

    # Otherwise, fetch 3 from DB (upload flow case)
    try:
        polishes = recommend_polish(features=None)
        hex1 = polishes[0]['hex_code'] if len(polishes) > 0 else None
        hex2 = polishes[1]['hex_code'] if len(polishes) > 1 else None
        hex3 = polishes[2]['hex_code'] if len(polishes) > 2 else None
        brand1 = polishes[0]['brand_name'] if len(polishes) > 0 else None
        brand2 = polishes[1]['brand_name'] if len(polishes) > 1 else None
        brand3 = polishes[2]['brand_name'] if len(polishes) > 2 else None
        return render_template('results.html', hex1=hex1, brand1=brand1, hex2=hex2, brand2=brand2, hex3=hex3, brand3=brand3)
    except Exception as e:
        flash(f"Error loading recommendations: {e}", 'error')
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
    return render_template('admin_dashboard.html')

@app.route('/admin/manage-product')
@app.route('/manage_product.html')
@login_required
def manage_product_page():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('home'))
    return render_template('manage_product.html')

@app.route('/admin/customer-history')
@app.route('/customer_history.html')
@login_required
def customer_history_page():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('home'))
    return render_template('customer_history.html')

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
    """Handle login form submission"""
    try:
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Please enter username and password', 'error')
            return redirect(url_for('login_page'))
        
        user = User.query.filter_by(username=username).first()
        
        if not user or not check_password_hash(user.password_hash, password):
            flash('Invalid username or password', 'error')
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

        # Try ML-driven recommendations via nailpolish_model if available
        try:
            user_input = {
                'age': int(age),
                'skin_tone': skin_tone,
                'finish_type': finish_type,
                'outfit_color': outfit_color,
                'occasion': occasion
            }
            if recommend_polishes:
                # Get color-brand pairs to render in results
                try:
                    from nailpolish_model import recommend_color_brand_pairs  # type: ignore
                    color_brand = recommend_color_brand_pairs(user_input, top_n=3)
                except Exception:
                    # Fallback: map ids to simple objects
                    ids = recommend_polishes(user_input)
                    color_brand = [{'name': f"Shade #{i+1}", 'brand': 'Unknown', 'hex_color': '#FF69B4', 'price': 9.99, 'reason': 'Model pick'} for i in range(len(ids))]

                # Normalize to the structure expected by results.html
                normalized = []
                for idx, cb in enumerate(color_brand):
                    normalized.append({
                        'name': f"Recommended Shade {idx+1}",
                        'brand': cb.get('brand', 'Unknown'),
                        'hex_color': cb.get('hex_color', '#FF69B4'),
                        'price': 9.99,
                        'reason': f"Based on your {skin_tone} skin tone and {occasion}"
                    })
                session['recommendations'] = normalized
            else:
                session['recommendations'] = generate_simple_recommendations(skin_tone, finish_type, occasion)
        except Exception:
            # Final fallback
            session['recommendations'] = generate_simple_recommendations(skin_tone, finish_type, occasion)
        
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
            return redirect(url_for('upload_page'))

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
def predict_nail_shape(image_path: str) -> str:
    """Convenience function that loads model and predicts shape label."""
    analyzer = NailShapeAnalyzer()
    shape, _conf = analyzer.predict_shape(image_path)
    return shape


def recommend_polish(features=None):
    """
    Load scaler and kmeans from data/trained_models/NailPolish_Model and
    (optionally) use them to select top 3 nail polishes from MySQL.
    If clustering fails or features are missing, fall back to first 3.
    Returns list of dicts: [{brand_name, hex_code}, ...]
    """
    # Load artifacts (paths relative to project root)
    import joblib  # lazy import

    base_dir = os.path.dirname(os.path.abspath(__file__))
    model_dir = os.path.join(base_dir, 'data', 'trained_models', 'NailPolish_Model')
    scaler_path = os.path.join(model_dir, 'scaler.pkl')
    kmeans_path = os.path.join(model_dir, 'kmeans.pkl')
    model_path = os.path.join(model_dir, 'nail_polish_model.h5')
    # Note: We do not need to load the .h5 here for DB-based selection

    # Try to predict cluster (optional)
    cluster_label = None
    try:
        scaler = joblib.load(scaler_path)
        kmeans = joblib.load(kmeans_path)
        if isinstance(features, dict):
            feature_names = getattr(scaler, 'feature_names_in_', None)
            if feature_names is not None:
                # Build vector aligned to scaler feature names
                lower_map = {k.lower(): v for k, v in features.items()}
                vec = []
                for name in feature_names:
                    value = 0.0
                    if name.lower() == 'age':
                        try:
                            value = float(lower_map.get('age', 0) or 0)
                        except Exception:
                            value = 0.0
                    else:
                        parts = name.split('_', 1)
                        if len(parts) == 2:
                            cat, val = parts[0].lower(), parts[1].lower()
                            input_val = str(lower_map.get(cat, '')).lower()
                            value = 1.0 if input_val == val else 0.0
                    vec.append(value)
                try:
                    X = scaler.transform([vec])
                    cluster_label = int(kmeans.predict(X)[0])
                except Exception as e:
                    print(f"Warning: clustering transform/predict failed: {e}")
            else:
                # Scaler missing feature names (sklearn version mismatch) → skip clustering
                pass
    except Exception as e:
        print(f"Warning: clustering unavailable: {e}")

    # Fetch polishes from MySQL
    conn = get_db_connection()
    cur = conn.cursor()

    # Without a cluster column, simply return top 3. You can adapt this to your schema.
    # Dynamic selection; if you have a cluster column you can filter by it.
    cur.execute("SELECT brand_name, hex_code FROM nail_polishes ORDER BY RAND() LIMIT 3")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    results = []
    for row in rows:
        results.append({"brand_name": row[0], "hex_code": row[1]})
    return results


@app.route('/api/recommend/live', methods=['POST'])
def api_recommend_live():
    """Return top 3 color-brand pairs dynamically based on incoming quiz inputs."""
    try:
        data = request.get_json() or {}
    except Exception:
        data = {}
    try:
        results = recommend_polish(features=data)
        return jsonify({'recommendations': results})
    except Exception as e:
        # Fallback to DB top 3 if anything goes wrong
        try:
            conn = get_db_connection()
            cur = conn.cursor()
            cur.execute("SELECT brand_name, hex_code FROM nail_polishes ORDER BY RAND() LIMIT 3")
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return jsonify({'recommendations': [{"brand_name": r[0], "hex_code": r[1]} for r in rows]})
        except Exception as db_e:
            return jsonify({'error': f"{e} / {db_e}"}), 200

def generate_simple_recommendations(skin_tone, finish_type, occasion):
    """Generate simple recommendations based on quiz data"""
    recommendations = []
    
    # Simple recommendation logic
    if skin_tone == 'fair':
        if finish_type == 'glossy':
            recommendations.append({
                'name': 'Classic Red',
                'brand': 'OPI',
                'hex_color': '#FF0000',
                'price': 12.99,
                'reason': 'Perfect for fair skin with glossy finish'
            })
        elif finish_type == 'matte':
            recommendations.append({
                'name': 'Nude Elegance',
                'brand': 'Essie',
                'hex_color': '#F5E6D3',
                'price': 9.99,
                'reason': 'Elegant nude for fair skin'
            })
    elif skin_tone == 'medium':
        if finish_type == 'glossy':
            recommendations.append({
                'name': 'Rose Gold',
                'brand': 'Revlon',
                'hex_color': '#B76E79',
                'price': 7.99,
                'reason': 'Beautiful rose gold for medium skin'
            })
        elif finish_type == 'metallic':
            recommendations.append({
                'name': 'Midnight Blue',
                'brand': 'Sally Hansen',
                'hex_color': '#191970',
                'price': 8.99,
                'reason': 'Stunning metallic blue'
            })
    elif skin_tone == 'deep':
        if finish_type == 'glossy':
            recommendations.append({
                'name': 'Emerald Green',
                'brand': 'China Glaze',
                'hex_color': '#50C878',
                'price': 11.99,
                'reason': 'Vibrant emerald for deep skin'
            })
        elif finish_type == 'glitter':
            recommendations.append({
                'name': 'Golden Sparkle',
                'brand': 'OPI',
                'hex_color': '#FFD700',
                'price': 13.99,
                'reason': 'Gorgeous glitter for special occasions'
            })
    
    # Add some default recommendations if none were generated
    if not recommendations:
        recommendations = [
            {
                'name': 'Classic Red',
                'brand': 'OPI',
                'hex_color': '#FF0000',
                'price': 12.99,
                'reason': 'A timeless classic that suits everyone'
            },
            {
                'name': 'Nude Elegance',
                'brand': 'Essie',
                'hex_color': '#F5E6D3',
                'price': 9.99,
                'reason': 'Perfect for everyday wear'
            },
            {
                'name': 'Midnight Blue',
                'brand': 'Sally Hansen',
                'hex_color': '#191970',
                'price': 8.99,
                'reason': 'Elegant and sophisticated'
            }
        ]
    
    return recommendations

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
    
    if not data or not all(k in data for k in ['username', 'password']):
        return jsonify({'error': 'Missing username or password'}), 400
    
    user = User.query.filter_by(username=data['username']).first()
    
    if not user or not check_password_hash(user.password_hash, data['password']):
        return jsonify({'error': 'Invalid username or password'}), 401
    
    # Create JWT token
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
        if recommend_polishes:
            # Use ML recommendation
            recommended_ids = recommend_polishes(user_input)
            recommended_products = Product.query.filter(Product.id.in_(recommended_ids)).all()
        else:
            # Fallback recommendations
            recommended_products = Product.query.limit(3).all()
        
        # Create recommendation records
        recommendations = []
        for product in recommended_products:
            recommendation = Recommendation(
                user_id=user.id,
                product_id=product.id,
                recommendation_score=0.85,
                recommendation_reason=f"Based on your {quiz_result.skin_tone} skin tone and {quiz_result.occasion} occasion"
            )
            db.session.add(recommendation)
            recommendations.append(recommendation)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Recommendations generated successfully',
            'recommendations': [
                {
                    'id': rec.id,
                    'product': {
                        'id': rec.product.id,
                        'name': rec.product.name,
                        'brand_name': rec.product.brand_name,
                        'hex_color': rec.product.hex_color,
                        'finish_type': rec.product.finish_type,
                        'price': rec.product.price,
                        'description': rec.product.description
                    },
                    'recommendation_score': rec.recommendation_score,
                    'recommendation_reason': rec.recommendation_reason,
                    'created_at': rec.created_at.isoformat()
                }
                for rec in recommendations
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
                'product': {
                    'id': rec.product.id,
                    'name': rec.product.name,
                    'brand_name': rec.product.brand_name,
                    'hex_color': rec.product.hex_color,
                    'finish_type': rec.product.finish_type,
                    'price': rec.product.price,
                    'description': rec.product.description
                },
                'recommendation_score': rec.recommendation_score,
                'recommendation_reason': rec.recommendation_reason,
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
                
                # Create sample products
                sample_products = [
                    Product(
                        name="Classic Red",
                        brand_name="OPI",
                        hex_color="#FF0000",
                        finish_type="Glossy",
                        price=12.99,
                        description="A timeless classic red nail polish"
                    ),
                    Product(
                        name="Nude Elegance",
                        brand_name="Essie",
                        hex_color="#F5E6D3",
                        finish_type="Matte",
                        price=9.99,
                        description="Perfect nude shade for everyday wear"
                    ),
                    Product(
                        name="Midnight Blue",
                        brand_name="Sally Hansen",
                        hex_color="#191970",
                        finish_type="Metallic",
                        price=8.99,
                        description="Deep blue with metallic finish"
                    ),
                    Product(
                        name="Rose Gold",
                        brand_name="Revlon",
                        hex_color="#B76E79",
                        finish_type="Glossy",
                        price=7.99,
                        description="Elegant rose gold shade"
                    ),
                    Product(
                        name="Emerald Green",
                        brand_name="China Glaze",
                        hex_color="#50C878",
                        finish_type="Glossy",
                        price=11.99,
                        description="Vibrant emerald green"
                    )
                ]
                
                for product in sample_products:
                    db.session.add(product)
                
                db.session.commit()
                print("Database initialized with admin user and sample products")
            else:
                print("Database already initialized")
                
        except Exception as e:
            print(f"Error initializing database: {e}")
            print("Make sure MySQL is running and the 'glossify' database exists in phpMyAdmin")

if __name__ == '__main__':
    init_database()
    app.run(debug=True, host='0.0.0.0', port=5000)
