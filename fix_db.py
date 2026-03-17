from app import create_app
from models import db
from sqlalchemy import text
app = create_app()

with app.app_context():
    try:
        db.session.execute(text("ALTER TABLE test_attempts ALTER COLUMN id RESTART WITH 10000;"))
        db.session.execute(text("ALTER TABLE practice_sessions ALTER COLUMN id RESTART WITH 10000;"))
        db.session.commit()
        print("✅ Identity columns restarted at 10000")
    except Exception as e:
        print("Error:", e)
