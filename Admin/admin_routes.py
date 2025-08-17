import os
from flask import Blueprint, render_template, redirect, url_for, request, flash, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from admin.forms import AdminLoginForm, PolishForm
from admin.models import db, User, NailPolish, QuizLog
from nailpolish_model import train_model

admin_bp = Blueprint('admin', __name__, template_folder='templates', static_folder='static')

# ─── Admin Login Page ─────────────────────────────
@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    form = AdminLoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            flash("Admin logged in successfully.", "success")
            return redirect(url_for('admin.dashboard'))
        flash("Invalid credentials", "danger")
    return render_template('admin_login.html', form=form)

# ─── Admin Dashboard ──────────────────────────────
@admin_bp.route('/dashboard')
@login_required
def dashboard():
    users = User.query.count()
    quizzes = QuizLog.query.count()
    products = NailPolish.query.count()
    return render_template('dashboard.html', users=users, quizzes=quizzes, products=products)

# ─── Manage Products ──────────────────────────────
@admin_bp.route('/manage-products', methods=['GET', 'POST'])
@login_required
def manage_products():
    form = PolishForm()
    if form.validate_on_submit():
        filename = None
        if form.image.data:
            filename = secure_filename(form.image.data.filename)
            image_path = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
            form.image.data.save(image_path)

        polish = NailPolish(
            name=form.name.data,
            brand=form.brand.data,
            hex=form.hex.data,
            image=os.path.join('images', filename) if filename else ""
        )
        db.session.add(polish)
        db.session.commit()
        flash("New polish added!", "success")
        return redirect(url_for('admin.manage_products'))

    polishes = NailPolish.query.all()
    return render_template('manage_products.html', form=form, polishes=polishes)

# ─── Retrain Model ────────────────────────────────
@admin_bp.route('/retrain-model', methods=['POST'])
@login_required
def retrain_model():
    loss = train_model()
    flash(f"Model retrained successfully. Final loss: {loss:.4f}", "info")
    return redirect(url_for('admin.dashboard'))

# ─── Delete Polish (Optional) ─────────────────────
@admin_bp.route('/delete-polish/<int:polish_id>', methods=['POST'])
@login_required
def delete_polish(polish_id):
    polish = NailPolish.query.get_or_404(polish_id)
    db.session.delete(polish)
    db.session.commit()
    flash("Polish deleted.", "warning")
    return redirect(url_for('admin.manage_products'))
