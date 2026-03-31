from flask import Flask, redirect, render_template, request
from flask_login import LoginManager, current_user
from models import db, User
import os
from dotenv import load_dotenv

load_dotenv()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'ddcet-change-this-in-production')

    db_uri = os.getenv('DATABASE_URL', 'sqlite:///ddcet.db')
    if db_uri.startswith("postgres://"):
        db_uri = db_uri.replace("postgres://", "postgresql://", 1)
    # Remove pgbouncer param — psycopg2 doesn't support it in URL
    if "pgbouncer=true" in db_uri:
        db_uri = db_uri.replace("?pgbouncer=true", "").replace("&pgbouncer=true", "")

    app.config['SQLALCHEMY_DATABASE_URI'] = db_uri
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
    app.config['UPLOAD_FOLDER'] = 'uploads'

    # ── Supabase Nano connection pool settings ──
    # Supabase Nano: pool_size=20, max_client=200
    # We use transaction mode pooling (port 6543) so keep pool small
    # gunicorn 4 workers x 4 threads = 16 threads max
    # Each thread holds 1 connection → stay well under 20
    app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
        'pool_size': 5,           # 5 base connections per worker (4 workers = 20 total → matches Supabase limit)
        'max_overflow': 2,        # small overflow buffer
        'pool_timeout': 10,       # fail fast if no connection available (don't queue up)
        'pool_recycle': 300,      # recycle every 5 min (Supabase drops idle after 5 min)
        'pool_pre_ping': True,    # test connection before use — prevents "connection closed" errors
    }

    db.init_app(app)

    lm = LoginManager(app)
    lm.login_view = 'auth.login'
    lm.login_message_category = 'warning'

    @lm.user_loader
    def load_user(uid):
        return User.query.get(int(uid))

    # ── IST timezone filter for all templates ──
    from datetime import timezone, timedelta
    IST = timezone(timedelta(hours=5, minutes=30))

    @app.template_filter('ist')
    def to_ist(dt):
        if dt is None:
            return ''
        try:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(IST).strftime('%Y-%m-%d %H:%M')
        except Exception:
            return str(dt)

    @app.template_filter('from_json')
    def from_json(value):
        import json
        if not value: return []
        if isinstance(value, list): return value
        try:
            parsed = json.loads(value)
            if isinstance(parsed, str):
                parsed = json.loads(parsed)
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
        return []

    @app.template_filter('ist_time')
    def to_ist_time(dt):
        if dt is None:
            return ''
        try:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(IST).strftime('%H:%M:%S')
        except Exception:
            return ''

    from auth import auth_bp
    from admin import admin_bp
    from student import student_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(student_bp, url_prefix='/student')

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect('/admin/dashboard' if current_user.role == 'admin' else '/student/home')
        
        from models import User, Question, TestAttempt
        stats = {
            'students': User.query.filter_by(role='student').count(),
            'questions': Question.query.count(),
            'attempts': TestAttempt.query.count()
        }
        return render_template('landing.html', stats=stats)

    @app.route('/contact', methods=['GET', 'POST'])
    def contact():
        if request.method == 'POST':
            from auth import send_email, validate_csrf
            if not validate_csrf(request.form.get('csrf_token')):
                from flask import flash as fl
                fl('Invalid request. Please try again.', 'error')
                return redirect('/contact')

            name = request.form.get('name', '').strip()
            email = request.form.get('email', '').strip()
            subject = request.form.get('subject', '').strip()
            message = request.form.get('message', '').strip()

            if not all([name, email, subject, message]):
                from flask import flash as fl
                fl('All fields are required.', 'error')
                return redirect('/contact')

            admin_email = os.getenv('CONTACT_EMAIL', 'aryamanjoshi23@gmail.com')
            html_body = f"""
            <div style="font-family:Inter,sans-serif;max-width:560px;margin:0 auto;padding:24px">
                <h2 style="color:#6366f1">📬 New Contact Message</h2>
                <table style="width:100%;border-collapse:collapse">
                    <tr><td style="padding:8px;font-weight:600;color:#64748b">Name</td><td style="padding:8px">{name}</td></tr>
                    <tr><td style="padding:8px;font-weight:600;color:#64748b">Email</td><td style="padding:8px"><a href="mailto:{email}">{email}</a></td></tr>
                    <tr><td style="padding:8px;font-weight:600;color:#64748b">Subject</td><td style="padding:8px">{subject}</td></tr>
                </table>
                <div style="background:#f8fafc;padding:16px;border-radius:8px;margin-top:16px">
                    <p style="margin:0;white-space:pre-wrap">{message}</p>
                </div>
            </div>
            """
            sent = send_email(admin_email, f'DDCET Contact: {subject}', html_body)
            from flask import flash as fl
            if sent:
                fl('Message sent successfully! We\'ll get back to you soon.', 'success')
            else:
                fl('Message could not be sent. Please try again later or email us directly.', 'error')

            return redirect('/contact')

        return render_template('contact.html')

    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(413)
    def too_large(e):
        from flask import flash
        flash('File is too large. Maximum size is 5MB.', 'error')
        return redirect(request.referrer or '/'), 302

    @app.errorhandler(500)
    def server_error(e):
        db.session.rollback()  # prevent transaction lock-up under load
        return render_template('errors/500.html'), 500

    try:
        with app.app_context():
            os.makedirs('uploads', exist_ok=True)
            db.create_all()
            # Seed default admin if none exists
            if not User.query.filter_by(role='admin').first():
                import bcrypt as bc
                import secrets as _secrets
                default_pw = os.getenv('ADMIN_DEFAULT_PASSWORD') or _secrets.token_urlsafe(12)
                hashed = bc.hashpw(default_pw.encode(), bc.gensalt(12)).decode()
                db.session.add(User(
                    name='Administrator',
                    email='admin@ddcet.local',
                    enrollment_number='ADMIN-001',
                    engineering_branch='Other',
                    password=hashed,
                    role='admin'
                ))
                db.session.commit()
                if os.getenv('ADMIN_DEFAULT_PASSWORD'):
                    print("✅ Default admin created (password from env var)")
                else:
                    print(f"✅ Default admin created: admin@ddcet.local / {default_pw}")
                    print("⚠️  Set ADMIN_DEFAULT_PASSWORD env var in production!")
    except Exception as e:
        print(f"⚠️  Database initialization skipped during startup: {e}")
        print("⚠️  The app will still start. Admin user can be seeded on next restart once the database is ready.")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=False)  # NEVER run debug=True in production
