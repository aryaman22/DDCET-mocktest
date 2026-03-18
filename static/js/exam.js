/* ============================================
   DDCET Exam Portal — exam.js  (Production)
   Mobile-safe: fullscreen is OPTIONAL on mobile
   Timer uses server started_at, not localStorage
   ============================================ */

const ATTEMPT_ID       = window.ATTEMPT_ID;
const DURATION_SECONDS = window.DURATION_SECONDS;
let questions    = window.EXAM_QUESTIONS || [];
let savedAnswers = window.SAVED_ANSWERS  || {};

let currentIdx      = 0;
let answers         = { ...savedAnswers };
let markedForReview = {};
let fsExitCount     = 0;
let tabSwitchCount  = 0;
let examStarted     = false;
let timerInterval   = null;
let autoSaveInterval = null;
let sectionFilter   = 'all';

// ── Mobile detection ──────────────────────
const isMobile = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);

// ── Fullscreen helpers ────────────────────
function enterFullscreen() {
    const el = document.documentElement;
    const fn = el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen;
    if (fn) return fn.call(el);
    return Promise.resolve(); // graceful no-op if not supported
}

function exitFullscreen() {
    const fn = document.exitFullscreen || document.webkitExitFullscreen || document.mozCancelFullScreen;
    if (fn) return fn.call(document);
    return Promise.resolve();
}

function isInFullscreen() {
    return !!(document.fullscreenElement || document.webkitFullscreenElement || document.mozFullScreenElement);
}

function canFullscreen() {
    const el = document.documentElement;
    return !!(el.requestFullscreen || el.webkitRequestFullscreen || el.mozRequestFullScreen);
}

// ── Init ──────────────────────────────────
window.addEventListener('load', () => {
    if (isMobile || !canFullscreen()) {
        // Mobile / unsupported: skip fullscreen, start exam directly
        startExamDirectly();
    } else {
        // Desktop: show fullscreen splash
        showFsSplash();
    }
});

function startExamDirectly() {
    examStarted = true;
    startTimer();
    startAutoSave();
    renderQuestion(currentIdx);
    updatePalette();
    updateStats();
}

// ── Fullscreen Splash (desktop only) ─────
function showFsSplash() {
    const splash = document.createElement('div');
    splash.id = 'fs-splash';
    splash.className = 'fs-splash';
    splash.innerHTML = `
        <h2>🖥️ Fullscreen Required</h2>
        <p>This exam requires fullscreen mode. Click below to enter fullscreen and start.</p>
        <button class="btn btn-primary btn-lg" onclick="startExamFullscreen()">
            🖥 Enter Fullscreen & Start Exam
        </button>
        <br><br>
        <button class="btn btn-outline btn-sm" onclick="startExamDirectly(); document.getElementById('fs-splash').remove();" 
                style="opacity:.6; font-size:.8rem;">
            Skip fullscreen (not recommended)
        </button>
    `;
    document.body.appendChild(splash);
}

function startExamFullscreen() {
    enterFullscreen().then(() => {
        // handleFsChange will fire and start exam
    }).catch(() => {
        // If fullscreen denied, start anyway
        const splash = document.getElementById('fs-splash');
        if (splash) splash.remove();
        startExamDirectly();
    });
}

// ── Fullscreen Change Handler (desktop) ──
document.addEventListener('fullscreenchange', handleFsChange);
document.addEventListener('webkitfullscreenchange', handleFsChange);
document.addEventListener('mozfullscreenchange', handleFsChange);

function handleFsChange() {
    if (!isInFullscreen() && examStarted && !isMobile) {
        fsExitCount++;
        showFsBlockingModal(fsExitCount);
        logViolation('fullscreen_exit', fsExitCount);
    } else if (isInFullscreen()) {
        const splash = document.getElementById('fs-splash');
        if (splash) splash.remove();
        removeFsBlockingModal();
        if (!examStarted) {
            startExamDirectly();
        }
    }
}

function showFsBlockingModal(count) {
    removeFsBlockingModal();
    const modal = document.createElement('div');
    modal.id = 'fs-blocking-modal';
    modal.className = 'fs-blocking-modal';
    modal.innerHTML = `
        <div class="warning-icon">⚠️</div>
        <h2>Fullscreen Required</h2>
        <p style="color:var(--muted);max-width:400px;">
            You exited fullscreen <strong>${count}</strong> time(s). This is logged.
            ${count >= 3 ? '<br><span style="color:var(--red);font-weight:600;">⛔ Multiple violations recorded. Your exam is flagged.</span>' : ''}
        </p>
        <button class="btn btn-primary btn-lg" onclick="enterFullscreen()" style="margin-top:20px;">
            🖥 Return to Fullscreen
        </button>
    `;
    document.body.appendChild(modal);
}

function removeFsBlockingModal() {
    const m = document.getElementById('fs-blocking-modal');
    if (m) m.remove();
}

// ── sendBeacon submit — fires reliably on ALL exit scenarios ──
// sendBeacon is the ONLY reliable way to submit on page close.
// fetch() gets cancelled. beforeunload warning alone doesn't submit.
function sendBeaconSubmit() {
    if (!examStarted) return;
    const payload = JSON.stringify({ answers });
    if (navigator.sendBeacon) {
        navigator.sendBeacon(`/student/exam/${ATTEMPT_ID}/beacon_submit`, payload);
    }
}

// pagehide: fires on mobile (iOS/Android) when tab closes or app backgrounds
// More reliable than beforeunload on mobile
window.addEventListener('pagehide', sendBeaconSubmit);

// beforeunload: fires on desktop when tab/browser is closed or refreshed
window.addEventListener('beforeunload', (e) => {
    if (examStarted) {
        sendBeaconSubmit();
        e.preventDefault();
        e.returnValue = 'Exam in progress. Leaving will auto-submit your exam.';
        return e.returnValue;
    }
});

// ── Tab Visibility ────────────────────────
document.addEventListener('visibilitychange', () => {
    if (document.hidden && examStarted) {
        tabSwitchCount++;
        logViolation('tab_switch', tabSwitchCount);
        showTabSwitchBanner();
        saveAnswers(); // extra safety save when backgrounded
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
    setTimeout(() => { const b = document.getElementById('tab-switch-banner'); if (b) b.remove(); }, 4000);
}

// ── Security ──────────────────────────────
document.addEventListener('contextmenu', e => e.preventDefault());
document.addEventListener('keydown', e => {
    if (e.key === 'F11') { e.preventDefault(); e.stopPropagation(); }
    if (e.ctrlKey && ['w','W','t','T','n','N'].includes(e.key)) e.preventDefault();
    if (e.ctrlKey && e.shiftKey && e.key === 'I') e.preventDefault();
});

// ── Logout Handler ────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('a[href*="/auth/logout"]').forEach(link => {
        link.addEventListener('click', (e) => {
            if (!examStarted) return;
            e.preventDefault();
            const logoutUrl = link.href;
            if (!confirm('Logging out will auto-submit your exam. Are you sure?')) return;
            clearInterval(timerInterval);
            clearInterval(autoSaveInterval);
            fetch(`/student/exam/${ATTEMPT_ID}/submit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ answers })
            }).finally(() => {
                window.onbeforeunload = null;
                window.location.href = logoutUrl;
            });
        });
    });
});

// ── Violation Log ─────────────────────────
function logViolation(event, count) {
    fetch(`/student/exam/${ATTEMPT_ID}/log`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event, count })
    }).catch(() => {});
}

// ── Timer ─────────────────────────────────
// Uses DURATION_SECONDS from server (remaining time, not full duration)
// This is already correctly set by the server to account for elapsed time
function startTimer() {
    const timerEl = document.getElementById('timer-display');
    if (!timerEl) return;

    let remaining = DURATION_SECONDS;

    timerInterval = setInterval(() => {
        remaining--;

        if (remaining <= 0) {
            clearInterval(timerInterval);
            timerEl.textContent = '00:00:00';
            autoSubmit();
            return;
        }

        const h = Math.floor(remaining / 3600);
        const m = Math.floor((remaining % 3600) / 60);
        const s = remaining % 60;
        const timeStr = `${String(h).padStart(2,'0')}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
        timerEl.textContent = timeStr;

        timerEl.classList.remove('warning', 'danger');
        if (remaining <= 300)      timerEl.classList.add('danger');
        else if (remaining <= 900) timerEl.classList.add('warning');
    }, 1000);
}

function autoSubmit() {
    submitExam(true);
}

// ── Auto-Save ─────────────────────────────
function startAutoSave() {
    autoSaveInterval = setInterval(saveAnswers, 30000); // every 30s
}

function saveAnswers() {
    fetch(`/student/exam/${ATTEMPT_ID}/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers })
    }).then(r => r.json()).then(d => {
        if (d.saved_at) {
            const el = document.getElementById('save-status');
            if (el) el.textContent = `Saved: ${d.saved_at}`;
        }
    }).catch(() => {});
}

// ── Question Rendering ────────────────────
function renderQuestion(idx) {
    if (idx < 0 || idx >= questions.length) return;
    currentIdx = idx;
    const q = questions[idx];
    const qId = q.id;
    const selectedAns = answers[qId] || '';
    const isMarked = markedForReview[qId] || false;

    const container = document.getElementById('question-container');
    if (!container) return;

    container.innerHTML = `
        <div class="question-card">
            <div class="question-header">
                <span class="question-number">Q ${q.qno_display} / ${questions.length}</span>
                <span class="badge badge-muted">Section ${q.section}</span>
                <span class="badge badge-muted">${q.topic}</span>
                ${isMarked ? '<span class="badge badge-warning">🔖 Marked</span>' : ''}
            </div>
            <div class="question-text">${q.question}</div>
            <div class="options-list">
                ${['A','B','C','D'].map(opt => {
                    const text = q[`option_${opt.toLowerCase()}`];
                    const sel = selectedAns === opt;
                    return `<button class="option-btn ${sel ? 'selected' : ''}"
                                onclick="selectOption('${qId}','${opt}')">
                        <span class="option-label">${opt}</span>
                        <span class="option-text">${text}</span>
                    </button>`;
                }).join('')}
            </div>
            <div class="question-actions">
                <div class="btn-group">
                    <button class="btn btn-outline btn-sm" onclick="prevQuestion()" ${idx===0?'disabled':''}>← Prev</button>
                    <button class="btn ${isMarked?'btn-warning':'btn-outline'} btn-sm" onclick="markForReview('${qId}')">
                        🔖 ${isMarked?'Unmark':'Mark'}
                    </button>
                    <button class="btn btn-outline btn-sm" onclick="clearAnswer('${qId}')">✕ Clear</button>
                </div>
                <button class="btn btn-primary btn-sm" onclick="nextQuestion()" ${idx===questions.length-1?'disabled':''}>Next →</button>
            </div>
        </div>`;

    updatePalette();
    updateStats();

    // Mobile: scroll to top of question on navigation
    if (isMobile) window.scrollTo({ top: 0, behavior: 'smooth' });
}

function selectOption(qId, opt) {
    answers[qId] = opt;
    renderQuestion(currentIdx);
    saveAnswers(); // save on every answer change
}

function clearAnswer(qId) {
    delete answers[qId];
    renderQuestion(currentIdx);
}

function markForReview(qId) {
    markedForReview[qId] = !markedForReview[qId];
    renderQuestion(currentIdx);
    updatePalette();
}

function prevQuestion() {
    if (sectionFilter !== 'all') {
        for (let i = currentIdx - 1; i >= 0; i--) {
            if (String(questions[i].section) === sectionFilter) { renderQuestion(i); return; }
        }
    } else if (currentIdx > 0) {
        renderQuestion(currentIdx - 1);
    }
}

function nextQuestion() {
    if (sectionFilter !== 'all') {
        for (let i = currentIdx + 1; i < questions.length; i++) {
            if (String(questions[i].section) === sectionFilter) { renderQuestion(i); return; }
        }
    } else if (currentIdx < questions.length - 1) {
        renderQuestion(currentIdx + 1);
    }
}

function goToQuestion(idx) {
    renderQuestion(idx);
    // Mobile: close palette drawer after selecting
    if (isMobile) {
        const sidebar = document.getElementById('examSidebar');
        if (sidebar) sidebar.classList.remove('drawer-open');
    }
}

// ── Palette ───────────────────────────────
function updatePalette() {
    const palette = document.getElementById('question-palette');
    if (!palette) return;
    palette.innerHTML = questions.map((q, i) => {
        let cls = 'palette-btn';
        if (i === currentIdx)       cls += ' current';
        if (answers[q.id])          cls += ' answered';
        if (markedForReview[q.id])  cls += ' marked';
        if (sectionFilter !== 'all' && String(q.section) !== sectionFilter) cls += ' hidden-palette';
        return `<button class="${cls}" onclick="goToQuestion(${i})" title="Q${q.qno_display}">${q.qno_display}</button>`;
    }).join('');
}

// ── Stats ─────────────────────────────────
function updateStats() {
    const answered   = Object.keys(answers).length;
    const unanswered = questions.length - answered;
    const marked     = Object.values(markedForReview).filter(Boolean).length;

    const set = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = v; };
    set('stat-answered',   answered);
    set('stat-unanswered', unanswered);
    set('stat-marked',     marked);
    set('stat-total',      questions.length);
    set('nav-progress',    `Q${currentIdx+1}/${questions.length}`);
    // Sync mobile bar
    set('mob-answered',   answered);
    set('mob-unanswered', unanswered);
}

// ── Section Filter ────────────────────────
function filterSection(sec) {
    sectionFilter = sec;
    document.querySelectorAll('.section-tab').forEach(t => t.classList.remove('active'));
    document.querySelector(`[data-section="${sec}"]`)?.classList.add('active');
    updatePalette();
    if (sec !== 'all') {
        for (let i = 0; i < questions.length; i++) {
            if (String(questions[i].section) === sec) { renderQuestion(i); return; }
        }
    }
}

// ── Submit ────────────────────────────────
function showSubmitModal() {
    const answered = Object.keys(answers).length;
    const total    = questions.length;
    const overlay  = document.createElement('div');
    overlay.id = 'submit-modal';
    overlay.className = 'modal-overlay';
    overlay.innerHTML = `
        <div class="modal">
            <h3>📝 Submit Exam?</h3>
            <p>Answered: <strong>${answered}</strong> / <strong>${total}</strong>
            ${total - answered > 0 ? `<br><span style="color:var(--yellow);">${total - answered} unanswered questions.</span>` : ' ✅ All answered!'}</p>
            <div class="modal-actions">
                <button class="btn btn-outline" onclick="closeSubmitModal()">Continue Exam</button>
                <button class="btn btn-danger" onclick="submitExam(false)">Confirm Submit</button>
            </div>
        </div>`;
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

    const container = document.getElementById('question-container');
    if (container) {
        container.innerHTML = `
            <div class="empty-state" style="padding:60px 20px;">
                <div class="empty-icon">⏳</div>
                <h3>Submitting your exam...</h3>
                <p class="text-muted">Please don't close this page.</p>
            </div>`;
    }

    fetch(`/student/exam/${ATTEMPT_ID}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ answers })
    }).then(r => r.json()).then(d => {
        if (d.ok && d.redirect) {
            window.onbeforeunload = null;
            if (isInFullscreen()) {
                exitFullscreen().finally(() => { window.location.href = d.redirect; });
            } else {
                window.location.href = d.redirect;
            }
        } else {
            if (container) container.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">❌</div>
                    <h3>Submission failed</h3>
                    <p>Your answers are saved. <button class="btn btn-primary btn-sm" onclick="submitExam(false)">Try Again</button></p>
                </div>`;
        }
    }).catch(() => {
        // Network error — retry once after 3s
        setTimeout(() => submitExam(isTimeout), 3000);
        if (container) container.innerHTML += `<p class="text-muted" style="text-align:center;margin-top:12px;">Network issue — retrying...</p>`;
    });
}

// ── Mobile drawer toggle ──────────────────
function toggleDrawer() {
    const sidebar = document.getElementById('examSidebar');
    if (sidebar) sidebar.classList.toggle('drawer-open');
}