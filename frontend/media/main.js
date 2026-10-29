// NL dashboard webview script. Plain browser JavaScript: the VS Code webview
// does not run TypeScript. All engine/model text is rendered with textContent.
(function () {
    'use strict';

    const vscode = acquireVsCodeApi();
    const $ = function (id) { return document.getElementById(id); };

    const statusEl = $('status');
    const projectBadge = $('project-badge');
    const execToggle = $('exec-toggle');
    const noticeEl = $('notice');
    const tabButtons = Array.prototype.slice.call(document.querySelectorAll('.nl-tab-button'));
    const panels = { chat: $('tab-chat'), missions: $('tab-missions'), engine: $('tab-engine') };

    const banner = $('mission-banner');
    const bannerTitle = $('banner-title');
    const bannerStatus = $('banner-status');
    const bannerBar = $('banner-progress-bar');
    const bannerCounts = $('banner-counts');
    const bannerStop = $('btn-banner-stop');
    const bannerResume = $('btn-banner-resume');
    const bannerDetails = $('btn-banner-details');

    const messagesEl = $('messages');
    const composer = $('composer');
    const inputEl = $('input');
    const modeEl = $('mode');
    const chatModelEl = $('chat-model');
    const missionFields = $('mission-fields');
    const devModelEl = $('dev-model');
    const reviewerModelEl = $('reviewer-model');
    const missionNote = $('mission-note');
    const hintEl = $('hint');
    const sendEl = $('send');

    const missionListEl = $('mission-list');
    const missionDetailEl = $('mission-detail');
    const engineContent = $('engine-content');

    const labels = { user: 'You', assistant: 'NL', system: 'NL', error: 'Error' };
    const transcript = [];
    let state = null;
    let mode = 'chat';
    let tab = 'chat';

    function persist() {
        vscode.setState({ transcript: transcript.slice(-120), mode: mode, tab: tab });
    }

    function setStatus(text, stateName) {
        statusEl.textContent = text || '';
        statusEl.dataset.state = stateName || '';
    }

    function showNotice(text) {
        if (!text) {
            noticeEl.classList.add('hidden');
            noticeEl.textContent = '';
            return;
        }
        noticeEl.textContent = text;
        noticeEl.classList.remove('hidden');
    }

    function el(tag, className, text) {
        const node = document.createElement(tag);
        if (className) { node.className = className; }
        if (text !== undefined && text !== null) { node.textContent = String(text); }
        return node;
    }

    function clear(node) {
        while (node.firstChild) { node.removeChild(node.firstChild); }
    }

    function chip(text, kind) {
        const node = el('span', 'nl-status-chip', text);
        if (kind) { node.dataset.kind = kind; }
        return node;
    }

    function statusKind(status) {
        if (status === 'completed') { return 'ok'; }
        if (status === 'failed' || status === 'blocked') { return 'bad'; }
        if (status === 'running' || status === 'pending') { return 'busy'; }
        if (status === 'interrupted') { return 'warn'; }
        return '';
    }

    function append(role, text) {
        const item = { role: role, text: String(text == null ? '' : text) };
        transcript.push(item);
        if (transcript.length > 120) { transcript.shift(); }
        persist();
        renderMessage(item);
        return item;
    }

    function renderMessage(item) {
        const wrap = el('div', 'nl-message nl-message-' + item.role);
        wrap.appendChild(el('span', 'nl-message-label', labels[item.role] || item.role));
        wrap.appendChild(el('div', 'nl-message-body', item.text));
        messagesEl.appendChild(wrap);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function postAction(action, payload) {
        vscode.postMessage({ type: 'action', action: action, payload: payload || {} });
    }

    function switchTab(next) {
        tab = next;
        Object.keys(panels).forEach(function (name) {
            panels[name].classList.toggle('active', name === tab);
        });
        tabButtons.forEach(function (button) {
            button.classList.toggle('active', button.dataset.tab === tab);
        });
        persist();
    }

    function setMode(next) {
        mode = next === 'mission' ? 'mission' : 'chat';
        modeEl.value = mode;
        missionFields.classList.toggle('hidden', mode !== 'mission');
        missionNote.classList.toggle('hidden', mode !== 'mission');
        sendEl.textContent = mode === 'mission' ? 'Start mission' : 'Send';
        persist();
    }

    function populateSelect(select, options, selected) {
        clear(select);
        options.forEach(function (option) {
            const node = el('option', '', option.label);
            node.value = option.value;
            if (option.group === 'configured' || option.loaded) {
                node.dataset.kind = option.loaded ? 'loaded' : 'configured';
            }
            select.appendChild(node);
        });
        if (selected !== undefined && selected !== null) {
            select.value = selected;
            if (select.value !== selected) {
                select.value = '';
            }
        }
    }

    function renderHeader(current) {
        setStatus(
            current.connected
                ? (current.executionEnabled ? 'missions enabled' : 'read-only') + ' · project #' + (current.project ? current.project.id : '?')
                : (current.connectionState || 'connecting'),
            current.connected ? 'ready' : 'connecting'
        );
        projectBadge.textContent = current.project
            ? '#' + current.project.id + (current.project.name ? ' · ' + current.project.name : '')
            : 'no project';
        projectBadge.title = current.project ? current.project.root : 'no workspace';
        execToggle.textContent = current.executionEnabled ? 'execution: enabled' : 'execution: read-only';
        execToggle.dataset.enabled = current.executionEnabled ? 'true' : 'false';
        showNotice(current.error || null);
    }

    function renderBanner(current) {
        const mission = current.activeMissionId
            ? (current.selected && current.selected.detail && current.selected.detail.mission.id === current.activeMissionId
                ? current.selected.detail
                : null)
            : null;
        if (!current.activeMissionId) {
            banner.classList.add('hidden');
            return;
        }
        const row = mission ? mission.mission : (current.missions || []).filter(function (item) { return item.id === current.activeMissionId; })[0];
        if (!row) {
            banner.classList.add('hidden');
            return;
        }
        banner.classList.remove('hidden');
        bannerTitle.textContent = 'Mission #' + row.id + ' · ' + (row.title || '');
        bannerStatus.textContent = row.status || '—';
        bannerStatus.dataset.kind = statusKind(row.status);
        const progress = mission ? mission.progress : null;
        const percent = progress ? Math.max(0, Math.min(100, Number(progress.percent) || 0)) : 0;
        bannerBar.style.width = percent + '%';
        bannerCounts.textContent = progress
            ? progress.completed + '/' + progress.total + ' tasks · ' + percent + '%' + (progress.failed ? ' · ' + progress.failed + ' failed' : '')
            : 'progress pending';
        const resumable = row.status === 'interrupted' || row.status === 'blocked' || row.status === 'failed';
        bannerStop.classList.toggle('hidden', !(row.status === 'running' || row.status === 'pending'));
        bannerResume.classList.toggle('hidden', !(resumable && row.harness_version === 2));
        bannerStop.disabled = Boolean(current.busyMission);
    }

    function renderModelSelectors(current) {
        const options = current.modelOptions || [];
        populateSelect(chatModelEl, options, current.chatModel || '');
        populateSelect(devModelEl, options, current.missionModels ? current.missionModels.developerModel : '');
        populateSelect(reviewerModelEl, options, current.missionModels ? current.missionModels.reviewerModel : '');
        sendEl.disabled = Boolean(current.busyChat || current.busyMission);
        hintEl.textContent = current.busyChat
            ? 'Waiting for the engine…'
            : current.busyMission
                ? 'Dispatching mission…'
                : '';
    }

    function renderMissionList(current) {
        clear(missionListEl);
        const missions = current.missions || [];
        if (!missions.length) {
            missionListEl.appendChild(el('p', 'nl-muted', 'No persistent missions for this project.'));
            return;
        }
        missions.forEach(function (mission) {
            const row = el('div', 'nl-mission-row');
            const head = el('div', 'nl-mission-row-head');
            head.appendChild(el('span', 'nl-mission-id', '#' + mission.id));
            head.appendChild(el('span', 'nl-mission-title', mission.title || '(untitled)'));
            head.appendChild(chip(mission.status || '—', statusKind(mission.status)));
            const meta = el('span', 'nl-muted', [mission.review_verdict, mission.promotion_status, mission.diff_stat]
                .filter(Boolean).join(' · '));
            head.appendChild(meta);
            row.appendChild(head);

            const goal = el('div', 'nl-muted nl-mission-goal', mission.goal || '');
            row.appendChild(goal);

            const actions = el('div', 'nl-actions');
            const open = el('button', '', 'Open');
            open.addEventListener('click', function (event) {
                event.stopPropagation();
                postAction('selectMission', { missionId: mission.id });
                switchTab('missions');
            });
            actions.appendChild(open);
            if (mission.status === 'running' || mission.status === 'pending') {
                const stop = el('button', '', 'Stop');
                stop.addEventListener('click', function (event) {
                    event.stopPropagation();
                    postAction('cancelMission', { missionId: mission.id });
                });
                actions.appendChild(stop);
            }
            if ((mission.status === 'interrupted' || mission.status === 'blocked' || mission.status === 'failed') && mission.harness_version === 2) {
                const resume = el('button', '', 'Resume');
                resume.addEventListener('click', function (event) {
                    event.stopPropagation();
                    postAction('resumeMission', { missionId: mission.id });
                });
                actions.appendChild(resume);
            }
            row.appendChild(actions);
            row.addEventListener('click', function () {
                postAction('selectMission', { missionId: mission.id });
                switchTab('missions');
            });
            missionListEl.appendChild(row);
        });
    }

    function renderTasks(detail) {
        const tasks = detail.tasks || [];
        if (!tasks.length) {
            return el('p', 'nl-muted', 'No task rows yet.');
        }
        const wrap = el('div', 'nl-tasks');
        tasks.forEach(function (task) {
            const row = el('div', 'nl-task');
            row.appendChild(el('span', 'nl-task-agent', task.agent_role || '?'));
            row.appendChild(el('span', 'nl-task-title', task.title || ''));
            row.appendChild(chip(task.status || '—', statusKind(task.status)));
            row.appendChild(el('span', 'nl-muted', 'attempts ' + (task.attempts || 0)
                + (task.last_error ? ' · ' + String(task.last_error).slice(0, 160) : '')));
            wrap.appendChild(row);
        });
        return wrap;
    }

    function renderHandoffs(detail) {
        const handoffs = detail.handoffs || [];
        if (!handoffs.length) {
            return el('p', 'nl-muted', 'No agent handoffs yet.');
        }
        const wrap = el('div', 'nl-handoffs');
        handoffs.forEach(function (handoff) {
            const item = el('div', 'nl-handoff');
            const route = el('div', 'nl-handoff-route');
            route.appendChild(el('span', 'nl-task-agent', handoff.from_role || '?'));
            route.appendChild(el('span', 'nl-muted', '→'));
            route.appendChild(el('span', 'nl-task-agent', handoff.to_role || '?'));
            item.appendChild(route);
            item.appendChild(el('div', 'nl-handoff-summary', handoff.summary || ''));
            if (handoff.payload && Object.keys(handoff.payload).length) {
                const details = el('details');
                details.appendChild(el('summary', 'nl-muted', 'payload'));
                details.appendChild(el('pre', 'nl-payload', JSON.stringify(handoff.payload, null, 2)));
                item.appendChild(details);
            }
            wrap.appendChild(item);
        });
        return wrap;
    }

    function renderVerification(detail) {
        const runs = detail.verification_runs || [];
        const wrap = el('div', 'nl-verification');
        if (!runs.length) {
            wrap.appendChild(el('p', 'nl-muted', 'No verification runs recorded yet.'));
            return wrap;
        }
        runs.forEach(function (run) {
            const item = el('div', 'nl-verify-run');
            const head = el('div', 'nl-verify-head');
            head.appendChild(chip(run.passed ? 'PASSED' : 'FAILED', run.passed ? 'ok' : 'bad'));
            head.appendChild(el('span', 'nl-muted', 'exit ' + run.exit_code + ' · ' + (run.command || '')));
            item.appendChild(head);
            const details = el('details');
            details.appendChild(el('summary', 'nl-muted', 'stdout/stderr'));
            details.appendChild(el('pre', 'nl-output', [run.stdout || '', run.stderr || ''].filter(Boolean).join('\n')));
            item.appendChild(details);
            wrap.appendChild(item);
        });
        return wrap;
    }

    function renderToolActivity(detail) {
        const actions = [];
        (detail.handoffs || []).forEach(function (handoff) {
            const recorded = handoff.payload && handoff.payload.actions;
            if (Array.isArray(recorded)) {
                recorded.forEach(function (action) { actions.push(String(action)); });
            }
        });
        (detail.verification_runs || []).forEach(function (run) {
            const label = String(run.command || '').split(' ')[0];
            actions.push('Executed ' + label + ' (exit ' + run.exit_code + ')');
        });
        const wrap = el('div', 'nl-tool-activity');
        if (!actions.length) {
            wrap.appendChild(el('p', 'nl-muted', 'The engine persisted no tool activity for this mission.'));
            return wrap;
        }
        actions.forEach(function (action) {
            wrap.appendChild(el('div', 'nl-tool-action', action));
        });
        return wrap;
    }

    function renderAttempts(detail) {
        const attempts = detail.attempts || [];
        if (!attempts.length) {
            return el('p', 'nl-muted', 'No agent attempts recorded yet.');
        }
        const wrap = el('div', 'nl-attempts');
        attempts.forEach(function (attempt) {
            const details = el('details', 'nl-attempt');
            const route = (attempt.agent_role || '?') + (attempt.task_title ? ' · ' + attempt.task_title : '');
            details.appendChild(el('summary', '', route + ' — ' + (attempt.status || '')));
            details.appendChild(el('pre', 'nl-output', (attempt.output || '') + (attempt.error ? '\nERROR: ' + attempt.error : '')));
            wrap.appendChild(details);
        });
        return wrap;
    }

    function reviewerNotes(detail) {
        const handoff = (detail.handoffs || []).filter(function (item) {
            return item.from_role === 'reviewer' && item.payload && item.payload.review_notes;
        }).pop();
        return handoff ? String(handoff.payload.review_notes) : '';
    }

    function renderMissionDetail(current) {
        clear(missionDetailEl);
        if (!current.selected) {
            missionDetailEl.classList.add('hidden');
            return;
        }
        missionDetailEl.classList.remove('hidden');
        const detail = current.selected.detail;
        const mission = detail.mission;
        const diff = current.selected.diff;

        const head = el('div', 'nl-detail-head');
        head.appendChild(el('h2', 'nl-detail-title', 'Mission #' + mission.id + ' · ' + (mission.title || '')));
        head.appendChild(chip(mission.status || '—', statusKind(mission.status)));
        if (mission.review_verdict) { head.appendChild(chip(mission.review_verdict, mission.review_verdict === 'APPROVE' ? 'ok' : 'bad')); }
        if (mission.promotion_status) { head.appendChild(chip(mission.promotion_status, 'neutral')); }
        missionDetailEl.appendChild(head);

        const actions = el('div', 'nl-actions');
        const refresh = el('button', '', 'Refresh');
        refresh.addEventListener('click', function () { postAction('selectMission', { missionId: mission.id }); });
        actions.appendChild(refresh);
        if (mission.status === 'running' || mission.status === 'pending') {
            const stop = el('button', '', 'Stop');
            stop.addEventListener('click', function () { postAction('cancelMission', { missionId: mission.id }); });
            actions.appendChild(stop);
        }
        if ((mission.status === 'interrupted' || mission.status === 'blocked' || mission.status === 'failed') && mission.harness_version === 2) {
            const resume = el('button', '', 'Resume');
            resume.addEventListener('click', function () { postAction('resumeMission', { missionId: mission.id }); });
            actions.appendChild(resume);
        }
        missionDetailEl.appendChild(actions);

        missionDetailEl.appendChild(el('div', 'nl-muted', 'Objective'));
        missionDetailEl.appendChild(el('div', 'nl-detail-goal', mission.goal || ''));
        if (mission.result_summary) {
            missionDetailEl.appendChild(el('div', 'nl-result', mission.result_summary));
        }
        const progress = detail.progress || { total: 0, completed: 0, failed: 0, running: 0, pending: 0, percent: 0 };
        const progressWrap = el('div', 'nl-progress-block');
        progressWrap.appendChild(el('div', 'nl-muted', 'Progress · ' + progress.completed + '/' + progress.total
            + (progress.failed ? ' · ' + progress.failed + ' failed' : '')
            + (progress.running ? ' · ' + progress.running + ' running' : '')));
        const bar = el('div', 'nl-progress');
        const fill = el('div', 'nl-progress-bar');
        fill.style.width = Math.max(0, Math.min(100, Number(progress.percent) || 0)) + '%';
        bar.appendChild(fill);
        progressWrap.appendChild(bar);
        missionDetailEl.appendChild(progressWrap);

        if (Array.isArray(mission.changed_paths) && mission.changed_paths.length) {
            missionDetailEl.appendChild(el('div', 'nl-muted', 'Changed paths: ' + mission.changed_paths.join(', ')));
        }
        if (mission.diff_stat) {
            missionDetailEl.appendChild(el('div', 'nl-muted', 'Diff: ' + mission.diff_stat));
        }

        const notes = reviewerNotes(detail);
        if (notes) {
            missionDetailEl.appendChild(el('h3', 'nl-detail-subtitle', 'Reviewer notes'));
            missionDetailEl.appendChild(el('pre', 'nl-output', notes));
        }

        missionDetailEl.appendChild(el('h3', 'nl-detail-subtitle', 'Tasks & agents'));
        missionDetailEl.appendChild(renderTasks(detail));
        missionDetailEl.appendChild(el('h3', 'nl-detail-subtitle', 'Agent handoffs'));
        missionDetailEl.appendChild(renderHandoffs(detail));
        missionDetailEl.appendChild(el('h3', 'nl-detail-subtitle', 'Tool activity (persisted evidence only)'));
        missionDetailEl.appendChild(renderToolActivity(detail));
        missionDetailEl.appendChild(el('h3', 'nl-detail-subtitle', 'Candidate / oracle verification'));
        missionDetailEl.appendChild(renderVerification(detail));
        missionDetailEl.appendChild(el('h3', 'nl-detail-subtitle', 'Attempts'));
        missionDetailEl.appendChild(renderAttempts(detail));
        missionDetailEl.appendChild(el('h3', 'nl-detail-subtitle', 'Diff'));
        if (!diff) {
            missionDetailEl.appendChild(el('p', 'nl-muted', 'Diff not loaded.'));
        } else if (diff.ok && diff.diff) {
            missionDetailEl.appendChild(el('pre', 'nl-diff', diff.diff));
        } else {
            missionDetailEl.appendChild(el('p', 'nl-muted', 'No diff available: ' + (diff.error || 'not staged or not retained')));
        }
    }

    function renderEngine(current) {
        clear(engineContent);
        const settings = current.settings;
        if (!settings) {
            engineContent.appendChild(el('p', 'nl-muted', 'Engine settings unavailable.'));
            return;
        }
        const execSection = el('div', 'nl-engine-section');
        execSection.appendChild(el('h3', '', 'Mission execution'));
        const execRow = el('div', 'nl-actions');
        execRow.appendChild(el('span', current.executionEnabled ? 'Execution enabled (--allow-execution)' : 'Read-only engine session'));
        const toggle = el('button', '', current.executionEnabled ? 'Disable execution' : 'Enable execution');
        toggle.addEventListener('click', function () { postAction('toggleExecution', {}); });
        execRow.appendChild(toggle);
        execSection.appendChild(execRow);
        engineContent.appendChild(execSection);

        const project = el('div', 'nl-engine-section');
        project.appendChild(el('h3', '', 'Project context'));
        project.appendChild(el('div', 'nl-muted', 'Project #' + settings.project.id + ' · ' + settings.project.root));
        project.appendChild(el('div', 'nl-muted', 'Engine: ' + (current.engine ? (current.engine.name + ' ' + current.engine.version) : '—')));
        project.appendChild(el('div', 'nl-muted', 'Model config: ' + settings.models.config_path));
        project.appendChild(el('div', 'nl-muted', 'Chat default: ' + (settings.models.chat_default_spec || 'not configured') + ' (role ' + settings.models.chat_role + ')'));
        project.appendChild(el('div', 'nl-muted', 'Mission defaults: ' + settings.mission_defaults.developer_model + ' / ' + settings.mission_defaults.reviewer_model));
        engineContent.appendChild(project);

        const permission = el('div', 'nl-engine-section');
        permission.appendChild(el('h3', '', 'Permissions (read-only, backend-owned)'));
        const table = el('div', 'nl-permissions');
        (settings.permissions.scopes || []).forEach(function (scope) {
            const row = el('div', 'nl-permission');
            row.appendChild(el('span', '', scope.toUpperCase()));
            row.appendChild(el('span', 'nl-muted', settings.permissions.policy[scope] ? 'Granted' : 'Denied'));
            table.appendChild(row);
        });
        permission.appendChild(table);
        permission.appendChild(el('div', 'nl-muted', 'Cloud escalation: ' + (settings.permissions.cloud_escalation_enabled ? 'enabled' : 'disabled')));
        engineContent.appendChild(permission);

        const agents = el('div', 'nl-engine-section');
        agents.appendChild(el('h3', '', 'Agent roles'));
        (settings.agents.roles || []).forEach(function (role) {
            const row = el('div', 'nl-permission');
            row.appendChild(el('span', '', role.role));
            row.appendChild(el('span', 'nl-muted', role.model + (role.note ? ' · ' + role.note : '')));
            agents.appendChild(row);
        });
        engineContent.appendChild(agents);

        const providers = el('div', 'nl-engine-section');
        providers.appendChild(el('h3', '', 'Providers and live models'));
        (settings.models.providers || []).forEach(function (provider) {
            const discovered = (settings.models.discovered && settings.models.discovered.providers || []).filter(function (item) {
                return item.provider_id === provider.provider_id;
            })[0];
            const row = el('div', 'nl-engine-section');
            row.appendChild(el('div', '', provider.label + ' (' + provider.kind + ') · ' + (provider.enabled ? 'enabled' : 'disabled')));
            row.appendChild(el('div', 'nl-muted', provider.base_url));
            if (discovered) {
                row.appendChild(el('div', 'nl-muted', discovered.reachable
                    ? discovered.models.length + ' models available'
                    : 'unreachable: ' + (discovered.error || '')));
                discovered.models.forEach(function (model) {
                    const line = el('div', 'nl-model');
                    line.appendChild(el('span', '', model.name));
                    if (model.loaded) { line.appendChild(chip('loaded', 'ok')); }
                    if (model.size_gb) { line.appendChild(el('span', 'nl-muted', model.size_gb + ' GB')); }
                    row.appendChild(line);
                });
            }
            providers.appendChild(row);
        });
        if (!settings.models.discovered) {
            providers.appendChild(el('p', 'nl-muted', 'Model probe not run. Use "Probe models" to discover live Ollama models.'));
        }
        engineContent.appendChild(providers);
    }

    function renderState() {
        if (!state) { return; }
        renderHeader(state);
        renderBanner(state);
        renderModelSelectors(state);
        renderMissionList(state);
        renderMissionDetail(state);
        renderEngine(state);
        if (mode === 'mission') {
            missionFields.classList.remove('hidden');
            missionNote.classList.remove('hidden');
            sendEl.textContent = 'Start mission';
        }
    }

    function submit() {
        const text = inputEl.value.trim();
        if (!text || (state && (state.busyChat || state.busyMission))) {
            return;
        }
        if (mode === 'mission') {
            postAction('startMission', {
                goal: text,
                developerModel: devModelEl.value,
                reviewerModel: reviewerModelEl.value
            });
            append('user', text);
        } else if (text.indexOf('/mission ') === 0) {
            postAction('startMission', {
                goal: text.slice('/mission '.length).trim(),
                developerModel: devModelEl.value,
                reviewerModel: reviewerModelEl.value
            });
            append('user', text);
        } else {
            append('user', text);
            postAction('sendChat', { text: text });
        }
        inputEl.value = '';
        inputEl.focus();
    }

    composer.addEventListener('submit', function (event) {
        event.preventDefault();
        submit();
    });

    inputEl.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            submit();
        }
    });

    modeEl.addEventListener('change', function () { setMode(modeEl.value); });
    chatModelEl.addEventListener('change', function () {
        postAction('setChatModel', { value: chatModelEl.value });
    });
    function missionModelsChanged() {
        postAction('setMissionModels', {
            developerModel: devModelEl.value,
            reviewerModel: reviewerModelEl.value
        });
    }
    devModelEl.addEventListener('change', missionModelsChanged);
    reviewerModelEl.addEventListener('change', missionModelsChanged);

    tabButtons.forEach(function (button) {
        button.addEventListener('click', function () { switchTab(button.dataset.tab); });
    });

    execToggle.addEventListener('click', function () { postAction('toggleExecution', {}); });
    $('refresh-missions').addEventListener('click', function () { postAction('refreshMissions', {}); });
    $('refresh-engine').addEventListener('click', function () { postAction('refreshEngine', {}); });
    $('refresh-models').addEventListener('click', function () { postAction('refreshEngine', {}); });
    bannerStop.addEventListener('click', function () {
        if (state && state.activeMissionId) { postAction('cancelMission', { missionId: state.activeMissionId }); }
    });
    bannerResume.addEventListener('click', function () {
        if (state && state.activeMissionId) { postAction('resumeMission', { missionId: state.activeMissionId }); }
    });
    bannerDetails.addEventListener('click', function () {
        if (state && state.activeMissionId) {
            postAction('selectMission', { missionId: state.activeMissionId });
            switchTab('missions');
        }
    });

    window.addEventListener('message', function (event) {
        const message = event.data || {};
        if (message.type === 'state') {
            state = message.payload;
            renderState();
        } else if (message.type === 'chat') {
            append(message.role || 'system', message.text);
        } else if (message.type === 'navigate' && message.tab) {
            switchTab(message.tab);
        } else if (message.type === 'status') {
            setStatus(message.label || '', message.state || '');
        } else if (message.type === 'focus') {
            inputEl.focus();
        }
    });

    const saved = vscode.getState();
    if (saved && Array.isArray(saved.transcript)) {
        saved.transcript.forEach(function (item) {
            if (item && item.role && typeof item.text === 'string' && transcript.length < 120) {
                transcript.push(item);
                renderMessage(item);
            }
        });
    }
    if (saved && saved.tab && panels[saved.tab]) {
        switchTab(saved.tab);
    }
    if (saved && saved.mode) {
        setMode(saved.mode);
    }

    setStatus('Connecting to NL Coding Agent…', 'connecting');
    setTimeout(function () { inputEl.focus(); }, 50);
    vscode.postMessage({ type: 'ready' });
})();
