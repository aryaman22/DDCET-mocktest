from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from models import db, User, TestAttempt, ExamConfig, Question
from utils import calculate_exam_score
from datetime import datetime, timezone
import bcrypt as bc
import secrets
import json

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
    # Auto-submit any in-progress exam attempts
    in_progress = TestAttempt.query.filter_by(
        user_id=current_user.id,
        status='in_progress',
        mode='exam'
    ).all()

    for attempt in in_progress:
        config = ExamConfig.query.get(attempt.config_id)
        q_data = json.loads(attempt.questions_json) if attempt.questions_json else []
        q_ids = [qd['q_id'] for qd in q_data]
        questions_from_db = Question.query.filter(Question.id.in_(q_ids)).all()
        questions_map = {q.id: q for q in questions_from_db}

        # Build answers dict for scoring
        user_answers = {}
        questions_for_scoring = []
        for qd in q_data:
            q = questions_map.get(qd['q_id'])
            if q:
                questions_for_scoring.append(q)
                if qd.get('given_answer'):
                    user_answers[str(q.id)] = qd['given_answer']

        if config:
            result = calculate_exam_score(questions_for_scoring, user_answers, config)

            # Update marks in q_data
            for qd in q_data:
                q = questions_map.get(qd['q_id'])
                if q:
                    given = user_answers.get(str(q.id), 'E')
                    if q.correct_ans == 'X':
                        qd['marks'] = config.marks_correct
                    elif given in ['E', '', 'SKIP']:
                        qd['marks'] = 0
                    elif given == q.correct_ans:
                        qd['marks'] = config.marks_correct
                    else:
                        qd['marks'] = -config.marks_wrong

            attempt.questions_json = json.dumps(q_data)
            attempt.score = result['marks']
            attempt.max_score = result['max_score']
            attempt.percentage = result['percentage']
            attempt.correct_count = result['correct']
            attempt.wrong_count = result['wrong']
            attempt.unattempted = result['unattempted']
            attempt.bonus_count = result['bonus']

        attempt.status = 'timeout'
        attempt.submitted_at = datetime.now(timezone.utc)
        if attempt.started_at:
            attempt.time_taken_sec = int((datetime.now(timezone.utc) - attempt.started_at).total_seconds())

    if in_progress:
        db.session.commit()
        flash('Your in-progress exam has been auto-submitted.', 'warning')

    logout_user()
    flash('Logged out successfully.', 'success')
    return redirect(url_for('auth.login'))

