#!/usr/bin/env python3
"""
Database setup script for Glossify MySQL database
"""

import pymysql
from sqlalchemy import create_engine, text
import os

def create_database():
    """Create the glossify database if it doesn't exist"""
    try:
        # Connect to MySQL server (without specifying database)
        connection = pymysql.connect(
            host='localhost',
            user='root',
            password='',  # Default XAMPP MySQL has no password
            charset='utf8mb4'
        )
        
        cursor = connection.cursor()
        
        # Create database if it doesn't exist
        cursor.execute("CREATE DATABASE IF NOT EXISTS glossify CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        print("✅ Database 'glossify' created successfully!")
        
        cursor.close()
        connection.close()
        
    except Exception as e:
        print(f"❌ Error creating database: {e}")
        print("Make sure MySQL is running in XAMPP and accessible")

def test_connection():
    """Test the database connection"""
    try:
        # Test connection to the glossify database
        connection = pymysql.connect(
            host='localhost',
            user='root',
            password='',
            database='glossify',
            charset='utf8mb4'
        )
        
        cursor = connection.cursor()
        cursor.execute("SELECT VERSION()")
        version = cursor.fetchone()
        print(f"✅ Connected to MySQL database successfully!")
        print(f"   MySQL Version: {version[0]}")
        
        cursor.close()
        connection.close()
        return True
        
    except Exception as e:
        print(f"❌ Error connecting to database: {e}")
        return False

def create_tables():
    """Create the required tables using SQLAlchemy"""
    try:
        # Import Flask app and models
        from flask import Flask
        from flask_sqlalchemy import SQLAlchemy
        from flask_login import UserMixin
        from datetime import datetime
        from werkzeug.security import generate_password_hash
        
        # Create a minimal Flask app for database setup
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/glossify'
        app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        
        db = SQLAlchemy(app)
        
        # Define models
        class User(UserMixin, db.Model):
            __tablename__ = "users"
            
            id = db.Column(db.Integer, primary_key=True, index=True)
            username = db.Column(db.String(50), unique=True, index=True, nullable=False)
            email = db.Column(db.String(100), unique=True, index=True, nullable=False)
            password_hash = db.Column(db.String(255), nullable=False)
            is_admin = db.Column(db.Boolean, default=False)
            created_at = db.Column(db.DateTime, default=datetime.utcnow)
            updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

        class Product(db.Model):
            __tablename__ = "products"
            
            id = db.Column(db.Integer, primary_key=True, index=True)
            name = db.Column(db.String(100), nullable=False)
            brand_name = db.Column(db.String(100), nullable=False)
            hex_color = db.Column(db.String(7), nullable=False)
            finish_type = db.Column(db.String(50), nullable=False)
            price = db.Column(db.Float, nullable=True)
            description = db.Column(db.Text, nullable=True)
            image_url = db.Column(db.String(255), nullable=True)
            created_at = db.Column(db.DateTime, default=datetime.utcnow)

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

        class NailShapeImage(db.Model):
            __tablename__ = "nailshapeimages"
            
            id = db.Column(db.Integer, primary_key=True, index=True)
            user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
            image_path = db.Column(db.String(255), nullable=False)
            predicted_shape = db.Column(db.String(50), nullable=True)
            confidence_score = db.Column(db.Float, nullable=True)
            uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

        class Recommendation(db.Model):
            __tablename__ = "recommendations"
            
            id = db.Column(db.Integer, primary_key=True, index=True)
            user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
            product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
            recommendation_score = db.Column(db.Float, nullable=True)
            recommendation_reason = db.Column(db.Text, nullable=True)
            created_at = db.Column(db.DateTime, default=datetime.utcnow)
        
        with app.app_context():
            # Create all tables
            db.create_all()
            print("✅ All tables created successfully!")
            
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
                
                
                
                
                for product in sample_products:
                    db.session.add(product)
                
                db.session.commit()
                print("✅ Admin user and sample products created!")
            else:
                print("✅ Admin user already exists")
                
    except Exception as e:
        print(f"❌ Error creating tables: {e}")

def main():
    """Main setup function"""
    print("🚀 Setting up Glossify MySQL Database...")
    print("=" * 50)
    
    # Step 1: Create database
    print("\n1. Creating database...")
    create_database()
    
    # Step 2: Test connection
    print("\n2. Testing connection...")
    if test_connection():
        # Step 3: Create tables
        print("\n3. Creating tables...")
        create_tables()
        
        print("\n" + "=" * 50)
        print("✅ Database setup completed successfully!")
        print("\n📋 Next steps:")
        print("1. Make sure XAMPP MySQL is running")
        print("2. Run: python app.py")
        print("3. Access the application at: http://localhost:5000")
        print("4. Admin login: username=admin, password=admin123")
    else:
        print("\n❌ Database setup failed. Please check your MySQL connection.")

if __name__ == "__main__":
    main()
