from flask import Flask, redirect, render_template, request
from flask_login import LoginManager, current_user
from models import db, User
import os

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'ddcet-change-this-in-production'
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///ddcet.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
    app.config['UPLOAD_FOLDER'] = 'uploads'

    db.init_app(app)

    lm = LoginManager(app)
    lm.login_view = 'auth.login'
    lm.login_message_category = 'warning'

    @lm.user_loader
    def load_user(uid):
        return User.query.get(int(uid))

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

    with app.app_context():
        os.makedirs('uploads', exist_ok=True)
        db.create_all()
        # Seed default admin if none exists
        if not User.query.filter_by(role='admin').first():
            import bcrypt as bc
            hashed = bc.hashpw(b'Admin@1234', bc.gensalt(12)).decode()
            db.session.add(User(
                name='Administrator',
                email='admin@ddcet.local',
                enrollment_number='ADMIN-001',
                engineering_branch='Other',
                password=hashed,
                role='admin'
            ))
            db.session.commit()
            print("✅ Default admin created: admin@ddcet.local / Admin@1234")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
