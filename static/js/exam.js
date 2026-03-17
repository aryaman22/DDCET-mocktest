/* ============================================
   DDCET Exam Portal — exam.js
   Fullscreen lock, timer, palette, auto-save
   EXAM MODE ONLY
   ============================================ */

const ATTEMPT_ID = window.ATTEMPT_ID;
const DURATION_SECONDS = window.DURATION_SECONDS;
let questions = window.EXAM_QUESTIONS || [];
let savedAnswers = window.SAVED_ANSWERS || {};

let currentIdx = 0;
let answers = { ...savedAnswers };
let markedForReview = {};
let fsExitCount = 0;
let tabSwitchCount = 0;
let examStarted = false;
let timerInterval = null;
let autoSaveInterval = null;
let sectionFilter = 'all';

// ── Fullscreen ──────────────────────────────
function enterFullscreen() {
    const el = document.documentElement;
    if (el.requestFullscreen) return el.requestFullscreen();
    if (el.webkitRequestFullscreen) return el.webkitRequestFullscreen();
    if (el.mozRequestFullScreen) return el.mozRequestFullScreen();
    return Promise.resolve();
}

function exitFullscreen() {
    if (document.exitFullscreen) return document.exitFullscreen();
    if (document.webkitExitFullscreen) return document.webkitExitFullscreen();
    if (document.mozCancelFullScreen) return document.mozCancelFullScreen();
}

function isInFullscreen() {
    return !!(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement);
}

// ── Splash Screen ────────────────────────────
window.addEventListener('load', () => {
    showFsSplash();
});

function showFsSplash() {
    const splash = document.createElement('div');
    splash.id = 'fs-splash';
    splash.className = 'fs-splash';
    splash.innerHTML = `
        <h2>🖥️ Fullscreen Required</h2>
        <p>This exam requires fullscreen mode. Click the button below to enter fullscreen and start your exam.</p>
        <button class="btn btn-primary btn-lg" onclick="startExamFullscreen()">
            🖥 Enter Fullscreen & Start Exam
        </button>
    `;
    document.body.appendChild(splash);
}

function startExamFullscreen() {
    enterFullscreen().then(() => {
        // Splash will be removed by handleFsChange when fullscreen is confirmed
    }).catch(() => {
        // Don't remove splash - keep blocking until fullscreen succeeds
        alert('Fullscreen is required for this exam. Please allow fullscreen mode and try again.');
    });
}

// ── Fullscreen Change Handler ────────────────
document.addEventListener('fullscreenchange', handleFsChange);
document.addEventListener('webkitfullscreenchange', handleFsChange);
document.addEventListener('mozfullscreenchange', handleFsChange);

function handleFsChange() {
    if (!isInFullscreen() && examStarted) {
        fsExitCount++;
        showFsBlockingModal(fsExitCount);
        logViolation('fullscreen_exit', fsExitCount);
    } else if (isInFullscreen()) {
        // Remove splash screen if present
        const splash = document.getElementById('fs-splash');
        if (splash) splash.remove();
        removeFsBlockingModal();
        if (!examStarted) {
            examStarted = true;
            startTimer();
            startAutoSave();
            renderQuestion(currentIdx);
            updatePalette();
            updateStats();
        }
    }
}

function showFsBlockingModal(count) {
    removeFsBlockingModal();
    const modal = document.createElement('div');
    modal.id = 'fs-blocking-modal';
    modal.className = 'fs-blocking-modal';

    let warningExtra = '';
    if (count >= 3) {
        warningExtra = '<p style="color: var(--red); font-weight: 600; margin-top: 12px;">⛔ Warning: Multiple violations recorded. Your exam is flagged.</p>';
    }

    modal.innerHTML = `
        <div class="warning-icon">⚠️</div>
        <h2>Fullscreen Required</h2>
        <p style="color: var(--muted); max-width: 400px;">You have exited fullscreen <strong>${count}</strong> time(s). This has been logged.</p>
        ${warningExtra}
        <button class="btn btn-primary btn-lg" onclick="enterFullscreen()" style="margin-top: 20px;">
            🖥 Return to Fullscreen
        </button>
    `;
    document.body.appendChild(modal);
}

function removeFsBlockingModal() {
    const m = document.getElementById('fs-blocking-modal');
    if (m) m.remove();
}

// ── Tab Visibility ────────────────────────────
document.addEventListener('visibilitychange', () => {
    if (document.hidden && examStarted) {
        tabSwitchCount++;
        logViolation('tab_switch', tabSwitchCount);
        showTabSwitchBanner();
    }
});

function showTabSwitchBanner() {
    const existing = document.getElementById('tab-switch-banner');
    if (existing) existing.remove();

    const banner = document.createElement('div');
    banner.id = 'tab-switch-banner';
    banner.className = 'tab-switch-banner';
    banner.textContent = `⚠ Tab switch detected and logged (${tabSwitchCount} total)`;
    document.body.appendChild(banner);

    setTimeout(() => {
        const b = document.getElementById('tab-switch-banner');
        if (b) b.remove();
    }, 4000);
}

// ── Security ──────────────────────────────────
document.addEventListener('contextmenu', e => e.preventDefault());
document.addEventListener('keydown', e => {
    if (e.key === 'F11') { e.preventDefault(); e.stopPropagation(); }
    if (e.ctrlKey && ['w', 'W', 't', 'T', 'n', 'N'].includes(e.key)) e.preventDefault();
    if (e.ctrlKey && e.shiftKey && e.key === 'I') e.preventDefault();
});

// ── Beforeunload Warning ──────────────────────
window.addEventListener('beforeunload', (e) => {
    if (examStarted) {
        e.preventDefault();
        e.returnValue = 'You have an exam in progress. Your exam will be auto-submitted if you leave.';
        return e.returnValue;
    }
});

// ── Logout Handler (submit exam first) ────────
document.addEventListener('DOMContentLoaded', () => {
    const logoutLinks = document.querySelectorAll('a[href*="/auth/logout"]');
    logoutLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            if (!examStarted) return; // Let normal logout happen
            e.preventDefault();
            const logoutUrl = link.href;

            if (!confirm('Logging out will auto-submit your exam. Are you sure?')) return;

            // Submit exam then logout
            clearInterval(timerInterval);
            clearInterval(autoSaveInterval);

            fetch(`/student/exam/${ATTEMPT_ID}/submit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ answers })
            }).then(() => {
                localStorage.removeItem(`exam_start_${ATTEMPT_ID}`);
                window.removeEventListener('beforeunload', () => { });
                window.onbeforeunload = null;
                window.location.href = logoutUrl;
            }).catch(() => {
                // Even if submit fails, logout (server-side will auto-submit)
                window.onbeforeunload = null;
                window.location.href = logoutUrl;
            });
        });
    });
});

// ── Violation Log ─────────────────────────────
function logViolation(event, count) {
    fetch(`/student/exam/${ATTEMPT_ID}/log`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event, count })
    }).catch(() => { });
}

// ── Timer ─────────────────────────────────────
function startTimer() {
    const storageKey = `exam_start_${ATTEMPT_ID}`;
    let startTime = localStorage.getItem(storageKey);
    if (!startTime) {
        startTime = Date.now().toString();
        localStorage.setItem(storageKey, startTime);
    }
    startTime = parseInt(startTime);

    const timerEl = document.getElementById('timer-display');
    if (!timerEl) return;

    timerInterval = setInterval(() => {
        const elapsed = Math.floor((Date.now() - startTime) / 1000);
        const remaining = DURATION_SECONDS - elapsed;

        if (remaining <= 0) {
            clearInterval(timerInterval);
            timerEl.textContent = '00:00:00';
            autoSubmit();
            return;
        }

        const h = Math.floor(remaining / 3600);
        const m = Math.floor((remaining % 3600) / 60);
        const s = remaining % 60;
        timerEl.textContent = `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;

        // Color changes
        timerEl.classList.remove('warning', 'danger');
        if (remaining <= 300) {
            timerEl.classList.add('danger');
        } else if (remaining <= 900) {
            timerEl.classList.add('warning');
        }
    }, 1000);
}

function autoSubmit() {
    submitExam(true);
}

// ── Auto-Save ─────────────────────────────────
function startAutoSave() {
    autoSaveInterval = setInterval(() => {
        saveAnswers();
    }, 30000);
}

function saveAnswers() {
    fetch(`/student/exam/${ATTEMPT_ID}/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers })
    }).then(r => r.json()).then(d => {
        if (d.saved_at) {
            const saveStatus = document.getElementById('save-status');
            if (saveStatus) saveStatus.textContent = `Saved: ${d.saved_at}`;
        }
    }).catch(() => { });
}

// ── Question Rendering ────────────────────────
function renderQuestion(idx) {
    if (idx < 0 || idx >= questions.length) return;
    currentIdx = idx;
    const q = questions[idx];
    const qId = q.id;

    const container = document.getElementById('question-container');
    if (!container) return;

    const selectedAns = answers[qId] || '';
    const isMarked = markedForReview[qId] || false;

    container.innerHTML = `
        <div class="question-header">
            <span class="question-number">Q ${q.qno_display} / ${questions.length}</span>
            <span class="badge badge-muted">Section ${q.section}</span>
            <span class="badge badge-muted">${q.topic}</span>
            ${isMarked ? '<span class="badge badge-warning">🔖 Marked</span>' : ''}
        </div>
        <div class="question-text">${q.question}</div>
        <div class="options-list">
            ${['A', 'B', 'C', 'D'].map(opt => {
        const optKey = `option_${opt.toLowerCase()}`;
        const isSelected = selectedAns === opt;
        return `<button class="option-btn ${isSelected ? 'selected' : ''}" onclick="selectOption('${qId}', '${opt}')">
                    <span class="option-label">${opt}</span>
                    <span class="option-text">${q[optKey]}</span>
                </button>`;
    }).join('')}
        </div>
        <div class="question-actions">
            <div class="btn-group">
                <button class="btn btn-outline btn-sm" onclick="prevQuestion()" ${idx === 0 ? 'disabled' : ''}>← Prev</button>
                <button class="btn ${isMarked ? 'btn-warning' : 'btn-outline'} btn-sm" onclick="markForReview('${qId}')">🔖 ${isMarked ? 'Unmark' : 'Mark'}</button>
                <button class="btn btn-outline btn-sm" onclick="clearAnswer('${qId}')">✕ Clear</button>
            </div>
            <button class="btn btn-primary btn-sm" onclick="nextQuestion()" ${idx === questions.length - 1 ? 'disabled' : ''}>Next →</button>
        </div>
    `;

    updatePalette();
}

function selectOption(qId, opt) {
    answers[qId] = opt;
    renderQuestion(currentIdx);
    updateStats();
    // Save on every answer
    saveAnswers();
}

function clearAnswer(qId) {
    delete answers[qId];
    renderQuestion(currentIdx);
    updateStats();
}

function markForReview(qId) {
    markedForReview[qId] = !markedForReview[qId];
    renderQuestion(currentIdx);
}

function prevQuestion() {
    if (currentIdx > 0) {
        if (sectionFilter !== 'all') {
            let i = currentIdx - 1;
            while (i >= 0) {
                if (String(questions[i].section) === sectionFilter) {
                    renderQuestion(i);
                    return;
                }
                i--;
            }
        } else {
            renderQuestion(currentIdx - 1);
        }
    }
}

function nextQuestion() {
    if (currentIdx < questions.length - 1) {
        if (sectionFilter !== 'all') {
            let i = currentIdx + 1;
            while (i < questions.length) {
                if (String(questions[i].section) === sectionFilter) {
                    renderQuestion(i);
                    return;
                }
                i++;
            }
        } else {
            renderQuestion(currentIdx + 1);
        }
    }
}

function goToQuestion(idx) {
    renderQuestion(idx);
}

// ── Palette ───────────────────────────────────
function updatePalette() {
    const palette = document.getElementById('question-palette');
    if (!palette) return;

    palette.innerHTML = questions.map((q, i) => {
        let cls = 'palette-btn';
        if (i === currentIdx) cls += ' current';
        if (answers[q.id]) cls += ' answered';
        if (markedForReview[q.id]) cls += ' marked';
        if (sectionFilter !== 'all' && String(q.section) !== sectionFilter) {
            cls += ' hidden-palette';
        }
        return `<button class="${cls}" onclick="goToQuestion(${i})" title="Q${q.qno_display}">${q.qno_display}</button>`;
    }).join('');
}

// ── Stats ─────────────────────────────────────
function updateStats() {
    const answered = Object.keys(answers).length;
    const unanswered = questions.length - answered;
    const marked = Object.values(markedForReview).filter(Boolean).length;

    const el = (id, val) => {
        const e = document.getElementById(id);
        if (e) e.textContent = val;
    };

    el('stat-answered', answered);
    el('stat-unanswered', unanswered);
    el('stat-marked', marked);
    el('stat-total', questions.length);
    el('nav-progress', `Q${currentIdx + 1}/${questions.length}`);
}

// ── Section Filter ────────────────────────────
function filterSection(sec) {
    sectionFilter = sec;
    document.querySelectorAll('.section-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-section="${sec}"]`)?.classList.add('active');
    updatePalette();

    // Jump to first question of that section
    if (sec !== 'all') {
        for (let i = 0; i < questions.length; i++) {
            if (String(questions[i].section) === sec) {
                renderQuestion(i);
                return;
            }
        }
    }
}

// ── Submit ────────────────────────────────────
function showSubmitModal() {
    const answered = Object.keys(answers).length;
    const total = questions.length;

    const overlay = document.createElement('div');
    overlay.id = 'submit-modal';
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
        <div class="modal">
            <h3>📝 Submit Exam?</h3>
            <p>You have answered <strong>${answered}</strong> out of <strong>${total}</strong> questions.
            ${total - answered > 0 ? `<br><span style="color: var(--yellow);">${total - answered} questions are unanswered.</span>` : ''}
            </p>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="closeSubmitModal()">Continue Exam</button>
                <button class="btn btn-danger" onclick="submitExam(false)">Confirm Submit</button>
            </div>
        </div>
    `;
    document.body.appendChild(overlay);
}

function closeSubmitModal() {
    const m = document.getElementById('submit-modal');
    if (m) m.remove();
}

function submitExam(isTimeout) {
    clearInterval(timerInterval);
    clearInterval(autoSaveInterval);
    closeSubmitModal();

    // Show loading
    const container = document.getElementById('question-container');
    if (container) {
        container.innerHTML = '<div class="empty-state"><div class="empty-icon">⏳</div><h3>Submitting exam...</h3></div>';
    }

    fetch(`/student/exam/${ATTEMPT_ID}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers })
    }).then(r => r.json()).then(d => {
        if (d.ok && d.redirect) {
            // Clean up localStorage
            localStorage.removeItem(`exam_start_${ATTEMPT_ID}`);
            // Exit fullscreen
            if (isInFullscreen()) {
                exitFullscreen().then(() => {
                    window.location.href = d.redirect;
                }).catch(() => {
                    window.location.href = d.redirect;
                });
            } else {
                window.location.href = d.redirect;
            }
        } else {
            alert('Error submitting exam. Please try again.');
        }
    }).catch(err => {
        console.error('Submit error:', err);
        alert('Network error. Your answers have been saved. Please try submitting again.');
    });
}
