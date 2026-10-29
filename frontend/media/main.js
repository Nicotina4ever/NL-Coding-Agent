// NL Chat webview script. Plain browser JavaScript: the VS Code webview does
// not run TypeScript. Model output is rendered with textContent only.
(function () {
    'use strict';

    const vscode = acquireVsCodeApi();
    const statusEl = document.getElementById('status');
    const messagesEl = document.getElementById('messages');
    const inputEl = document.getElementById('input');
    const sendEl = document.getElementById('send');
    const composerEl = document.getElementById('composer');
    const hintEl = document.getElementById('hint');

    const labels = { user: 'You', assistant: 'NL', system: 'NL', error: 'Error' };
    const transcript = [];
    let busy = false;

    function setStatus(state, label) {
        statusEl.textContent = label || '';
        statusEl.dataset.state = state || '';
    }

    function persist() {
        vscode.setState({ transcript: transcript.slice(-100) });
    }

    function append(role, text) {
        const item = { role: role, text: String(text == null ? '' : text) };
        transcript.push(item);
        if (transcript.length > 100) {
            transcript.shift();
        }
        persist();
        render(item);
        return item;
    }

    function render(item) {
        const wrap = document.createElement('div');
        wrap.className = 'nl-message nl-message-' + item.role;
        const label = document.createElement('span');
        label.className = 'nl-message-label';
        label.textContent = labels[item.role] || item.role;
        const body = document.createElement('div');
        body.className = 'nl-message-body';
        body.textContent = item.text;
        wrap.appendChild(label);
        wrap.appendChild(body);
        messagesEl.appendChild(wrap);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function setBusy(value) {
        busy = Boolean(value);
        sendEl.disabled = busy;
        statusEl.dataset.busy = busy ? 'true' : 'false';
        hintEl.textContent = busy ? 'Waiting for the engine…' : '';
    }

    function submit() {
        const text = inputEl.value.trim();
        if (!text || busy) {
            return;
        }
        append('user', text);
        inputEl.value = '';
        vscode.postMessage({ type: 'send', text: text });
    }

    composerEl.addEventListener('submit', function (event) {
        event.preventDefault();
        submit();
    });

    inputEl.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            submit();
        }
    });

    window.addEventListener('message', function (event) {
        const message = event.data || {};
        if (message.type === 'status') {
            setStatus(message.state, message.label);
        } else if (message.type === 'busy') {
            setBusy(message.value);
        } else if (message.type === 'message') {
            append(message.role || 'system', message.text);
        } else if (message.type === 'focus') {
            inputEl.focus();
        }
    });

    const saved = vscode.getState();
    if (saved && Array.isArray(saved.transcript)) {
        saved.transcript.forEach(function (item) {
            if (item && item.role && typeof item.text === 'string' && transcript.length < 100) {
                transcript.push(item);
                render(item);
            }
        });
    }

    setStatus('connecting', 'Connecting to NL Coding Agent…');
    setTimeout(function () {
        inputEl.focus();
    }, 50);
    vscode.postMessage({ type: 'ready' });
})();
