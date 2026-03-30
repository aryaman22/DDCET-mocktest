/* ════════════════════════════════════════════════════════
   DDCET Portal — main.js (shared utilities)
   ════════════════════════════════════════════════════════ */

document.addEventListener('DOMContentLoaded', () => {
    // ── Auto-dismiss flash messages after 4s ──────────
    document.querySelectorAll('.flash-msg').forEach(msg => {
        setTimeout(() => {
            msg.classList.add('fade-out');
            setTimeout(() => msg.remove(), 300);
        }, 4000);
    });
    document.querySelectorAll('.flash-close').forEach(btn => {
        btn.addEventListener('click', () => {
            const msg = btn.closest('.flash-msg');
            msg.classList.add('fade-out');
            setTimeout(() => msg.remove(), 300);
        });
    });

    // ── Mobile drawer toggle ─────────────────────────
    const hamburger = document.getElementById('hamburger-btn');
    const drawer = document.getElementById('mobile-drawer');
    const overlay = document.getElementById('drawer-overlay');
    if (hamburger && drawer && overlay) {
        hamburger.addEventListener('click', () => {
            drawer.classList.toggle('open');
            overlay.classList.toggle('open');
        });
        overlay.addEventListener('click', () => {
            drawer.classList.remove('open');
            overlay.classList.remove('open');
        });
    }

    // ── Admin sidebar toggle (mobile) ────────────────
    const adminHamburger = document.getElementById('admin-hamburger');
    const adminSidebar = document.getElementById('admin-sidebar');
    const adminOverlay = document.getElementById('admin-overlay');
    if (adminHamburger && adminSidebar) {
        adminHamburger.addEventListener('click', () => {
            adminSidebar.classList.toggle('open');
            if (adminOverlay) adminOverlay.classList.toggle('open');
        });
        if (adminOverlay) {
            adminOverlay.addEventListener('click', () => {
                adminSidebar.classList.remove('open');
                adminOverlay.classList.remove('open');
            });
        }
    }

    // ── Active nav link highlighting ─────────────────
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-links a, .sidebar-nav a, .bottom-nav a, .drawer-links a').forEach(a => {
        if (a.getAttribute('href') === currentPath) {
            a.classList.add('active');
        }
    });

    // ── Button ripple effect ─────────────────────────
    document.querySelectorAll('.btn').forEach(btn => {
        btn.addEventListener('click', function (e) {
            const ripple = document.createElement('span');
            ripple.classList.add('ripple');
            const rect = this.getBoundingClientRect();
            ripple.style.left = (e.clientX - rect.left) + 'px';
            ripple.style.top = (e.clientY - rect.top) + 'px';
            this.appendChild(ripple);
            setTimeout(() => ripple.remove(), 600);
        });
    });

    // ── FAQ accordion ────────────────────────────────
    document.querySelectorAll('.faq-question').forEach(q => {
        q.addEventListener('click', () => {
            const item = q.closest('.faq-item');
            item.classList.toggle('open');
        });
    });

    // ── Smooth scroll for anchor links ───────────────
    document.querySelectorAll('a[href^="#"]').forEach(a => {
        a.addEventListener('click', e => {
            const target = document.querySelector(a.getAttribute('href'));
            if (target) {
                e.preventDefault();
                target.scrollIntoView({ behavior: 'smooth', block: 'start' });
            }
        });
    });

    // ── Confirm delete modals ────────────────────────
    document.querySelectorAll('[data-confirm]').forEach(el => {
        el.addEventListener('click', e => {
            if (!confirm(el.dataset.confirm)) {
                e.preventDefault();
            }
        });
    });
});
