from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

# Initialize SQLAlchemy (called from app.py)
db = SQLAlchemy()

# ─── User Model ───────────────────────────────────────
class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

# ─── Nail Polish Product Model ─────────────────────────
class NailPolish(db.Model):
    __tablename__ = 'nail_polishes'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    brand = db.Column(db.String(100), nullable=False)
    hex = db.Column(db.String(7), nullable=False)  # e.g., #F2AEBB
    image = db.Column(db.String(255), nullable=False)

# ─── Quiz Log (Optional - for analytics) ──────────────
class QuizLog(db.Model):
    __tablename__ = 'quiz_logs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'))
    age = db.Column(db.Integer)
    skin_tone = db.Column(db.String(50))
    finish_type = db.Column(db.String(50))
    occasion = db.Column(db.String(50))
    outfit_color = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, server_default=db.func.now())
