from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime, timezone

db = SQLAlchemy()


class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    enrollment_number = db.Column(db.String(50), unique=True, nullable=False)
    engineering_branch = db.Column(db.String(100), nullable=False, default='Other')
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default='student')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_active_user = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime, nullable=True)

    @property
    def is_active(self):
        return self.is_active_user


class QuestionBank(db.Model):
    __tablename__ = 'question_banks'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, default='')
    year = db.Column(db.Integer, nullable=True)
    section = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    question_count = db.Column(db.Integer, default=0)

    questions = db.relationship('Question', backref='bank', lazy='dynamic',
                                cascade='all, delete-orphan')
    creator = db.relationship('User', foreign_keys=[created_by])


class Question(db.Model):
    __tablename__ = 'questions'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    bank_id = db.Column(db.Integer, db.ForeignKey('question_banks.id', ondelete='CASCADE'), nullable=False)
    qno = db.Column(db.Integer, default=0)
    section = db.Column(db.Integer, default=1)
    topic = db.Column(db.String(100), default='General')
    question = db.Column(db.Text, nullable=False)
    option_a = db.Column(db.Text, nullable=False)
    option_b = db.Column(db.Text, nullable=False)
    option_c = db.Column(db.Text, nullable=False)
    option_d = db.Column(db.Text, nullable=False)
    correct_ans = db.Column(db.String(1), nullable=False)
    explanation = db.Column(db.Text, default='')
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))


class ExamConfig(db.Model):
    __tablename__ = 'exam_configs'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(150), nullable=False)
    mode = db.Column(db.String(20), default='exam')
    bank_ids = db.Column(db.Text, nullable=False, default='[]')
    total_questions = db.Column(db.Integer, default=100)
    duration_minutes = db.Column(db.Integer, default=150)
    marks_correct = db.Column(db.Float, default=2.0)
    marks_wrong = db.Column(db.Float, default=0.5)
    section_filter = db.Column(db.Integer, default=0)
    topic_filter = db.Column(db.Text, default='')
    is_active = db.Column(db.Boolean, default=True)
    allow_reattempt = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'))
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    end_date = db.Column(db.DateTime, nullable=True)

    creator = db.relationship('User', foreign_keys=[created_by])


class TestAttempt(db.Model):
    __tablename__ = 'test_attempts'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    config_id = db.Column(db.Integer, db.ForeignKey('exam_configs.id'), nullable=False)
    mode = db.Column(db.String(20), default='exam')
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    submitted_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), default='in_progress')
    score = db.Column(db.Float, default=0)
    max_score = db.Column(db.Float, default=0)
    percentage = db.Column(db.Float, default=0)
    correct_count = db.Column(db.Integer, default=0)
    wrong_count = db.Column(db.Integer, default=0)
    unattempted = db.Column(db.Integer, default=0)
    bonus_count = db.Column(db.Integer, default=0)
    time_taken_sec = db.Column(db.Integer, default=0)
    questions_json = db.Column(db.Text, default='[]')
    fs_exit_count = db.Column(db.Integer, default=0)
    tab_switch_count = db.Column(db.Integer, default=0)

    user = db.relationship('User', foreign_keys=[user_id])
    config = db.relationship('ExamConfig', foreign_keys=[config_id])


class PracticeSession(db.Model):
    __tablename__ = 'practice_sessions'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    config_id = db.Column(db.Integer, db.ForeignKey('exam_configs.id'), nullable=False)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_active_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    total_answered = db.Column(db.Integer, default=0)
    total_correct = db.Column(db.Integer, default=0)
    questions_seen = db.Column(db.Text, default='[]')
    status = db.Column(db.String(20), default='active')

    user = db.relationship('User', foreign_keys=[user_id])
    config = db.relationship('ExamConfig', foreign_keys=[config_id])


class AdminLog(db.Model):
    __tablename__ = 'admin_logs'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    admin_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(200), nullable=False)
    detail = db.Column(db.Text, default='')
    timestamp = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    admin = db.relationship('User', foreign_keys=[admin_id])
    affected_user = db.relationship('User', foreign_keys=[user_id])


class BookmarkedQuestion(db.Model):
    __tablename__ = 'bookmarked_questions'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id', ondelete='CASCADE'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    
    __table_args__ = (db.UniqueConstraint('user_id', 'question_id'),)
    
    user = db.relationship('User', foreign_keys=[user_id])
    question = db.relationship('Question', foreign_keys=[question_id])

