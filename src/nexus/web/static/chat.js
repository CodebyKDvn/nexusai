// Nexus AI — Chat Interface

const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const welcomeScreen = document.getElementById('welcome-screen');
const statusCard = document.getElementById('status-card');
const connectionStatus = document.getElementById('connection-status');
const agentList = document.getElementById('agent-list');
const activityLog = document.getElementById('activity-log');
const clearBtn = document.getElementById('clear-btn');
const sidebarToggle = document.getElementById('sidebar-toggle');
const sidebar = document.getElementById('sidebar');
const menuBtn = document.getElementById('menu-btn');
const providerInfo = document.getElementById('provider-info');
const modelInfo = document.getElementById('model-info');

let ws = null;
let isProcessing = false;
let thinkingEl = null;

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatContent(text) {
    // Code blocks
    text = text.replace(/```(\w+)?\n([\s\S]*?)```/g, (_, lang, code) => {
        return `<pre><code>${escapeHtml(code.trim())}</code></pre>`;
    });
    // Inline code
    text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
    // Bold
    text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Line breaks
    text = text.replace(/\n/g, '<br>');
    return text;
}

function getTimeStr() {
    return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function scrollToBottom() {
    requestAnimationFrame(() => {
        messagesEl.scrollTop = messagesEl.scrollHeight;
    });
}

function hideWelcome() {
    if (welcomeScreen) {
        welcomeScreen.style.display = 'none';
    }
}

function showThinking() {
    const el = document.createElement('div');
    el.className = 'thinking';
    el.innerHTML = `
        <div class="message-avatar" style="background: var(--accent-dim); color: var(--accent);">N</div>
        <div class="thinking-dots">
            <span></span><span></span><span></span>
        </div>
    `;
    messagesEl.appendChild(el);
    scrollToBottom();
    return el;
}

function removeThinking() {
    if (thinkingEl) {
        thinkingEl.remove();
        thinkingEl = null;
    }
}

function addMessage(type, content, sender = '', options = {}) {
    hideWelcome();
    removeThinking();

    const el = document.createElement('div');
    el.className = `message ${type}`;

    let avatarText = 'N';
    let senderName = 'Nexus AI';

    if (type === 'user') {
        avatarText = 'U';
        senderName = 'You';
    } else if (type === 'error') {
        avatarText = '!';
        senderName = 'Error';
    } else if (sender) {
        senderName = sender.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        avatarText = sender.charAt(0).toUpperCase();
    }

    el.innerHTML = `
        <div class="message-avatar">${escapeHtml(avatarText)}</div>
        <div class="message-body">
            <div class="message-sender">
                ${escapeHtml(senderName)}
                <span class="message-time">${getTimeStr()}</span>
            </div>
            <div class="message-content">${formatContent(content)}</div>
        </div>
    `;

    messagesEl.appendChild(el);
    scrollToBottom();
    return el;
}

function addAgentActivity(sender, recipient, content) {
    const el = document.createElement('div');
    el.className = 'agent-activity';
    el.innerHTML = `
        <span class="agent-activity-icon">&#x25B6;</span>
        <span class="agent-activity-text">
            <span class="activity-agent">${escapeHtml(sender)}</span>
            &#x2192; ${escapeHtml(recipient)}: ${escapeHtml(content.substring(0, 100))}
        </span>
    `;
    messagesEl.appendChild(el);
    scrollToBottom();

    // Also add to sidebar activity log
    const logEntry = document.createElement('div');
    logEntry.className = 'activity-entry';
    logEntry.innerHTML = `<span class="activity-sender">${escapeHtml(sender)}</span> &#x2192; ${escapeHtml(content.substring(0, 60))}`;
    activityLog.prepend(logEntry);

    // Keep only last 20 entries
    while (activityLog.children.length > 20) {
        activityLog.lastChild.remove();
    }

    // Highlight active agent in sidebar
    document.querySelectorAll('.agent-item').forEach(item => {
        item.classList.toggle('active', item.dataset.agent === sender);
    });
}

function setProcessing(processing) {
    isProcessing = processing;
    inputEl.disabled = processing;
    sendBtn.disabled = processing || !inputEl.value.trim();
    if (!processing) {
        inputEl.focus();
    }
}

function sendMessage(text) {
    if (!text.trim() || !ws || ws.readyState !== WebSocket.OPEN) return;

    addMessage('user', text);
    inputEl.value = '';
    inputEl.style.height = 'auto';
    sendBtn.disabled = true;

    setProcessing(true);
    thinkingEl = showThinking();

    ws.send(JSON.stringify({ message: text }));
}

function sendSuggestion(text) {
    sendMessage(text);
}

// WebSocket connection

function connectWebSocket() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${location.host}/ws/chat`;

    ws = new WebSocket(url);

    ws.onopen = () => {
        connectionStatus.textContent = 'Connected';
        statusCard.querySelector('.status-dot').classList.add('connected');
    };

    ws.onclose = () => {
        connectionStatus.textContent = 'Disconnected';
        statusCard.querySelector('.status-dot').classList.remove('connected');
        // Reconnect after 3 seconds
        setTimeout(connectWebSocket, 3000);
    };

    ws.onerror = () => {
        connectionStatus.textContent = 'Connection error';
    };

    ws.onmessage = (event) => {
        let data;
        try {
            data = JSON.parse(event.data);
        } catch {
            return;
        }

        switch (data.type) {
            case 'system':
                // Populate agent list
                if (data.agents) {
                    agentList.innerHTML = data.agents.map(a =>
                        `<li class="agent-item" data-agent="${escapeHtml(a)}">
                            <span class="agent-dot"></span>
                            ${escapeHtml(a.replace(/_/g, ' '))}
                        </li>`
                    ).join('');
                }
                break;

            case 'status':
                // Agent is thinking
                break;

            case 'agent_message':
                if (data.msg_type === 'task_result') {
                    removeThinking();
                    addMessage('assistant', data.content, data.sender);
                    setProcessing(false);
                } else if (data.msg_type === 'error') {
                    removeThinking();
                    addMessage('error', data.content, data.sender);
                    setProcessing(false);
                } else {
                    addAgentActivity(data.sender, data.recipient, data.content);
                }
                break;

            case 'result':
                removeThinking();
                addMessage('assistant', data.content);
                if (data.errors && data.errors.length > 0) {
                    data.errors.forEach(err => addMessage('error', err));
                }
                setProcessing(false);
                break;

            case 'error':
                removeThinking();
                addMessage('error', data.content);
                setProcessing(false);
                break;
        }
    };
}

// Input handling

inputEl.addEventListener('input', () => {
    sendBtn.disabled = !inputEl.value.trim() || isProcessing;
    // Auto-resize textarea
    inputEl.style.height = 'auto';
    inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
});

inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!isProcessing && inputEl.value.trim()) {
            sendMessage(inputEl.value);
        }
    }
});

sendBtn.addEventListener('click', () => {
    if (!isProcessing && inputEl.value.trim()) {
        sendMessage(inputEl.value);
    }
});

clearBtn.addEventListener('click', () => {
    messagesEl.innerHTML = '';
    if (welcomeScreen) {
        messagesEl.appendChild(welcomeScreen);
        welcomeScreen.style.display = 'flex';
    }
    activityLog.innerHTML = '';
});

// Sidebar toggle
sidebarToggle.addEventListener('click', () => {
    sidebar.classList.toggle('collapsed');
});

menuBtn.addEventListener('click', () => {
    sidebar.classList.toggle('open');
});

// Close sidebar on mobile when clicking outside
document.addEventListener('click', (e) => {
    if (window.innerWidth <= 768 &&
        sidebar.classList.contains('open') &&
        !sidebar.contains(e.target) &&
        e.target !== menuBtn) {
        sidebar.classList.remove('open');
    }
});

// Fetch initial status
async function fetchStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();
        providerInfo.textContent = data.provider || '—';
        modelInfo.textContent = (data.model || '—').split('/').pop();
        if (!data.has_api_key) {
            document.getElementById('chat-subtitle').textContent = 'Rule-based mode (no API key)';
        }
    } catch {
        // Will retry on reconnect
    }
}

// Initialize
connectWebSocket();
fetchStatus();
