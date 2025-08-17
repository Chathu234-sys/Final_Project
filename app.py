from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from datetime import datetime
import os

# ─── Import custom modules ───────────────────────────
from nailpolish_model import recommend_polishes
from admin_routes import admin_bp
from admin_models import db, User, NailPolish

# ─── App Setup ────────────────────────────────────────
app = Flask(__name__, instance_relative_config=True)
app.config.from_pyfile('config.py')

# ─── Init Extensions ──────────────────────────────────
db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

# ─── Register Blueprints ──────────────────────────────
app.register_blueprint(admin_bp, url_prefix='/admin')

# ─── User Loader ──────────────────────────────────────
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# ─── Routes ───────────────────────────────────────────
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/quiz')
def quiz():
    return render_template('quiz.html')

@app.route('/results', methods=['POST'])
def results():
    form = request.form
    user_input = {
        'age': int(form['age']),
        'skin_tone': form['skin_tone'],
        'finish_type': form['finish_type'],
        'occasion': form['occasion'],
        'outfit_color': form['outfit_color']
    }
    ids = recommend_polishes(user_input)
    recommendations = NailPolish.query.filter(NailPolish.id.in_(ids)).all()
    return render_template('results.html', recommendations=recommendations)

# ─── Auth: Sign Up ────────────────────────────────────
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "error")
            return redirect(url_for('signup'))
        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        flash("Account created! Please log in.", "success")
        return redirect(url_for('login'))
    return render_template('signup.html')

# ─── Auth: Login ──────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('home'))
        else:
            flash("Invalid credentials.", "error")
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Logged out successfully.", "info")
    return redirect(url_for('home'))

# ─── CLI Command: Create Tables ───────────────────────
@app.cli.command("init-db")
def init_db():
    db.create_all()
    print("✔️ Database initialized.")

# ─── Main ─────────────────────────────────────────────
if __name__ == '__main__':
    app.run(debug=True)
