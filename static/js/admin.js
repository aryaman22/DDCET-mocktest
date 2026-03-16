/* ============================================
   DDCET Exam Portal — admin.js
   Admin UI helpers: config form, topic loading
   ============================================ */

document.addEventListener('DOMContentLoaded', () => {
    initConfigForm();
    initTabs();
    initBulkSelect();
    initDeleteConfirm();
});

// ── Config Form Mode Toggle ──────────────────
function initConfigForm() {
    const modeSelect = document.getElementById('config-mode');
    if (!modeSelect) return;

    modeSelect.addEventListener('change', handleModeChange);
    handleModeChange(); // initial state

    // Bank selection → load topics
    const bankCheckboxes = document.querySelectorAll('.bank-checkbox');
    bankCheckboxes.forEach(cb => {
        cb.addEventListener('change', loadTopics);
    });

    // Initial topic load if banks are pre-selected
    const selectedBanks = document.querySelectorAll('.bank-checkbox:checked');
    if (selectedBanks.length > 0) {
        loadTopics();
    }
}

function handleModeChange() {
    const modeSelect = document.getElementById('config-mode');
    if (!modeSelect) return;

    const mode = modeSelect.value;
    const examFields = document.getElementById('exam-only-fields');
    const modeInfo = document.getElementById('mode-info');
    const reattemptCb = document.getElementById('allow-reattempt');

    if (mode === 'practice') {
        if (examFields) examFields.style.display = 'none';
        if (modeInfo) {
            modeInfo.className = 'info-box info-box-blue';
            modeInfo.innerHTML = 'ℹ️ Practice mode: No timer, no negative marking, instant answer feedback.';
            modeInfo.style.display = 'flex';
        }
        if (reattemptCb) reattemptCb.checked = true;
    } else {
        if (examFields) examFields.style.display = 'block';
        if (modeInfo) {
            modeInfo.className = 'info-box info-box-yellow';
            modeInfo.innerHTML = '⚠️ Exam mode: Timed, fullscreen-locked, negative marking applies.';
            modeInfo.style.display = 'flex';
        }
        if (reattemptCb) reattemptCb.checked = false;
    }
}

function loadTopics() {
    const selectedBanks = [];
    document.querySelectorAll('.bank-checkbox:checked').forEach(cb => {
        selectedBanks.push(cb.value);
    });

    const topicContainer = document.getElementById('topic-checkboxes');
    if (!topicContainer) return;

    if (selectedBanks.length === 0) {
        topicContainer.innerHTML = '<p class="text-muted">Select banks first to see available topics.</p>';
        return;
    }

    topicContainer.innerHTML = '<p class="text-muted">Loading topics...</p>';

    fetch(`/admin/api/topics?bank_ids=${selectedBanks.join(',')}`)
        .then(r => r.json())
        .then(data => {
            if (data.topics && data.topics.length > 0) {
                const selectedTopics = window.SELECTED_TOPICS || [];
                topicContainer.innerHTML = data.topics.map(t => `
                    <div class="form-check">
                        <input type="checkbox" name="topic_filter" value="${t}" class="topic-checkbox"
                               ${selectedTopics.includes(t) ? 'checked' : ''}>
                        <label>${t}</label>
                    </div>
                `).join('');
            } else {
                topicContainer.innerHTML = '<p class="text-muted">No topics found in selected banks.</p>';
            }
        })
        .catch(() => {
            topicContainer.innerHTML = '<p class="text-muted">Error loading topics.</p>';
        });
}

// ── Tabs ──────────────────────────────────────
function initTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const target = btn.dataset.tab;
            // Deactivate all
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            // Activate
            btn.classList.add('active');
            const targetEl = document.getElementById(target);
            if (targetEl) targetEl.classList.add('active');
        });
    });
}

// ── Bulk Select ───────────────────────────────
function initBulkSelect() {
    const selectAll = document.getElementById('select-all-questions');
    if (!selectAll) return;

    selectAll.addEventListener('change', () => {
        document.querySelectorAll('.question-checkbox').forEach(cb => {
            cb.checked = selectAll.checked;
        });
    });
}

// ── Delete Confirmation ───────────────────────
function initDeleteConfirm() {
    document.querySelectorAll('.delete-form').forEach(form => {
        form.addEventListener('submit', (e) => {
            if (!confirm('Are you sure you want to delete this? This action cannot be undone.')) {
                e.preventDefault();
            }
        });
    });
}

// ── Question Preview Modal ────────────────────
function showQuestionPreview(qId) {
    // Find question data from the page
    const row = document.querySelector(`[data-q-id="${qId}"]`);
    if (!row) return;

    const data = JSON.parse(row.dataset.qJson || '{}');

    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay';
    overlay.id = 'preview-modal';
    overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };

    const correctColors = { A: '', B: '', C: '', D: '' };
    if (data.correct_ans && data.correct_ans !== 'X') {
        correctColors[data.correct_ans] = 'color: var(--green); font-weight: 600;';
    }

    overlay.innerHTML = `
        <div class="modal" style="max-width: 600px;">
            <h3 style="margin-bottom: 4px;">Question #${data.qno || ''}</h3>
            <div style="display: flex; gap: 8px; margin-bottom: 16px;">
                <span class="badge badge-muted">Section ${data.section || 1}</span>
                <span class="badge badge-muted">${data.topic || 'General'}</span>
                <span class="badge ${data.correct_ans === 'X' ? 'badge-warning' : 'badge-success'}">Ans: ${data.correct_ans || ''}</span>
            </div>
            <p style="margin-bottom: 16px; line-height: 1.6;">${data.question || ''}</p>
            <div style="display: grid; gap: 8px;">
                <div class="review-option" style="${correctColors.A}">A: ${data.option_a || ''}</div>
                <div class="review-option" style="${correctColors.B}">B: ${data.option_b || ''}</div>
                <div class="review-option" style="${correctColors.C}">C: ${data.option_c || ''}</div>
                <div class="review-option" style="${correctColors.D}">D: ${data.option_d || ''}</div>
            </div>
            ${data.explanation ? `<div class="review-explanation" style="margin-top: 12px;">💡 ${data.explanation}</div>` : ''}
            <div class="modal-actions" style="margin-top: 20px;">
                <button class="btn btn-outline" onclick="document.getElementById('preview-modal').remove()">Close</button>
            </div>
        </div>
    `;

    document.body.appendChild(overlay);
}
