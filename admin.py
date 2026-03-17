from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort, Response, send_file
from flask_login import login_required, current_user
from models import db, User, QuestionBank, Question, ExamConfig, TestAttempt, PracticeSession, AdminLog
from utils import parse_csv_questions, parse_json_questions, parse_excel_questions, generate_sample_csv
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta, timezone
import json
import os
import io
import csv

admin_bp = Blueprint('admin', __name__, template_folder='templates')


def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            abort(403)
        return f(*args, **kwargs)
    return decorated


def log_action(action, detail='', user_id=None):
    entry = AdminLog(
        admin_id=current_user.id if current_user.is_authenticated else None,
        user_id=user_id,
        action=action,
        detail=detail
    )
    db.session.add(entry)
    db.session.commit()


# ── Dashboard ──────────────────────────────────────────
@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    total_questions = Question.query.count()
    active_banks = QuestionBank.query.filter_by(is_active=True).count()
    active_exam_configs = ExamConfig.query.filter_by(is_active=True, mode='exam').count()
    active_practice_configs = ExamConfig.query.filter_by(is_active=True, mode='practice').count()
    total_students = User.query.filter_by(role='student').count()

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    attempts_today = TestAttempt.query.filter(TestAttempt.started_at >= today_start).count()

    # Pass rate
    submitted_attempts = TestAttempt.query.filter(
        TestAttempt.status.in_(['submitted', 'timeout']),
        TestAttempt.mode == 'exam'
    ).all()
    pass_count = sum(1 for a in submitted_attempts if a.percentage and a.percentage >= 50)
    pass_rate = round(pass_count / len(submitted_attempts) * 100, 1) if submitted_attempts else 0

    last_attempts = TestAttempt.query.order_by(TestAttempt.started_at.desc()).limit(10).all()

    return render_template('admin/dashboard.html',
                           total_questions=total_questions,
                           active_banks=active_banks,
                           active_exam_configs=active_exam_configs,
                           active_practice_configs=active_practice_configs,
                           total_students=total_students,
                           attempts_today=attempts_today,
                           pass_rate=pass_rate,
                           last_attempts=last_attempts)


# ── Question Banks ──────────────────────────────────────
@admin_bp.route('/banks')
@login_required
@admin_required
def banks():
    bank_list = QuestionBank.query.order_by(QuestionBank.created_at.desc()).all()
    return render_template('admin/banks.html', banks=bank_list)


@admin_bp.route('/banks/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_bank():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        year = request.form.get('year', '')
        section = request.form.get('section', '0')
        is_active = request.form.get('is_active') == 'on'

        if not name:
            flash('Bank name is required.', 'error')
            return redirect(url_for('admin.create_bank'))

        bank = QuestionBank(
            name=name,
            description=description,
            year=int(year) if year and year.isdigit() else None,
            section=int(section) if section.isdigit() else 0,
            is_active=is_active,
            created_by=current_user.id
        )
        db.session.add(bank)
        db.session.commit()
        log_action('Created question bank', f'Bank: {name} (ID: {bank.id})')
        flash(f'Question bank "{name}" created successfully.', 'success')
        return redirect(url_for('admin.banks'))

    return render_template('admin/bank_detail.html', bank=None, mode='create')


@admin_bp.route('/banks/<int:bank_id>/questions')
@login_required
@admin_required
def bank_questions(bank_id):
    bank = QuestionBank.query.get_or_404(bank_id)
    page = request.args.get('page', 1, type=int)
    section_f = request.args.get('section', '', type=str)
    topic_f = request.args.get('topic', '', type=str)
    search_q = request.args.get('q', '', type=str)

    query = Question.query.filter_by(bank_id=bank_id)

    if section_f and section_f.isdigit() and int(section_f) in [1, 2]:
        query = query.filter_by(section=int(section_f))
    if topic_f:
        query = query.filter_by(topic=topic_f)
    if search_q:
        query = query.filter(Question.question.ilike(f'%{search_q}%'))

    pagination = query.order_by(Question.qno).paginate(page=page, per_page=50, error_out=False)
    questions = pagination.items

    # Get distinct topics for filter
    topics = db.session.query(Question.topic).filter_by(bank_id=bank_id).distinct().order_by(Question.topic).all()
    topics = [t[0] for t in topics if t[0]]

    # Stats
    total = Question.query.filter_by(bank_id=bank_id).count()
    sec1 = Question.query.filter_by(bank_id=bank_id, section=1).count()
    sec2 = Question.query.filter_by(bank_id=bank_id, section=2).count()

    return render_template('admin/bank_detail.html', bank=bank, mode='questions',
                           questions=questions, pagination=pagination, topics=topics,
                           section_f=section_f, topic_f=topic_f, search_q=search_q,
                           total=total, sec1=sec1, sec2=sec2, unique_topics=len(topics))


# ── Upload Questions ──────────────────────────────────────
@admin_bp.route('/banks/<int:bank_id>/upload', methods=['GET', 'POST'])
@login_required
@admin_required
def upload_questions(bank_id):
    bank = QuestionBank.query.get_or_404(bank_id)

    if request.method == 'POST':
        file = request.files.get('file')
        if not file or file.filename == '':
            flash('No file selected.', 'error')
            return redirect(url_for('admin.upload_questions', bank_id=bank_id))

        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
        if ext not in ['csv', 'json', 'xlsx']:
            flash('Only CSV, JSON, and Excel (.xlsx) files are accepted.', 'error')
            return redirect(url_for('admin.upload_questions', bank_id=bank_id))

        upload_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
        os.makedirs(upload_dir, exist_ok=True)
        filepath = os.path.join(upload_dir, filename)
        file.save(filepath)

        try:
            if ext == 'csv':
                questions, warnings = parse_csv_questions(filepath, bank_id)
            elif ext == 'json':
                questions, warnings = parse_json_questions(filepath, bank_id)
            else:
                questions, warnings = parse_excel_questions(filepath, bank_id)

            if questions:
                db.session.add_all(questions)
                db.session.commit()
                # Update question count
                bank.question_count = Question.query.filter_by(bank_id=bank_id).count()
                db.session.commit()

            log_action('Uploaded questions', f'Bank: {bank.name}, Imported: {len(questions)}, Skipped: {len(warnings)}')

            if warnings:
                flash(f'{len(questions)} questions imported, {len(warnings)} skipped.', 'warning')
                for w in warnings[:10]:
                    flash(w, 'warning')
            else:
                flash(f'{len(questions)} questions imported successfully!', 'success')
        except Exception as e:
            flash(f'Error processing file: {str(e)}', 'error')

        # Clean up uploaded file
        try:
            os.remove(filepath)
        except OSError:
            pass

        return redirect(url_for('admin.bank_questions', bank_id=bank_id))

    return render_template('admin/upload.html', bank=bank)


@admin_bp.route('/banks/sample.csv')
@login_required
@admin_required
def sample_csv():
    csv_content = generate_sample_csv()
    return Response(
        csv_content,
        mimetype='text/csv',
        headers={'Content-Disposition': 'attachment; filename=sample_questions.csv'}
    )


# ── Manual Add/Edit/Delete Questions ──────────────────────
@admin_bp.route('/banks/<int:bank_id>/add', methods=['GET', 'POST'])
@login_required
@admin_required
def add_question(bank_id):
    bank = QuestionBank.query.get_or_404(bank_id)

    if request.method == 'POST':
        q = Question(
            bank_id=bank_id,
            qno=int(request.form.get('qno', 0)) if request.form.get('qno', '').isdigit() else 0,
            section=int(request.form.get('section', 1)),
            topic=request.form.get('topic', 'General').strip() or 'General',
            question=request.form.get('question', '').strip(),
            option_a=request.form.get('option_a', '').strip(),
            option_b=request.form.get('option_b', '').strip(),
            option_c=request.form.get('option_c', '').strip(),
            option_d=request.form.get('option_d', '').strip(),
            correct_ans=request.form.get('correct_ans', 'A').strip().upper(),
            explanation=request.form.get('explanation', '').strip()
        )
        if not q.question or not all([q.option_a, q.option_b, q.option_c, q.option_d]):
            flash('Question and all options are required.', 'error')
            return redirect(url_for('admin.add_question', bank_id=bank_id))

        db.session.add(q)
        db.session.commit()
        bank.question_count = Question.query.filter_by(bank_id=bank_id).count()
        db.session.commit()
        log_action('Added question manually', f'Bank: {bank.name}, Q ID: {q.id}')
        flash('Question added successfully!', 'success')
        return redirect(url_for('admin.bank_questions', bank_id=bank_id))

    return render_template('admin/add_question.html', bank=bank)


@admin_bp.route('/questions/<int:q_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_question(q_id):
    q = Question.query.get_or_404(q_id)
    bank = QuestionBank.query.get_or_404(q.bank_id)

    if request.method == 'POST':
        q.qno = int(request.form.get('qno', q.qno)) if request.form.get('qno', '').isdigit() else q.qno
        q.section = int(request.form.get('section', q.section))
        q.topic = request.form.get('topic', q.topic).strip() or 'General'
        q.question = request.form.get('question', q.question).strip()
        q.option_a = request.form.get('option_a', q.option_a).strip()
        q.option_b = request.form.get('option_b', q.option_b).strip()
        q.option_c = request.form.get('option_c', q.option_c).strip()
        q.option_d = request.form.get('option_d', q.option_d).strip()
        q.correct_ans = request.form.get('correct_ans', q.correct_ans).strip().upper()
        q.explanation = request.form.get('explanation', q.explanation).strip()

        db.session.commit()
        log_action('Edited question', f'Q ID: {q.id}')
        flash('Question updated successfully!', 'success')
        return redirect(url_for('admin.bank_questions', bank_id=q.bank_id))

    return render_template('admin/edit_question.html', question=q, bank=bank)


@admin_bp.route('/questions/<int:q_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_question(q_id):
    q = Question.query.get_or_404(q_id)
    bank_id = q.bank_id
    db.session.delete(q)
    db.session.commit()
    bank = QuestionBank.query.get(bank_id)
    if bank:
        bank.question_count = Question.query.filter_by(bank_id=bank_id).count()
        db.session.commit()
    log_action('Deleted question', f'Q ID: {q_id}, Bank ID: {bank_id}')
    flash('Question deleted.', 'success')
    return redirect(url_for('admin.bank_questions', bank_id=bank_id))


@admin_bp.route('/questions/bulk_delete', methods=['POST'])
@login_required
@admin_required
def bulk_delete_questions():
    q_ids = request.form.getlist('question_ids')
    bank_id = request.form.get('bank_id', type=int)

    if q_ids:
        Question.query.filter(Question.id.in_([int(i) for i in q_ids])).delete(synchronize_session=False)
        db.session.commit()
        if bank_id:
            bank = QuestionBank.query.get(bank_id)
            if bank:
                bank.question_count = Question.query.filter_by(bank_id=bank_id).count()
                db.session.commit()
        log_action('Bulk deleted questions', f'{len(q_ids)} questions from Bank ID: {bank_id}')
        flash(f'{len(q_ids)} questions deleted.', 'success')

    return redirect(url_for('admin.bank_questions', bank_id=bank_id) if bank_id else url_for('admin.banks'))


@admin_bp.route('/banks/<int:bank_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_bank(bank_id):
    bank = QuestionBank.query.get_or_404(bank_id)
    bank.is_active = not bank.is_active
    db.session.commit()
    log_action('Toggled bank', f'Bank: {bank.name} → {"active" if bank.is_active else "inactive"}')
    flash(f'Bank "{bank.name}" is now {"active" if bank.is_active else "inactive"}.', 'success')
    return redirect(url_for('admin.banks'))


@admin_bp.route('/banks/<int:bank_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_bank(bank_id):
    bank = QuestionBank.query.get_or_404(bank_id)
    name = bank.name
    db.session.delete(bank)
    db.session.commit()
    log_action('Deleted bank', f'Bank: {name}')
    flash(f'Bank "{name}" and all its questions deleted.', 'success')
    return redirect(url_for('admin.banks'))


# ── Exam / Practice Configs ──────────────────────────────
@admin_bp.route('/configs')
@login_required
@admin_required
def configs():
    exam_configs = ExamConfig.query.filter_by(mode='exam').order_by(ExamConfig.created_at.desc()).all()
    practice_configs = ExamConfig.query.filter_by(mode='practice').order_by(ExamConfig.created_at.desc()).all()
    return render_template('admin/configs.html',
                           exam_configs=exam_configs,
                           practice_configs=practice_configs)


@admin_bp.route('/configs/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_config():
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        mode = request.form.get('mode', 'exam')
        if mode not in ['exam', 'practice']:
            mode = 'exam'
        bank_ids_list = request.form.getlist('bank_ids')
        topic_filter_list = request.form.getlist('topic_filter')
        topic_filter = ','.join(topic_filter_list) if topic_filter_list else ''
        is_active = request.form.get('is_active') == 'on'
        allow_reattempt = request.form.get('allow_reattempt') == 'on'

        # Safe numeric parsing — bare int()/float() raises ValueError on bad input
        try:
            total_questions = max(1, int(request.form.get('total_questions', 100)))
            duration_minutes = max(1, int(request.form.get('duration_minutes', 150)))
            marks_correct = max(0.0, float(request.form.get('marks_correct', 2.0)))
            marks_wrong = max(0.0, float(request.form.get('marks_wrong', 0.5)))
            section_filter = int(request.form.get('section_filter', 0))
            if section_filter not in [0, 1, 2]:
                section_filter = 0
        except (ValueError, TypeError):
            flash('Invalid number entered. Please check Total Questions, Duration, and Marks fields.', 'error')
            return redirect(url_for('admin.create_config'))

        if not name:
            flash('Config name is required.', 'error')
            return redirect(url_for('admin.create_config'))
        if not bank_ids_list:
            flash('At least one question bank must be selected.', 'error')
            return redirect(url_for('admin.create_config'))

        config = ExamConfig(
            name=name,
            mode=mode,
            bank_ids=json.dumps([int(b) for b in bank_ids_list]),
            total_questions=total_questions,
            duration_minutes=duration_minutes if mode == 'exam' else 0,
            marks_correct=marks_correct if mode == 'exam' else 0,
            marks_wrong=marks_wrong if mode == 'exam' else 0,
            section_filter=section_filter,
            topic_filter=topic_filter,
            is_active=is_active,
            allow_reattempt=True if mode == 'practice' else allow_reattempt,
            created_by=current_user.id
        )
        db.session.add(config)
        db.session.commit()
        log_action('Created config', f'{mode.title()} config: {name} (ID: {config.id})')
        flash(f'{mode.title()} config "{name}" created!', 'success')
        return redirect(url_for('admin.configs'))

    active_banks = QuestionBank.query.filter_by(is_active=True).all()
    return render_template('admin/config_form.html', config=None, banks=active_banks, mode='create')


@admin_bp.route('/configs/<int:config_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_config(config_id):
    config = ExamConfig.query.get_or_404(config_id)

    if request.method == 'POST':
        config.name = request.form.get('name', config.name).strip()
        config.mode = request.form.get('mode', config.mode)
        bank_ids_list = request.form.getlist('bank_ids')
        config.bank_ids = json.dumps([int(b) for b in bank_ids_list]) if bank_ids_list else config.bank_ids
        topic_filter_list = request.form.getlist('topic_filter')
        config.topic_filter = ','.join(topic_filter_list) if topic_filter_list else ''
        config.is_active = request.form.get('is_active') == 'on'
        config.allow_reattempt = True if config.mode == 'practice' else request.form.get('allow_reattempt') == 'on'

        # Safe numeric parsing
        try:
            config.total_questions = max(1, int(request.form.get('total_questions', config.total_questions)))
            section_filter = int(request.form.get('section_filter', config.section_filter))
            config.section_filter = section_filter if section_filter in [0, 1, 2] else 0
            if config.mode == 'exam':
                config.duration_minutes = max(1, int(request.form.get('duration_minutes', config.duration_minutes)))
                config.marks_correct = max(0.0, float(request.form.get('marks_correct', config.marks_correct)))
                config.marks_wrong = max(0.0, float(request.form.get('marks_wrong', config.marks_wrong)))
            else:
                config.duration_minutes = 0
                config.marks_correct = 0
                config.marks_wrong = 0
        except (ValueError, TypeError):
            flash('Invalid number entered. Please check Total Questions, Duration, and Marks fields.', 'error')
            return redirect(url_for('admin.edit_config', config_id=config_id))

        if not config.name:
            flash('Config name is required.', 'error')
            return redirect(url_for('admin.edit_config', config_id=config_id))

        db.session.commit()
        log_action('Edited config', f'Config: {config.name} (ID: {config.id})')
        flash(f'Config "{config.name}" updated!', 'success')
        return redirect(url_for('admin.configs'))

    active_banks = QuestionBank.query.filter_by(is_active=True).all()
    selected_bank_ids = json.loads(config.bank_ids) if config.bank_ids else []
    selected_topics = [t.strip() for t in config.topic_filter.split(',') if t.strip()] if config.topic_filter else []
    return render_template('admin/config_form.html', config=config, banks=active_banks,
                           mode='edit', selected_bank_ids=selected_bank_ids,
                           selected_topics=selected_topics)


@admin_bp.route('/configs/<int:config_id>/delete', methods=['POST'])
@login_required
@admin_required
def delete_config(config_id):
    config = ExamConfig.query.get_or_404(config_id)
    name = config.name
    db.session.delete(config)
    db.session.commit()
    log_action('Deleted config', f'Config: {name}')
    flash(f'Config "{name}" deleted.', 'success')
    return redirect(url_for('admin.configs'))


@admin_bp.route('/api/topics')
@login_required
@admin_required
def api_topics():
    bank_ids_str = request.args.get('bank_ids', '')
    if not bank_ids_str:
        return jsonify({'topics': []})
    try:
        bank_ids = [int(b.strip()) for b in bank_ids_str.split(',') if b.strip()]
    except ValueError:
        return jsonify({'topics': []})

    topics = db.session.query(Question.topic).filter(
        Question.bank_id.in_(bank_ids)
    ).distinct().order_by(Question.topic).all()
    return jsonify({'topics': [t[0] for t in topics if t[0]]})


# ── Attempts debug ────────────────────────────────────
@admin_bp.route('/attempts/debug')
@login_required
@admin_required
def attempts_debug():
    """Temporary debug route - shows raw DB count"""
    total = TestAttempt.query.count()
    exam_c = TestAttempt.query.filter_by(mode='exam').count()
    prac_c = TestAttempt.query.filter_by(mode='practice').count()
    sample = TestAttempt.query.order_by(TestAttempt.id.desc()).limit(3).all()
    sample_data = [{'id': a.id, 'mode': a.mode, 'status': a.status,
                    'user': a.user.name if a.user else '?',
                    'config': a.config.name if a.config else '?'} for a in sample]
    from flask import jsonify
    return jsonify({
        'total_attempts': total,
        'exam_attempts': exam_c,
        'practice_attempts': prac_c,
        'latest_3': sample_data
    })


# ── Attempts ──────────────────────────────────────────
@admin_bp.route('/attempts')
@login_required
@admin_required
def attempts():
    page = request.args.get('page', 1, type=int)
    config_filter = request.args.get('config_id', '', type=str)
    mode_filter = request.args.get('mode', '', type=str)
    student_filter = request.args.get('student', '', type=str)

    query = TestAttempt.query

    if config_filter and config_filter.isdigit():
        query = query.filter(TestAttempt.config_id == int(config_filter))
    if mode_filter and mode_filter in ['exam', 'practice']:
        query = query.filter(TestAttempt.mode == mode_filter)
    if student_filter and student_filter.strip():
        query = query.join(User, TestAttempt.user_id == User.id).filter(
            User.name.ilike(f'%{student_filter.strip()}%')
        )

    total_count = query.count()
    pagination = query.order_by(TestAttempt.started_at.desc()).paginate(
        page=page, per_page=25, error_out=False
    )
    attempts_list = pagination.items
    configs = ExamConfig.query.order_by(ExamConfig.name).all()

    return render_template('admin/attempts.html',
                           attempts=attempts_list,
                           pagination=pagination,
                           configs=configs,
                           total_count=total_count,
                           config_filter=config_filter,
                           mode_filter=mode_filter,
                           student_filter=student_filter)


@admin_bp.route('/attempts/export')
@login_required
@admin_required
def export_attempts():
    attempts_list = TestAttempt.query.order_by(TestAttempt.started_at.desc()).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID', 'Student', 'Email', 'Config', 'Mode', 'Started', 'Submitted',
                      'Score', 'Max Score', '%', 'Correct', 'Wrong', 'Unattempted',
                      'Bonus', 'Time (sec)', 'Status', 'FS Violations', 'Tab Switches'])
    for a in attempts_list:
        writer.writerow([
            a.id, a.user.name if a.user else 'N/A',
            a.user.email if a.user else 'N/A',
            a.config.name if a.config else 'N/A',
            a.mode,
            a.started_at.strftime('%Y-%m-%d %H:%M') if a.started_at else '',
            a.submitted_at.strftime('%Y-%m-%d %H:%M') if a.submitted_at else '',
            a.score, a.max_score, a.percentage,
            a.correct_count, a.wrong_count, a.unattempted,
            a.bonus_count, a.time_taken_sec, a.status,
            a.fs_exit_count, a.tab_switch_count
        ])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=attempts_export_{datetime.now(timezone.utc).strftime("%Y%m%d")}.csv'}
    )


@admin_bp.route('/attempts/<int:attempt_id>')
@login_required
@admin_required
def attempt_detail(attempt_id):
    attempt = TestAttempt.query.get_or_404(attempt_id)
    questions_data = json.loads(attempt.questions_json) if attempt.questions_json else []

    # Enrich with full question data
    enriched = []
    for qd in questions_data:
        q = Question.query.get(qd.get('q_id'))
        if q:
            enriched.append({
                'q_id': q.id,
                'qno': q.qno,
                'section': q.section,
                'topic': q.topic,
                'question': q.question,
                'option_a': q.option_a,
                'option_b': q.option_b,
                'option_c': q.option_c,
                'option_d': q.option_d,
                'correct_ans': q.correct_ans,
                'explanation': q.explanation,
                'given_answer': qd.get('given_answer', ''),
                'status': qd.get('status', 'unanswered'),
                'marks': qd.get('marks', 0)
            })

    return render_template('admin/attempt_detail.html', attempt=attempt, questions=enriched)


@admin_bp.route('/attempts/<int:attempt_id>/reset', methods=['POST'])
@login_required
@admin_required
def reset_attempt(attempt_id):
    attempt = TestAttempt.query.get_or_404(attempt_id)
    config = ExamConfig.query.get(attempt.config_id)
    if config and config.allow_reattempt:
        attempt.status = 'reset'
        db.session.commit()
        log_action('Reset attempt', f'Attempt ID: {attempt_id}', user_id=attempt.user_id)
        flash('Attempt has been reset. Student can re-attempt.', 'success')
    else:
        flash('Re-attempt is not allowed for this config.', 'error')
    return redirect(url_for('admin.attempt_detail', attempt_id=attempt_id))


# ── Practice Sessions ──────────────────────────────────────
@admin_bp.route('/practice_sessions')
@login_required
@admin_required
def practice_sessions():
    # Auto-deactivate sessions inactive for more than 2 hours
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
    stale = PracticeSession.query.filter(
        PracticeSession.status == 'active',
        PracticeSession.last_active_at < cutoff
    ).all()
    auto_closed = 0
    for s in stale:
        s.status = 'abandoned'
        auto_closed += 1
    if auto_closed:
        db.session.commit()
        log_action('Auto-abandoned practice sessions', f'{auto_closed} sessions inactive >2h')

    sessions = PracticeSession.query.order_by(PracticeSession.started_at.desc()).all()
    return render_template('admin/practice_sessions.html', sessions=sessions,
                           auto_closed=auto_closed)


@admin_bp.route('/practice_sessions/<int:session_id>/deactivate', methods=['POST'])
@login_required
@admin_required
def deactivate_practice_session(session_id):
    practice_session = PracticeSession.query.get_or_404(session_id)
    if practice_session.status == 'active':
        practice_session.status = 'abandoned'
        db.session.commit()
        log_action('Manually abandoned practice session',
                   f'Session ID: {session_id}, User: {practice_session.user.name if practice_session.user else "?"}',
                   user_id=practice_session.user_id)
        flash(f'Practice session deactivated.', 'success')
    else:
        flash('Session is not active.', 'warning')
    return redirect(url_for('admin.practice_sessions'))


# ── Analytics ──────────────────────────────────────────
@admin_bp.route('/analytics')
@login_required
@admin_required
def analytics():
    # Total exam attempts
    total_exam_attempts = TestAttempt.query.filter_by(mode='exam').count()
    exam_submitted = TestAttempt.query.filter(
        TestAttempt.mode == 'exam',
        TestAttempt.status.in_(['submitted', 'timeout'])
    ).all()
    avg_exam_score = round(sum(a.percentage for a in exam_submitted) / len(exam_submitted), 1) if exam_submitted else 0
    pass_count = sum(1 for a in exam_submitted if a.percentage >= 50)
    pass_rate = round(pass_count / len(exam_submitted) * 100, 1) if exam_submitted else 0

    total_practice = PracticeSession.query.count()
    practice_completed = PracticeSession.query.filter(PracticeSession.total_answered > 0).all()
    avg_practice_accuracy = round(
        sum(s.total_correct / s.total_answered * 100 for s in practice_completed if s.total_answered > 0)
        / len(practice_completed), 1
    ) if practice_completed else 0

    # Daily exam attempts (last 14 days)
    daily_data = []
    for i in range(13, -1, -1):
        day = datetime.now(timezone.utc).date() - timedelta(days=i)
        day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
        day_end = day_start + timedelta(days=1)
        count = TestAttempt.query.filter(
            TestAttempt.started_at >= day_start,
            TestAttempt.started_at < day_end,
            TestAttempt.mode == 'exam'
        ).count()
        daily_data.append({'date': day.strftime('%b %d'), 'count': count})

    # Topic-wise accuracy + hardest questions
    # BUG FIX: Collect all question IDs first, then do ONE bulk query instead
    # of calling Question.query.get() for every single question in every attempt (N+1).
    all_attempts = TestAttempt.query.filter(TestAttempt.status.in_(['submitted', 'timeout'])).all()

    all_q_ids = set()
    for attempt in all_attempts:
        qdata = json.loads(attempt.questions_json) if attempt.questions_json else []
        for qd in qdata:
            if qd.get('q_id'):
                all_q_ids.add(qd['q_id'])

    questions_map = {q.id: q for q in Question.query.filter(Question.id.in_(all_q_ids)).all()}

    topic_accuracy = {}
    q_stats = {}

    for attempt in all_attempts:
        qdata = json.loads(attempt.questions_json) if attempt.questions_json else []
        for qd in qdata:
            qid = qd.get('q_id')
            q = questions_map.get(qid)
            if not q:
                continue

            given = qd.get('given_answer', '')

            # Topic accuracy
            if q.topic not in topic_accuracy:
                topic_accuracy[q.topic] = {'correct': 0, 'total': 0}
            topic_accuracy[q.topic]['total'] += 1
            if given and given == q.correct_ans:
                topic_accuracy[q.topic]['correct'] += 1

            # Question difficulty stats
            if qid not in q_stats:
                q_stats[qid] = {'correct': 0, 'total': 0}
            q_stats[qid]['total'] += 1
            if given and given == q.correct_ans:
                q_stats[qid]['correct'] += 1

    topic_chart_data = []
    for topic, data in sorted(topic_accuracy.items()):
        pct = round(data['correct'] / data['total'] * 100, 1) if data['total'] > 0 else 0
        topic_chart_data.append({'topic': topic, 'accuracy': pct, 'total': data['total']})

    hardest = []
    for qid, data in q_stats.items():
        if data['total'] > 0:
            q = questions_map.get(qid)
            if q:
                pct = round(data['correct'] / data['total'] * 100, 1)
                hardest.append({
                    'id': qid, 'question': q.question[:80],
                    'topic': q.topic, 'accuracy': pct, 'attempts': data['total']
                })
    hardest.sort(key=lambda x: x['accuracy'])
    hardest = hardest[:10]

    # Exam vs Practice ratio
    exam_count = TestAttempt.query.filter_by(mode='exam').count()
    practice_count = PracticeSession.query.count()

    # Top 10 students
    top_students = db.session.query(
        User.name, User.email, User.engineering_branch,
        db.func.max(TestAttempt.percentage).label('best_score'),
        db.func.count(TestAttempt.id).label('attempt_count')
    ).join(TestAttempt).filter(
        TestAttempt.mode == 'exam',
        TestAttempt.status.in_(['submitted', 'timeout'])
    ).group_by(User.id).order_by(db.desc('best_score')).limit(10).all()

    return render_template('admin/analytics.html',
                           total_exam_attempts=total_exam_attempts,
                           avg_exam_score=avg_exam_score,
                           pass_rate=pass_rate,
                           total_practice=total_practice,
                           avg_practice_accuracy=avg_practice_accuracy,
                           daily_data=json.dumps(daily_data),
                           topic_chart_data=json.dumps(topic_chart_data),
                           exam_count=exam_count,
                           practice_count=practice_count,
                           top_students=top_students,
                           hardest=hardest)


@admin_bp.route('/analytics/export')
@login_required
@admin_required
def export_analytics():
    # Export all students' best scores and data
    students_data = db.session.query(
        User.name, User.email, User.engineering_branch, User.enrollment_number,
        db.func.max(TestAttempt.percentage).label('best_score'),
        db.func.count(TestAttempt.id).label('attempt_count')
    ).join(TestAttempt).filter(
        TestAttempt.mode == 'exam',
        TestAttempt.status.in_(['submitted', 'timeout'])
    ).group_by(User.id).order_by(db.desc('best_score')).all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Name', 'Email', 'Enrollment Number', 'Engineering Branch', 'Best Score (%)', 'Total Attempts'])
    for s in students_data:
        writer.writerow([s.name, s.email, s.enrollment_number, s.engineering_branch, s.best_score, s.attempt_count])

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=analytics_student_scores_{datetime.now(timezone.utc).strftime("%Y%m%d")}.csv'}
    )


# ── User Management ──────────────────────────────────────
@admin_bp.route('/users')
@login_required
@admin_required
def users():
    users_list = User.query.order_by(User.created_at.desc()).all()
    # Get last attempt for each user
    user_last_attempts = {}
    for u in users_list:
        last = TestAttempt.query.filter_by(user_id=u.id).order_by(TestAttempt.started_at.desc()).first()
        user_last_attempts[u.id] = last.started_at if last else None

    return render_template('admin/users.html', users=users_list, user_last_attempts=user_last_attempts)


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot deactivate yourself.', 'error')
        return redirect(url_for('admin.users'))
    user.is_active_user = not user.is_active_user
    db.session.commit()
    status = 'activated' if user.is_active_user else 'deactivated'
    log_action(f'User {status}', f'User: {user.name} ({user.email})', user_id=user.id)
    flash(f'User "{user.name}" has been {status}.', 'success')
    return redirect(url_for('admin.users'))


@admin_bp.route('/users/<int:user_id>/promote', methods=['POST'])
@login_required
@admin_required
def promote_user(user_id):
    user = User.query.get_or_404(user_id)
    user.role = 'admin'
    db.session.commit()
    log_action('Promoted to admin', f'User: {user.name} ({user.email})', user_id=user.id)
    flash(f'User "{user.name}" promoted to admin.', 'success')
    return redirect(url_for('admin.users'))