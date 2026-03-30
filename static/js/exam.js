/* ════════════════════════════════════════════════════════
   DDCET Portal — exam.js v2.0
   Live exam interface logic
   ════════════════════════════════════════════════════════ */

(function () {
    'use strict';

    const questions = window.EXAM_QUESTIONS || [];
    const attemptId = window.ATTEMPT_ID;
    const savedAnswers = window.SAVED_ANSWERS || {};
    let timeLeft = window.TIME_LEFT || 0;
    const csrf = window.CSRF_TOKEN;

    let currentIndex = 0;
    let answers = {};        // { qIndex: 'A'/'B'/'C'/'D' }
    let marked = new Set();  // set of qIndex
    let timerInterval;

    // Restore saved answers
    if (savedAnswers) {
        questions.forEach((q, i) => {
            const key = String(q.q_id || q.id);
            if (savedAnswers[key]) answers[i] = savedAnswers[key];
        });
    }

    // ── Render question ──────────────────────────────
    function renderQuestion(idx) {
        currentIndex = idx;
        const q = questions[idx];
        if (!q) return;

        document.getElementById('q-counter').textContent = `Q ${idx + 1} / ${questions.length}`;
        document.getElementById('q-section').textContent = q.section ? `Section ${q.section}` : '';
        document.getElementById('q-topic').textContent = q.topic || '';
        document.getElementById('question-text').textContent = q.question;

        const optContainer = document.getElementById('options-container');
        optContainer.innerHTML = '';
        ['A', 'B', 'C', 'D'].forEach(opt => {
            const btn = document.createElement('button');
            btn.className = 'option-btn' + (answers[idx] === opt ? ' selected' : '');
            btn.innerHTML = `<span class="option-label">${opt}</span><span class="option-text">${q['option_' + opt.toLowerCase()]}</span>`;
            btn.onclick = () => selectOption(idx, opt);
            optContainer.appendChild(btn);
        });

        // Nav buttons
        document.getElementById('btn-prev').disabled = idx === 0;
        document.getElementById('btn-next').textContent = idx === questions.length - 1 ? 'Finish' : 'Next →';
        document.getElementById('btn-mark').textContent = marked.has(idx) ? '⚑ Unmark' : '⚑ Mark';

        updatePalette();
        updateStats();
    }

    function selectOption(idx, opt) {
        answers[idx] = opt;
        renderQuestion(idx);
    }

    window.nextQuestion = function () {
        if (currentIndex < questions.length - 1) renderQuestion(currentIndex + 1);
    };
    window.prevQuestion = function () {
        if (currentIndex > 0) renderQuestion(currentIndex - 1);
    };
    window.markForReview = function () {
        if (marked.has(currentIndex)) marked.delete(currentIndex);
        else marked.add(currentIndex);
        document.getElementById('btn-mark').textContent = marked.has(currentIndex) ? '⚑ Unmark' : '⚑ Mark';
        updatePalette();
        updateStats();
    };
    window.clearAnswer = function () {
        delete answers[currentIndex];
        renderQuestion(currentIndex);
    };

    // ── Palette ──────────────────────────────────────
    function buildPalette(containerId) {
        const grid = document.getElementById(containerId);
        if (!grid) return;
        grid.innerHTML = '';
        questions.forEach((q, i) => {
            const btn = document.createElement('button');
            btn.className = 'palette-btn';
            if (answers[i] !== undefined) btn.classList.add('answered');
            if (marked.has(i)) btn.classList.add('marked');
            if (i === currentIndex) btn.classList.add('current');
            btn.textContent = i + 1;
            btn.onclick = () => { renderQuestion(i); closePaletteSheet(); };
            grid.appendChild(btn);
        });
    }
    function updatePalette() {
        buildPalette('palette-grid');
        buildPalette('mobile-palette-grid');
    }

    // ── Stats ─────────────────────────────────────────
    function updateStats() {
        const answered = Object.keys(answers).length;
        const unanswered = questions.length - answered;
        const markedCount = marked.size;
        ['stat', 'm-stat'].forEach(prefix => {
            const el1 = document.getElementById(`${prefix}-answered`);
            const el2 = document.getElementById(`${prefix}-unanswered`);
            const el3 = document.getElementById(`${prefix}-marked`);
            if (el1) el1.textContent = answered;
            if (el2) el2.textContent = unanswered;
            if (el3) el3.textContent = markedCount;
        });
    }

    // ── Timer ─────────────────────────────────────────
    function startTimer() {
        const timerBox = document.getElementById('timer-box');
        const timerDisplay = document.getElementById('timer-display');
        const timerMini = document.getElementById('timer-mini');

        timerInterval = setInterval(() => {
            timeLeft--;
            if (timeLeft <= 0) { clearInterval(timerInterval); doSubmit(); return; }

            const h = Math.floor(timeLeft / 3600);
            const m = Math.floor((timeLeft % 3600) / 60);
            const s = timeLeft % 60;
            const display = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
            if (timerDisplay) timerDisplay.textContent = display;
            if (timerMini) timerMini.textContent = display;

            // Color changes
            if (timerBox) {
                timerBox.classList.remove('warning', 'danger');
                if (timeLeft <= 300) { timerBox.classList.add('danger'); timerDisplay?.classList.add('pulse'); }
                else if (timeLeft <= 900) timerBox.classList.add('warning');
            }
        }, 1000);
    }

    // ── Mobile palette sheet ──────────────────────────
    window.togglePaletteSheet = function () {
        document.getElementById('palette-sheet')?.classList.toggle('open');
        document.getElementById('palette-overlay')?.classList.toggle('open');
    };
    function closePaletteSheet() {
        document.getElementById('palette-sheet')?.classList.remove('open');
        document.getElementById('palette-overlay')?.classList.remove('open');
    }

    // ── Auto-save ─────────────────────────────────────
    function buildAnswerPayload() {
        const payload = {};
        questions.forEach((q, i) => {
            const key = String(q.q_id || q.id);
            if (answers[i]) payload[key] = answers[i];
        });
        return payload;
    }

    function autoSave() {
        fetch(`/student/exam/${attemptId}/save`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
            body: JSON.stringify({ answers: buildAnswerPayload() })
        }).catch(() => { });
    }
    setInterval(autoSave, 30000);

    // ── Submit ────────────────────────────────────────
    window.confirmSubmit = function () {
        const answered = Object.keys(answers).length;
        const unanswered = questions.length - answered;
        document.getElementById('submit-summary').innerHTML =
            `<p>You have answered <strong>${answered}</strong> of <strong>${questions.length}</strong> questions.</p>` +
            (unanswered > 0 ? `<p style="color:var(--yellow);margin-top:8px">⚠️ ${unanswered} questions are unanswered!</p>` : '') +
            `<p style="margin-top:8px">Are you sure you want to submit?</p>`;
        document.getElementById('submit-modal').classList.add('open');
    };
    window.closeSubmitModal = function () {
        document.getElementById('submit-modal').classList.remove('open');
    };
    window.doSubmit = function () {
        clearInterval(timerInterval);
        fetch(`/student/exam/${attemptId}/submit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
            body: JSON.stringify({ answers: buildAnswerPayload() })
        })
            .then(r => r.json())
            .then(data => { window.location.href = data.redirect || `/student/result/${attemptId}`; })
            .catch(() => { window.location.href = `/student/result/${attemptId}`; });
    };

    // ── Beacon submit on page unload ──────────────────
    window.addEventListener('beforeunload', () => {
        const payload = JSON.stringify({ answers: buildAnswerPayload() });
        navigator.sendBeacon(`/student/exam/${attemptId}/beacon_submit`, payload);
    });

    // ── Violation logging ─────────────────────────────
    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            fetch(`/student/exam/${attemptId}/violation`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                body: JSON.stringify({ type: 'tab_switch' })
            }).catch(() => { });
        }
    });

    // ── Fullscreen ────────────────────────────────────
    function enterFullscreen() {
        const el = document.documentElement;
        if (el.requestFullscreen) el.requestFullscreen();
        else if (el.webkitRequestFullscreen) el.webkitRequestFullscreen();
    }

    document.addEventListener('fullscreenchange', () => {
        if (!document.fullscreenElement) {
            fetch(`/student/exam/${attemptId}/violation`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf },
                body: JSON.stringify({ type: 'fullscreen_exit' })
            }).catch(() => { });
        }
    });

    // Disable right click
    document.addEventListener('contextmenu', e => e.preventDefault());

    // ── Init ──────────────────────────────────────────
    window.startExamNow = function () {
        const overlay = document.getElementById('start-overlay');
        if (overlay) overlay.classList.remove('open');

        enterFullscreen();
        renderQuestion(0);
        startTimer();
    };
})();