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
        return redirect('/auth/login')

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

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=False)  # NEVER run debug=True in production
