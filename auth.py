from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User
import bcrypt as bc
import secrets

auth_bp = Blueprint('auth', __name__, template_folder='templates')


def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(32)
    return session['_csrf_token']


def validate_csrf(form_token):
    return form_token and form_token == session.get('_csrf_token')


@auth_bp.before_app_request
def inject_csrf():
    from flask import g
    g.csrf_token = generate_csrf_token()


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        return redirect(url_for('student.home'))

    if request.method == 'POST':
        if not validate_csrf(request.form.get('csrf_token')):
            flash('Invalid request. Please try again.', 'error')
            return redirect(url_for('auth.login'))

        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()
        if user and bc.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
            if not user.is_active:
                flash('Your account has been deactivated. Contact admin.', 'error')
                return redirect(url_for('auth.login'))
            login_user(user)
            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('student.home'))
        else:
            flash('Invalid email or password.', 'error')
            return redirect(url_for('auth.login'))

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('student.home'))

    if request.method == 'POST':
        if not validate_csrf(request.form.get('csrf_token')):
            flash('Invalid request. Please try again.', 'error')
            return redirect(url_for('auth.register'))

        name = request.form.get('name', '').strip()
        enrollment_number = request.form.get('enrollment_number', '').strip()
        engineering_branch = request.form.get('engineering_branch', '').strip()
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        VALID_BRANCHES = [
            'Civil Engineering', 'Mechanical Engineering', 'Electrical Engineering',
            'Computer Science and Engineering', 'Computer Engineering',
            'Chemical Engineering', 'IT Engineering', 'Other'
        ]

        # Validation
        if not name or not email or not password or not enrollment_number or not engineering_branch:
            flash('All fields are required.', 'error')
            return redirect(url_for('auth.register'))

        if engineering_branch not in VALID_BRANCHES:
            flash('Please select a valid Engineering Branch.', 'error')
            return redirect(url_for('auth.register'))

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return redirect(url_for('auth.register'))

        if not any(c.isdigit() for c in password):
            flash('Password must contain at least 1 number.', 'error')
            return redirect(url_for('auth.register'))

        if password != confirm:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(email=email).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('auth.register'))

        if User.query.filter_by(enrollment_number=enrollment_number).first():
            flash('Enrollment number already registered.', 'error')
            return redirect(url_for('auth.register'))

        hashed = bc.hashpw(password.encode('utf-8'), bc.gensalt(12)).decode('utf-8')
        user = User(
            name=name,
            enrollment_number=enrollment_number,
            engineering_branch=engineering_branch,
            email=email,
            password=hashed,
            role='student'
        )
        db.session.add(user)
        db.session.commit()

        flash('Registration successful! Please login.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('auth.login'))
