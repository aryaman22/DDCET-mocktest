/* ════════════════════════════════════════════════════════
   DDCET Portal — practice.js v2.0
   Practice mode: server-side answer validation, no cheating
   ════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    const questions = window.PRACTICE_QUESTIONS || [];
    const sessionId = window.SESSION_ID;
    const csrf = window.CSRF_TOKEN;

    let currentIndex = 0;
    let totalCorrect = 0;
    let totalAnswered = 0;
    let answered = new Set(); // indices already answered
    let feedbackShown = false;

    const container = document.getElementById('practice-container');

    // ── Render question ──────────────────────────────
    function renderQuestion(idx) {
        currentIndex = idx;
        feedbackShown = false;
        const q = questions[idx];
        if (!q) { finishPractice(); return; }

        updateProgress();

        container.innerHTML = `
            <div class="question-card animate-fade" id="q-card">
                <div class="flex items-center gap-8" style="margin-bottom:12px">
                    <span class="badge badge-primary">Q${idx + 1}</span>
                    ${q.section ? `<span class="chip">${q.section}</span>` : ''}
                    ${q.topic ? `<span class="chip">${q.topic}</span>` : ''}
                </div>
                <div class="question-text">${q.question}</div>
                <div class="options-list" id="options-list">
                    ${['A', 'B', 'C', 'D'].map(opt => `
                        <button class="option-btn" data-opt="${opt}" onclick="selectAnswer('${opt}')">
                            <span class="option-label">${opt}</span>
                            <span class="option-text">${q['option_' + opt.toLowerCase()]}</span>
                        </button>
                    `).join('')}
                </div>
                <div class="question-actions" style="margin-top:20px">
                    <button class="btn btn-primary" id="btn-submit" onclick="submitAnswer()" disabled>Submit Answer</button>
                    <button class="btn btn-ghost" onclick="skipQuestion()">Skip</button>
                </div>
                <div id="feedback-area"></div>
            </div>
            <div class="text-center" style="margin-top:24px">
                <button class="btn btn-outline" onclick="finishPractice()">Finish Practice</button>
            </div>`;
    }

    let selectedOption = null;

    window.selectAnswer = function (opt) {
        if (feedbackShown) return;
        selectedOption = opt;
        document.querySelectorAll('#options-list .option-btn').forEach(b => {
            b.classList.toggle('selected', b.dataset.opt === opt);
        });
        document.getElementById('btn-submit').disabled = false;
    };

    // ── Submit answer (server-side validation) ───────
    window.submitAnswer = function () {
        if (!selectedOption || feedbackShown) return;
        feedbackShown = true;
        const q = questions[currentIndex];

        document.getElementById('btn-submit').disabled = true;

        fetch(`/student/practice/${sessionId}/answer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
            body: JSON.stringify({ question_id: q.id, answer: selectedOption })
        })
            .then(r => r.json())
            .then(data => {
                totalAnswered++;
                if (data.correct) totalCorrect++;
                answered.add(currentIndex);

                // Lock options and show correct/wrong
                document.querySelectorAll('#options-list .option-btn').forEach(b => {
                    b.classList.add('locked');
                    b.style.pointerEvents = 'none';
                    if (b.dataset.opt === data.correct_answer) b.classList.add('correct');
                    if (b.dataset.opt === selectedOption && !data.correct) b.classList.add('wrong');
                });

                // Show feedback
                const feedbackArea = document.getElementById('feedback-area');
                feedbackArea.innerHTML = `
                <div class="feedback-box ${data.correct ? 'feedback-correct' : 'feedback-wrong'}" style="margin-top:16px;animation:slideUp .3s ease">
                    <strong>${data.correct ? '✅ Correct!' : '❌ Incorrect'}</strong>
                    ${data.explanation ? `<div class="explanation">${data.explanation}</div>` : ''}
                </div>
                <div class="question-actions" style="margin-top:12px">
                    <button class="btn btn-primary" onclick="nextPracticeQuestion()">Next Question →</button>
                </div>`;

                updateProgress();

                // Auto-scroll to feedback
                feedbackArea.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            })
            .catch(err => {
                console.error('Answer submission failed:', err);
                feedbackShown = false;
                document.getElementById('btn-submit').disabled = false;
            });
    };

    window.skipQuestion = function () {
        if (currentIndex < questions.length - 1) renderQuestion(currentIndex + 1);
        else finishPractice();
    };

    window.nextPracticeQuestion = function () {
        selectedOption = null;
        if (currentIndex < questions.length - 1) renderQuestion(currentIndex + 1);
        else finishPractice();
    };

    // ── Progress ─────────────────────────────────────
    function updateProgress() {
        const pct = Math.round(((currentIndex + 1) / questions.length) * 100);
        const progressFill = document.getElementById('progress-fill');
        if (progressFill) progressFill.style.width = pct + '%';

        document.getElementById('q-counter').textContent = `Q ${currentIndex + 1} / ${questions.length}`;

        const accPct = totalAnswered > 0 ? Math.round(totalCorrect / totalAnswered * 100) : 0;
        const accEl = document.getElementById('accuracy-display');
        if (accEl) {
            accEl.textContent = `Accuracy: ${accPct}% (${totalCorrect}/${totalAnswered})`;
            accEl.style.color = accPct >= 70 ? 'var(--green)' : accPct >= 40 ? 'var(--yellow)' : 'var(--red)';
        }
    }

    // ── Finish ────────────────────────────────────────
    window.finishPractice = function () {
        fetch(`/student/practice/${sessionId}/finish`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf }
        })
            .then(() => { window.location.href = `/student/practice_result/${sessionId}`; })
            .catch(() => { window.location.href = `/student/practice_result/${sessionId}`; });
    };

    // ── Init ──────────────────────────────────────────
    if (questions.length > 0) renderQuestion(0);
    else {
        container.innerHTML = '<div class="empty-state"><div class="empty-icon">🎯</div><p>No questions available for this practice set.</p></div>';
    }
})();
