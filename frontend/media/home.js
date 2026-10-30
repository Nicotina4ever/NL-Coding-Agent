// NL Code home dashboard: presentation only. Commands execute in the extension host.
(function () {
    'use strict';
    const vscode = acquireVsCodeApi();
    const $ = (id) => document.getElementById(id);

    function text(id, value) {
        const node = $(id);
        if (node) { node.textContent = value === undefined || value === null ? '' : String(value); }
    }

    function render(state) {
        if (!state) { return; }
        text('connection', state.connected ? 'engine connected' : (state.connectionState || 'offline'));
        text('project', state.projectName || state.projectRoot || 'no project');
        text('execution', state.executionEnabled ? 'missions enabled' : 'read-only');
        text('mission-count', state.missionTotal || 0);
        text('active-count', state.missionActive || 0);
        text('model-count', state.modelCount || 0);
        text('agent-count', state.agentCount || 0);
        text('session-count', state.sessionCount || 0);
        text('standalone', state.isStandalone ? 'NL Code standalone' : 'VS Code integration');
        const error = $('error');
        if (state.error) {
            error.textContent = state.error;
            error.classList.remove('hidden');
        } else {
            error.textContent = '';
            error.classList.add('hidden');
        }
        const details = $('details');
        details.textContent = '';
        const rows = [
            ['Project', (state.projectName || '') + (state.projectId ? '  #' + state.projectId : '')],
            ['Workspace', state.projectRoot || '(none)'],
            ['Engine', [state.engineName, state.engineVersion].filter(Boolean).join(' ') || '(not connected)'],
            ['Configured roles', (state.roleNames || []).join(', ') || '(none)'],
            ['Configured models', (state.configuredModels || []).join(', ') || '(none)'],
            ['Queued chat turns', String(state.queueCount || 0)]
        ];
        rows.forEach(function (entry) {
            const row = document.createElement('div');
            row.className = 'detail-row';
            const key = document.createElement('span');
            key.className = 'muted';
            key.textContent = entry[0];
            const value = document.createElement('span');
            value.textContent = entry[1];
            row.appendChild(key);
            row.appendChild(value);
            details.appendChild(row);
        });
    }

    document.querySelectorAll('[data-command]').forEach(function (button) {
        button.addEventListener('click', function () {
            vscode.postMessage({ type: 'command', command: button.dataset.command });
        });
    });
    const refresh = $('refresh');
    if (refresh) {
        refresh.addEventListener('click', function () { vscode.postMessage({ type: 'refresh' }); });
    }
    window.addEventListener('message', function (event) {
        const message = event.data || {};
        if (message.type === 'homeState') { render(message.payload); }
    });
    vscode.postMessage({ type: 'ready' });
})();
