/* ============================================
   DDCET Exam Portal — practice.js
   Practice mode: instant feedback, no lock,
   no timer, no fullscreen
   ============================================ */

const SESSION_ID = window.SESSION_ID;
let questions = window.PRACTICE_QUESTIONS || [];
let currentIdx = 0;
let answered = {};   // { q_id: { given, correct_ans, isCorrect } }
let totalCorrect = 0;
let totalAnswered = 0;

window.addEventListener('load', () => {
    renderQuestion(0);
    updateProgress();
    updateAccuracy();
});

// ── Render Question ─────────────────────────
function renderQuestion(idx) {
    if (idx < 0 || idx >= questions.length) return;
    currentIdx = idx;
    const q = questions[idx];
    const qId = q.id;

    const container = document.getElementById('practice-container');
    if (!container) return;

    const prev = answered[qId];
    const isAnswered = !!prev;

    let optionsHtml = ['A', 'B', 'C', 'D'].map(opt => {
        const optKey = `option_${opt.toLowerCase()}`;
        let cls = 'option-btn';
        if (isAnswered) {
            cls += ' locked';
            if (opt === q.correct_ans || q.correct_ans === 'X') cls += ' correct';
            if (opt === prev.given && !prev.isCorrect && q.correct_ans !== 'X') cls += ' wrong';
        }
        return `<button class="${cls}" ${isAnswered ? 'disabled' : `onclick="selectPracticeOption('${qId}', '${opt}')"`} id="opt-${qId}-${opt}">
            <span class="option-label">${opt}</span>
            <span class="option-text">${q[optKey]}</span>
        </button>`;
    }).join('');

    let feedbackHtml = '';
    if (isAnswered) {
        const isCorrect = prev.isCorrect;
        feedbackHtml = `
            <div class="feedback-box ${isCorrect ? 'feedback-correct' : 'feedback-wrong'}">
                <div>${isCorrect ? '✅ Correct!' : '❌ Incorrect.'} The answer is <strong>${q.correct_ans}</strong>: ${q['option_' + q.correct_ans.toLowerCase()] || 'Bonus question'}</div>
                ${q.explanation ? `<div class="explanation">💡 ${q.explanation}</div>` : ''}
            </div>
        `;
    }

    let buttonsHtml = '';
    if (!isAnswered) {
        buttonsHtml = `
            <div class="question-actions">
                <button class="btn btn-primary" id="submit-answer-btn" onclick="submitPracticeAnswer('${qId}')" disabled>Submit Answer</button>
                <button class="btn btn-outline" onclick="skipQuestion('${qId}')">Skip →</button>
            </div>
        `;
    } else {
        buttonsHtml = `
            <div class="question-actions">
                <div class="btn-group">
                    <button class="btn btn-outline btn-sm" onclick="prevPracticeQuestion()" ${idx === 0 ? 'disabled' : ''}>← Prev</button>
                </div>
                <div class="btn-group">
                    ${idx < questions.length - 1 ?
                `<button class="btn btn-primary btn-sm" onclick="nextPracticeQuestion()">Next Question →</button>` :
                `<button class="btn btn-success btn-sm" onclick="finishPractice()">🏁 Finish Practice</button>`
            }
                </div>
            </div>
        `;
    }

    container.innerHTML = `
        <div class="question-card">
            <div class="question-header">
                <span class="question-number">Q ${idx + 1} / ${questions.length}</span>
                <span class="badge badge-muted">Section ${q.section}</span>
                <span class="badge badge-muted">${q.topic}</span>
            </div>
            <div class="question-text">${q.question}</div>
            <div class="options-list" id="options-${qId}">
                ${optionsHtml}
            </div>
            ${feedbackHtml}
            ${buttonsHtml}
        </div>
    `;

    // Update question counter in header
    const qCounter = document.getElementById('q-counter');
    if (qCounter) qCounter.textContent = `Q ${idx + 1} / ${questions.length}`;

    updateProgress();
}

// ── Selected Option Tracking ──────────────────
let selectedOption = null;

function selectPracticeOption(qId, opt) {
    if (answered[qId]) return;

    selectedOption = opt;

    // Deselect all, select clicked
    document.querySelectorAll(`#options-${qId} .option-btn`).forEach(btn => {
        btn.classList.remove('selected');
    });
    document.getElementById(`opt-${qId}-${opt}`)?.classList.add('selected');

    // Enable submit button
    const submitBtn = document.getElementById('submit-answer-btn');
    if (submitBtn) submitBtn.disabled = false;
}

// ── Submit Answer ─────────────────────────────
function submitPracticeAnswer(qId) {
    if (!selectedOption || answered[qId]) return;

    const q = questions[currentIdx];
    const given = selectedOption;
    const isCorrect = given === q.correct_ans || q.correct_ans === 'X';

    answered[qId] = { given, correct_ans: q.correct_ans, isCorrect };
    totalAnswered++;
    if (isCorrect) totalCorrect++;

    selectedOption = null;

    // POST to server
    fetch(`/student/practice/${SESSION_ID}/answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ q_id: parseInt(qId), given_answer: given })
    }).catch(() => { });

    // Re-render with feedback
    renderQuestion(currentIdx);
    updateAccuracy();
}

// ── Skip ──────────────────────────────────────
function skipQuestion(qId) {
    fetch(`/student/practice/${SESSION_ID}/answer`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ q_id: parseInt(qId), given_answer: 'skip' })
    }).catch(() => { });

    selectedOption = null;
    nextPracticeQuestion();
}

// ── Navigation ────────────────────────────────
function prevPracticeQuestion() {
    if (currentIdx > 0) {
        selectedOption = null;
        renderQuestion(currentIdx - 1);
    }
}

function nextPracticeQuestion() {
    if (currentIdx < questions.length - 1) {
        selectedOption = null;
        renderQuestion(currentIdx + 1);
    }
}

// ── Progress ──────────────────────────────────
function updateProgress() {
    const answeredCount = Object.keys(answered).length;
    const pct = questions.length > 0 ? Math.round((answeredCount / questions.length) * 100) : 0;

    const fill = document.getElementById('progress-fill');
    if (fill) fill.style.width = pct + '%';

    const pctText = document.getElementById('progress-pct');
    if (pctText) pctText.textContent = pct + '%';
}

function updateAccuracy() {
    const accEl = document.getElementById('accuracy-display');
    if (accEl) {
        const pct = totalAnswered > 0 ? Math.round((totalCorrect / totalAnswered) * 100) : 0;
        accEl.textContent = `Accuracy: ${pct}% (${totalCorrect}/${totalAnswered})`;
    }
}

// ── Finish ────────────────────────────────────
function finishPractice() {
    if (!confirm('Finish this practice session?')) return;

    fetch(`/student/practice/${SESSION_ID}/finish`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
    }).then(r => r.json()).then(d => {
        if (d.redirect) window.location.href = d.redirect;
    }).catch(() => {
        alert('Error finishing practice. Please try again.');
    });
}
