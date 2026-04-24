// ── Progress Tracking (localStorage) ─────────────────────────────────────────

function getCompleted() {
  try { return JSON.parse(localStorage.getItem('qb_completed') || '{}'); }
  catch { return {}; }
}
function setCompleted(data) {
  localStorage.setItem('qb_completed', JSON.stringify(data));
}
function markComplete(key) {
  const data = getCompleted();
  data[key] = true;
  setCompleted(data);
  updateProgressUI();
}

function updateProgressUI() {
  const completed = getCompleted();

  // Sidebar check icons
  document.querySelectorAll('.check-icon').forEach(el => {
    const key = el.dataset.key;
    if (completed[key]) {
      el.classList.add('done');
      el.querySelector('i').className = 'bi bi-check-circle-fill';
    }
  });

  // Dashboard progress bars
  document.querySelectorAll('[data-progress-bar]').forEach(bar => {
    const modId = bar.dataset.progressBar;
    const keys = [...document.querySelectorAll(`.check-icon[data-key^="${modId}-"]`)]
      .map(el => el.dataset.key);
    if (!keys.length) return;
    const done = keys.filter(k => completed[k]).length;
    const pct = Math.round((done / keys.length) * 100);
    bar.style.width = pct + '%';
    const label = document.querySelector(`.module-pct[data-module="${modId}"]`);
    if (label) label.textContent = pct + '%';
  });

  // Overall progress in navbar
  const allKeys = [...document.querySelectorAll('.check-icon')].map(el => el.dataset.key);
  if (allKeys.length) {
    const totalDone = allKeys.filter(k => completed[k]).length;
    const el = document.getElementById('progress-display');
    if (el) el.textContent = `${totalDone} / ${allKeys.length} complete`;
  }
}

// ── Mark Complete Button ───────────────────────────────────────────────────────

const completeBtn = document.getElementById('completeBtn');
if (completeBtn) {
  const key = completeBtn.dataset.key;
  if (getCompleted()[key]) {
    completeBtn.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i>Completed';
    completeBtn.classList.add('done');
  }
  completeBtn.addEventListener('click', () => {
    markComplete(key);
    completeBtn.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i>Completed';
    completeBtn.classList.add('done');
  });
}

// ── Mobile Sidebar ────────────────────────────────────────────────────────────

const sidebarToggle = document.getElementById('sidebarToggle');
const sidebar = document.getElementById('sidebar');

sidebarToggle?.addEventListener('click', () => {
  sidebar.classList.toggle('open');
});

// Close sidebar when clicking outside on mobile
document.addEventListener('click', e => {
  if (window.innerWidth <= 768 &&
      sidebar?.classList.contains('open') &&
      !sidebar.contains(e.target) &&
      !sidebarToggle?.contains(e.target)) {
    sidebar.classList.remove('open');
  }
});

// ── AI Chat Widget ─────────────────────────────────────────────────────────────

const chatFab = document.getElementById('chatFab');
const chatPanel = document.getElementById('chatPanel');
const chatClose = document.getElementById('chatClose');
const chatOverlay = document.getElementById('chatOverlay');
const chatMessages = document.getElementById('chatMessages');
const chatInput = document.getElementById('chatInput');
const chatSend = document.getElementById('chatSend');

let chatHistory = [];

function toggleChat(open) {
  chatPanel.classList.toggle('open', open);
  chatFab.classList.toggle('active', open);
  chatOverlay.classList.toggle('show', open);
  if (open) { setTimeout(() => chatInput?.focus(), 300); }
}

chatFab?.addEventListener('click', () => toggleChat(!chatPanel.classList.contains('open')));
chatClose?.addEventListener('click', () => toggleChat(false));
chatOverlay?.addEventListener('click', () => toggleChat(false));

function escHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/\n/g, '<br>');
}

function appendMsg(role, html, isHtml) {
  const wrap = document.createElement('div');
  wrap.className = `chat-msg ${role}`;
  const bubble = document.createElement('div');
  bubble.className = 'msg-bubble';
  bubble.innerHTML = isHtml ? html : escHtml(html);
  wrap.appendChild(bubble);
  chatMessages.appendChild(wrap);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return bubble;
}

async function sendChat() {
  const text = chatInput.value.trim();
  if (!text) return;

  chatInput.value = '';
  chatInput.disabled = true;
  chatSend.disabled = true;

  appendMsg('user', text, false);
  chatHistory.push({ role: 'user', content: text });

  const typingBubble = appendMsg('assistant', 'Thinking…', false);
  typingBubble.classList.add('typing');

  try {
    const ctx = window.QB_CONTEXT || {};
    const resp = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        messages: chatHistory,
        lesson_title: ctx.lessonTitle || '',
        module_title: ctx.moduleTitle || '',
        path_token: window.QB_PATH_TOKEN || '',
      }),
    });
    const data = await resp.json();
    typingBubble.parentElement.remove();

    if (data.reply) {
      chatHistory.push({ role: 'assistant', content: data.reply });
      appendMsg('assistant', data.reply, false);
    } else {
      appendMsg('assistant', `⚠️ ${data.error || 'Something went wrong.'}`, false);
    }
  } catch {
    typingBubble.parentElement.remove();
    appendMsg('assistant', '⚠️ Could not reach the server. Please check your connection.', false);
  } finally {
    chatInput.disabled = false;
    chatSend.disabled = false;
    chatInput.focus();
  }
}

chatSend?.addEventListener('click', sendChat);
chatInput?.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
});

// ── Init ──────────────────────────────────────────────────────────────────────

updateProgressUI();
