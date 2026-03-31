from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User
from datetime import datetime, timezone
import bcrypt as bc
import secrets
import re
import time
from collections import defaultdict
from threading import Lock

auth_bp = Blueprint('auth', __name__, template_folder='templates')

# FIX 7: Input Validation Logic
EMAIL_RE = re.compile(r'^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$')
NAME_RE = re.compile(r'^[a-zA-Z\s]{2,100}$')
ENROLL_RE = re.compile(r'^[a-zA-Z0-9\-]{3,20}$')

def validate_email(email): return bool(EMAIL_RE.match(email))
def validate_name(name): return bool(NAME_RE.match(name.strip()))
def validate_enrollment(enr): return bool(ENROLL_RE.match(enr.strip()))

# FIX 3: Login brute-force protection
_login_attempts = defaultdict(list)  # {ip: [timestamps]}
_lock = Lock()
MAX_ATTEMPTS = 5
WINDOW = 300    # 5 min
LOCKOUT = 600   # 10 min

def check_rate_limit(ip):
    now = time.time()
    with _lock:
        _login_attempts[ip] = [t for t in _login_attempts[ip] if now - t < LOCKOUT]
        if len(_login_attempts[ip]) >= MAX_ATTEMPTS:
            wait = int(LOCKOUT - (now - _login_attempts[ip][0]))
            return False, wait
        return True, 0

def record_fail(ip):
    with _lock:
        _login_attempts[ip].append(time.time())

def clear_attempts(ip):
    with _lock:
        _login_attempts[ip] = []

def get_real_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()


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
        ip = get_real_ip()
        allowed, wait_sec = check_rate_limit(ip)
        
        if not allowed:
            mins, secs = divmod(wait_sec, 60)
            flash(f'Too many failed attempts. Try again in {mins}m {secs}s.', 'error')
            return redirect(url_for('auth.login'))

        if not validate_csrf(request.form.get('csrf_token')):
            flash('Invalid request. Please try again.', 'error')
            return redirect(url_for('auth.login'))

        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()
        if user and bc.checkpw(password.encode('utf-8'), user.password.encode('utf-8')):
            if not user.is_active_user:  # FIX: was user.is_active (wrong column name)
                flash('Your account has been deactivated. Contact admin.', 'error')
                return redirect(url_for('auth.login'))
            
            clear_attempts(ip)
            
            # Update last_login
            user.last_login = datetime.now(timezone.utc)
            db.session.commit()
            
            login_user(user)
            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            return redirect(url_for('student.home'))
        else:
            record_fail(ip)
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

        if not validate_name(name):
            flash('Name must be 2-100 characters and contain only letters and spaces.', 'error')
            return redirect(url_for('auth.register'))

        if not validate_email(email):
            flash('Please enter a valid email address.', 'error')
            return redirect(url_for('auth.register'))

        if not validate_enrollment(enrollment_number):
            flash('Enrollment Number must be alphanumeric (dashes allowed) and 3-20 characters long.', 'error')
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


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        if not validate_csrf(request.form.get('csrf_token')):
            flash('Invalid request. Please try again.', 'error')
            return redirect(url_for('auth.profile'))

        action = request.form.get('action', 'update_info')

        if action == 'update_info':
            name = request.form.get('name', '').strip()
            engineering_branch = request.form.get('engineering_branch', '').strip()

            VALID_BRANCHES = [
                'Civil Engineering', 'Mechanical Engineering', 'Electrical Engineering',
                'Computer Science and Engineering', 'Computer Engineering',
                'Chemical Engineering', 'IT Engineering', 'Other'
            ]

            if not name:
                flash('Name cannot be empty.', 'error')
                return redirect(url_for('auth.profile'))
                
            if not validate_name(name):
                flash('Name must be 2-100 characters and contain only letters and spaces.', 'error')
                return redirect(url_for('auth.profile'))

            if engineering_branch and engineering_branch not in VALID_BRANCHES:
                flash('Please select a valid engineering branch.', 'error')
                return redirect(url_for('auth.profile'))

            current_user.name = name
            if engineering_branch:
                current_user.engineering_branch = engineering_branch
            db.session.commit()
            flash('Profile updated successfully!', 'success')

        elif action == 'change_password':
            current_password = request.form.get('current_password', '')
            new_password = request.form.get('new_password', '')
            confirm_password = request.form.get('confirm_password', '')

            if not bc.checkpw(current_password.encode('utf-8'), current_user.password.encode('utf-8')):
                flash('Current password is incorrect.', 'error')
                return redirect(url_for('auth.profile'))

            if len(new_password) < 8:
                flash('New password must be at least 8 characters.', 'error')
                return redirect(url_for('auth.profile'))

            if not any(c.isdigit() for c in new_password):
                flash('New password must contain at least 1 number.', 'error')
                return redirect(url_for('auth.profile'))

            if new_password != confirm_password:
                flash('New passwords do not match.', 'error')
                return redirect(url_for('auth.profile'))

            current_user.password = bc.hashpw(new_password.encode('utf-8'), bc.gensalt(12)).decode('utf-8')
            db.session.commit()
            flash('Password changed successfully!', 'success')

        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html')


# ── Email Helper ──────────────────────────────────────
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

def send_email(to_email, subject, html_body):
    """Send email using Gmail SMTP. Returns True on success."""
    smtp_email = os.getenv('SMTP_EMAIL', '')
    smtp_password = os.getenv('SMTP_APP_PASSWORD', '')
    if not smtp_email or not smtp_password:
        return False

    msg = MIMEMultipart('alternative')
    msg['From'] = f'DDCET Portal <{smtp_email}>'
    msg['To'] = to_email
    msg['Subject'] = subject
    msg.attach(MIMEText(html_body, 'html'))

    try:
        with smtplib.SMTP('smtp.gmail.com', 587) as server:
            server.starttls()
            server.login(smtp_email, smtp_password)
            server.send_message(msg)
        return True
    except Exception as e:
        print(f'Email send failed: {e}')
        return False


# ── Forgot Password ──────────────────────────────────
_reset_tokens = {}  # {token: {'email': str, 'expires': float}}

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('student.home'))

    if request.method == 'POST':
        if not validate_csrf(request.form.get('csrf_token')):
            flash('Invalid request. Please try again.', 'error')
            return redirect(url_for('auth.forgot_password'))

        email = request.form.get('email', '').strip().lower()
        # Always show success to prevent email enumeration
        flash('If this email is registered, a password reset link has been sent.', 'success')

        user = User.query.filter_by(email=email).first()
        if user:
            token = secrets.token_urlsafe(32)
            _reset_tokens[token] = {
                'email': email,
                'expires': time.time() + 900  # 15 minutes
            }
            # Clean up expired tokens
            now = time.time()
            expired = [t for t, d in _reset_tokens.items() if d['expires'] < now]
            for t in expired:
                del _reset_tokens[t]

            reset_url = request.host_url.rstrip('/') + url_for('auth.reset_password', token=token)
            html_body = f"""
            <div style="font-family:Inter,sans-serif;max-width:500px;margin:0 auto;padding:24px">
                <h2 style="color:#6366f1">🔑 DDCET Password Reset</h2>
                <p>Hi <strong>{user.name}</strong>,</p>
                <p>You requested a password reset. Click the button below to set a new password:</p>
                <div style="text-align:center;margin:24px 0">
                    <a href="{reset_url}" style="background:#6366f1;color:#fff;padding:12px 32px;border-radius:8px;text-decoration:none;font-weight:600;display:inline-block">Reset Password</a>
                </div>
                <p style="color:#64748b;font-size:14px">This link expires in 15 minutes. If you didn't request this, ignore this email.</p>
            </div>
            """
            send_email(email, 'DDCET Portal — Password Reset', html_body)

        return redirect(url_for('auth.forgot_password'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    data = _reset_tokens.get(token)
    if not data or data['expires'] < time.time():
        flash('This reset link has expired or is invalid.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password', '')
        confirm = request.form.get('confirm_password', '')

        if len(password) < 8:
            flash('Password must be at least 8 characters.', 'error')
            return redirect(url_for('auth.reset_password', token=token))

        if not any(c.isdigit() for c in password):
            flash('Password must contain at least 1 number.', 'error')
            return redirect(url_for('auth.reset_password', token=token))

        if password != confirm:
            flash('Passwords do not match.', 'error')
            return redirect(url_for('auth.reset_password', token=token))

        user = User.query.filter_by(email=data['email']).first()
        if user:
            user.password = bc.hashpw(password.encode('utf-8'), bc.gensalt(12)).decode('utf-8')
            db.session.commit()
            del _reset_tokens[token]
            flash('Password has been reset successfully! Please login.', 'success')
            return redirect(url_for('auth.login'))

        flash('User not found.', 'error')
        return redirect(url_for('auth.forgot_password'))

    return render_template('auth/reset_password.html', token=token)