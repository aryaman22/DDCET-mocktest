from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, abort
from flask_login import login_required, current_user
from models import db, User, QuestionBank, Question, ExamConfig, TestAttempt, PracticeSession, AdminLog
from utils import select_questions_for_config, calculate_exam_score
from datetime import datetime
import json

student_bp = Blueprint('student', __name__, template_folder='templates')


def student_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'student':
            abort(403)
        return f(*args, **kwargs)
    return decorated


def get_bank_names(config):
    """Get bank names for a config."""
    try:
        bank_ids = json.loads(config.bank_ids) if config.bank_ids else []
    except (json.JSONDecodeError, TypeError):
        bank_ids = []
    banks = QuestionBank.query.filter(QuestionBank.id.in_(bank_ids)).all()
    return ', '.join(b.name for b in banks)


# ── Home ──────────────────────────────────────────
@student_bp.route('/home')
@login_required
@student_required
def home():
    # Exam configs
    exam_configs = ExamConfig.query.filter_by(mode='exam', is_active=True).all()
    exam_data = []
    for config in exam_configs:
        attempt = TestAttempt.query.filter_by(
            user_id=current_user.id,
            config_id=config.id,
            mode='exam'
        ).order_by(TestAttempt.started_at.desc()).first()

        status = 'available'
        attempt_id = None
        if attempt:
            if attempt.status == 'in_progress':
                status = 'in_progress'
                attempt_id = attempt.id
            elif attempt.status in ['submitted', 'timeout'] and not config.allow_reattempt:
                status = 'completed'
                attempt_id = attempt.id
            elif attempt.status == 'reset':
                status = 'available'

        exam_data.append({
            'config': config,
            'bank_names': get_bank_names(config),
            'status': status,
            'attempt_id': attempt_id
        })

    # Practice configs
    practice_configs = ExamConfig.query.filter_by(mode='practice', is_active=True).all()
    practice_data = []
    for config in practice_configs:
        # Lifetime accuracy
        sessions = PracticeSession.query.filter_by(
            user_id=current_user.id,
            config_id=config.id
        ).all()
        total_answered = sum(s.total_answered for s in sessions)
        total_correct = sum(s.total_correct for s in sessions)
        accuracy = round(total_correct / total_answered * 100, 1) if total_answered > 0 else 0

        topics = []
        if config.topic_filter and config.topic_filter.strip():
            topics = [t.strip() for t in config.topic_filter.split(',') if t.strip()]

        practice_data.append({
            'config': config,
            'bank_names': get_bank_names(config),
            'accuracy': accuracy,
            'total_answered': total_answered,
            'total_correct': total_correct,
            'topics': topics
        })

    # History (exam only)
    history = TestAttempt.query.filter_by(
        user_id=current_user.id,
        mode='exam'
    ).order_by(TestAttempt.started_at.desc()).all()

    return render_template('student/home.html',
                           exam_data=exam_data,
                           practice_data=practice_data,
                           history=history)


# ══════════════════════════════════════════════════════
# EXAM FLOW
# ══════════════════════════════════════════════════════

@student_bp.route('/exam/<int:config_id>/instructions')
@login_required
@student_required
def exam_instructions(config_id):
    config = ExamConfig.query.get_or_404(config_id)
    if config.mode != 'exam' or not config.is_active:
        abort(404)

    # Check if already has completed attempt
    existing = TestAttempt.query.filter_by(
        user_id=current_user.id,
        config_id=config_id,
        mode='exam'
    ).filter(TestAttempt.status.in_(['submitted', 'timeout'])).first()

    if existing and not config.allow_reattempt:
        flash('You have already completed this exam.', 'warning')
        return redirect(url_for('student.result', attempt_id=existing.id))

    return render_template('student/instructions.html', config=config)


@student_bp.route('/exam/<int:config_id>/start')
@login_required
@student_required
def start_exam(config_id):
    config = ExamConfig.query.get_or_404(config_id)
    if config.mode != 'exam' or not config.is_active:
        abort(404)

    # Check for existing in_progress attempt
    existing = TestAttempt.query.filter_by(
        user_id=current_user.id,
        config_id=config_id,
        mode='exam',
        status='in_progress'
    ).first()

    if existing:
        # Resume
        return _render_exam(existing, config)

    # Check if already completed
    completed = TestAttempt.query.filter_by(
        user_id=current_user.id,
        config_id=config_id,
        mode='exam'
    ).filter(TestAttempt.status.in_(['submitted', 'timeout'])).first()

    if completed and not config.allow_reattempt:
        flash('You have already completed this exam.', 'warning')
        return redirect(url_for('student.result', attempt_id=completed.id))

    # Select questions
    questions = select_questions_for_config(config)
    if not questions:
        flash('No questions available for this exam configuration.', 'error')
        return redirect(url_for('student.home'))

    # Build questions_json
    q_json = [{'q_id': q.id, 'given_answer': None, 'status': 'unanswered', 'marks': 0} for q in questions]

    attempt = TestAttempt(
        user_id=current_user.id,
        config_id=config_id,
        mode='exam',
        started_at=datetime.utcnow(),
        status='in_progress',
        max_score=len(questions) * config.marks_correct,
        questions_json=json.dumps(q_json)
    )
    db.session.add(attempt)
    db.session.commit()

    if len(questions) < config.total_questions:
        log = AdminLog(
            action='Question pool warning',
            detail=f'Config {config.name}: requested {config.total_questions} but only {len(questions)} available',
            user_id=current_user.id
        )
        db.session.add(log)
        db.session.commit()

    return _render_exam(attempt, config)


def _render_exam(attempt, config):
    """Render exam page with question data (WITHOUT correct answers)."""
    q_data = json.loads(attempt.questions_json)
    q_ids = [qd['q_id'] for qd in q_data]
    questions_from_db = {q.id: q for q in Question.query.filter(Question.id.in_(q_ids)).all()}

    # Build client-safe question list (NO correct_ans)
    client_questions = []
    answers = {}
    for idx, qd in enumerate(q_data):
        q = questions_from_db.get(qd['q_id'])
        if q:
            client_questions.append({
                'id': q.id,
                'qno_display': idx + 1,
                'section': q.section,
                'topic': q.topic,
                'question': q.question,
                'option_a': q.option_a,
                'option_b': q.option_b,
                'option_c': q.option_c,
                'option_d': q.option_d
            })
            if qd.get('given_answer'):
                answers[str(q.id)] = qd['given_answer']

    return render_template('student/exam.html',
                           attempt=attempt,
                           config=config,
                           questions_json=json.dumps(client_questions),
                           saved_answers=json.dumps(answers),
                           duration_seconds=config.duration_minutes * 60)


@student_bp.route('/exam/<int:attempt_id>/save', methods=['POST'])
@login_required
@student_required
def save_exam(attempt_id):
    attempt = TestAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id or attempt.status != 'in_progress':
        return jsonify({'ok': False, 'error': 'Not authorized'}), 403

    data = request.get_json()
    answers = data.get('answers', {})

    # Update questions_json with answers
    q_data = json.loads(attempt.questions_json)
    for qd in q_data:
        ans = answers.get(str(qd['q_id']))
        if ans:
            qd['given_answer'] = ans
            qd['status'] = 'answered'

    attempt.questions_json = json.dumps(q_data)
    db.session.commit()

    return jsonify({'ok': True, 'saved_at': datetime.utcnow().strftime('%H:%M:%S')})


@student_bp.route('/exam/<int:attempt_id>/submit', methods=['POST'])
@login_required
@student_required
def submit_exam(attempt_id):
    attempt = TestAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id:
        return jsonify({'ok': False, 'error': 'Not authorized'}), 403
    if attempt.status not in ['in_progress']:
        return jsonify({'ok': False, 'error': 'Already submitted'}), 400

    config = ExamConfig.query.get(attempt.config_id)
    data = request.get_json() or {}
    final_answers = data.get('answers', {})

    # Update questions_json with final answers
    q_data = json.loads(attempt.questions_json)
    q_ids = [qd['q_id'] for qd in q_data]
    questions_from_db = Question.query.filter(Question.id.in_(q_ids)).all()
    questions_map = {q.id: q for q in questions_from_db}

    for qd in q_data:
        ans = final_answers.get(str(qd['q_id']))
        if ans:
            qd['given_answer'] = ans
            qd['status'] = 'answered'

    # Build answers dict and questions list for scoring
    user_answers = {}
    questions_for_scoring = []
    for qd in q_data:
        q = questions_map.get(qd['q_id'])
        if q:
            questions_for_scoring.append(q)
            if qd.get('given_answer'):
                user_answers[str(q.id)] = qd['given_answer']

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
    attempt.submitted_at = datetime.utcnow()
    attempt.status = 'submitted'
    attempt.score = result['marks']
    attempt.max_score = result['max_score']
    attempt.percentage = result['percentage']
    attempt.correct_count = result['correct']
    attempt.wrong_count = result['wrong']
    attempt.unattempted = result['unattempted']
    attempt.bonus_count = result['bonus']

    # Calculate time taken
    if attempt.started_at:
        attempt.time_taken_sec = int((datetime.utcnow() - attempt.started_at).total_seconds())

    db.session.commit()

    return jsonify({'ok': True, 'redirect': url_for('student.result', attempt_id=attempt.id)})


@student_bp.route('/exam/<int:attempt_id>/log', methods=['POST'])
@login_required
@student_required
def log_violation(attempt_id):
    attempt = TestAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id:
        return jsonify({'ok': False}), 403

    data = request.get_json()
    event = data.get('event', '')
    count = data.get('count', 0)

    if event == 'fullscreen_exit':
        attempt.fs_exit_count = count
    elif event == 'tab_switch':
        attempt.tab_switch_count = count

    db.session.commit()

    log = AdminLog(
        user_id=current_user.id,
        action=f'Exam violation: {event}',
        detail=f'Attempt {attempt_id}, Count: {count}'
    )
    db.session.add(log)
    db.session.commit()

    return jsonify({'ok': True})


@student_bp.route('/result/<int:attempt_id>')
@login_required
@student_required
def result(attempt_id):
    attempt = TestAttempt.query.get_or_404(attempt_id)
    if attempt.user_id != current_user.id:
        abort(403)

    config = ExamConfig.query.get(attempt.config_id)
    q_data = json.loads(attempt.questions_json) if attempt.questions_json else []
    q_ids = [qd['q_id'] for qd in q_data]
    questions_map = {q.id: q for q in Question.query.filter(Question.id.in_(q_ids)).all()}

    # Build review data
    review = []
    topic_stats = {}
    for idx, qd in enumerate(q_data):
        q = questions_map.get(qd['q_id'])
        if q:
            given = qd.get('given_answer', '')
            is_correct = (given == q.correct_ans) or (q.correct_ans == 'X')
            review.append({
                'qno_display': idx + 1,
                'section': q.section,
                'topic': q.topic,
                'question': q.question,
                'option_a': q.option_a,
                'option_b': q.option_b,
                'option_c': q.option_c,
                'option_d': q.option_d,
                'correct_ans': q.correct_ans,
                'given_answer': given,
                'explanation': q.explanation or '',
                'is_correct': is_correct,
                'marks': qd.get('marks', 0)
            })

            # Topic stats
            if q.topic not in topic_stats:
                topic_stats[q.topic] = {'correct': 0, 'total': 0}
            topic_stats[q.topic]['total'] += 1
            if is_correct:
                topic_stats[q.topic]['correct'] += 1

    topic_chart = [
        {'topic': t, 'accuracy': round(d['correct'] / d['total'] * 100, 1) if d['total'] > 0 else 0,
         'correct': d['correct'], 'total': d['total']}
        for t, d in sorted(topic_stats.items())
    ]

    return render_template('student/result.html',
                           attempt=attempt,
                           config=config,
                           review=review,
                           topic_chart=json.dumps(topic_chart))


# ══════════════════════════════════════════════════════
# PRACTICE FLOW
# ══════════════════════════════════════════════════════

@student_bp.route('/practice/<int:config_id>/start', methods=['POST'])
@login_required
@student_required
def start_practice(config_id):
    config = ExamConfig.query.get_or_404(config_id)
    if config.mode != 'practice' or not config.is_active:
        abort(404)

    questions = select_questions_for_config(config)
    if not questions:
        flash('No questions available for this practice config.', 'error')
        return redirect(url_for('student.home'))

    session = PracticeSession(
        user_id=current_user.id,
        config_id=config_id,
        started_at=datetime.utcnow(),
        last_active_at=datetime.utcnow(),
        questions_seen=json.dumps([q.id for q in questions]),
        status='active'
    )
    db.session.add(session)
    db.session.commit()

    return redirect(url_for('student.practice_page', session_id=session.id))


@student_bp.route('/practice/<int:session_id>')
@login_required
@student_required
def practice_page(session_id):
    practice = PracticeSession.query.get_or_404(session_id)
    if practice.user_id != current_user.id:
        abort(403)

    config = ExamConfig.query.get(practice.config_id)
    q_ids = json.loads(practice.questions_seen) if practice.questions_seen else []

    # Get questions in order
    questions_map = {q.id: q for q in Question.query.filter(Question.id.in_(q_ids)).all()}
    client_questions = []
    for qid in q_ids:
        q = questions_map.get(qid)
        if q:
            client_questions.append({
                'id': q.id,
                'qno': q.qno,
                'section': q.section,
                'topic': q.topic,
                'question': q.question,
                'option_a': q.option_a,
                'option_b': q.option_b,
                'option_c': q.option_c,
                'option_d': q.option_d,
                'correct_ans': q.correct_ans,
                'explanation': q.explanation or ''
            })

    # Topic drill display
    topic_drill = ''
    if config and config.topic_filter and config.topic_filter.strip():
        topics = [t.strip() for t in config.topic_filter.split(',') if t.strip()]
        if len(topics) <= 3:
            topic_drill = ', '.join(topics)

    return render_template('student/practice.html',
                           practice=practice,
                           config=config,
                           questions_json=json.dumps(client_questions),
                           topic_drill=topic_drill)


@student_bp.route('/practice/<int:session_id>/answer', methods=['POST'])
@login_required
@student_required
def practice_answer(session_id):
    practice = PracticeSession.query.get_or_404(session_id)
    if practice.user_id != current_user.id:
        return jsonify({'ok': False}), 403

    data = request.get_json()
    q_id = data.get('q_id')
    given_answer = data.get('given_answer', '')

    if given_answer and given_answer.lower() != 'skip':
        q = Question.query.get(q_id)
        if q:
            practice.total_answered += 1
            if given_answer.upper() == q.correct_ans or q.correct_ans == 'X':
                practice.total_correct += 1
            practice.last_active_at = datetime.utcnow()
            db.session.commit()
            return jsonify({'ok': True, 'correct': given_answer.upper() == q.correct_ans or q.correct_ans == 'X'})

    return jsonify({'ok': True, 'correct': False})


@student_bp.route('/practice/<int:session_id>/finish', methods=['POST'])
@login_required
@student_required
def finish_practice(session_id):
    practice = PracticeSession.query.get_or_404(session_id)
    if practice.user_id != current_user.id:
        return jsonify({'ok': False}), 403

    practice.status = 'completed'
    practice.last_active_at = datetime.utcnow()
    db.session.commit()

    return jsonify({'ok': True, 'redirect': url_for('student.practice_result', session_id=session_id)})


@student_bp.route('/practice_result/<int:session_id>')
@login_required
@student_required
def practice_result(session_id):
    practice = PracticeSession.query.get_or_404(session_id)
    if practice.user_id != current_user.id:
        abort(403)

    config = ExamConfig.query.get(practice.config_id)
    q_ids = json.loads(practice.questions_seen) if practice.questions_seen else []
    questions_map = {q.id: q for q in Question.query.filter(Question.id.in_(q_ids)).all()}

    accuracy = round(practice.total_correct / practice.total_answered * 100, 1) if practice.total_answered > 0 else 0

    questions_list = []
    for qid in q_ids:
        q = questions_map.get(qid)
        if q:
            questions_list.append({
                'id': q.id,
                'qno': q.qno,
                'section': q.section,
                'topic': q.topic,
                'question': q.question,
                'option_a': q.option_a,
                'option_b': q.option_b,
                'option_c': q.option_c,
                'option_d': q.option_d,
                'correct_ans': q.correct_ans,
                'explanation': q.explanation or ''
            })

    return render_template('student/practice_result.html',
                           practice=practice,
                           config=config,
                           accuracy=accuracy,
                           questions=questions_list)
