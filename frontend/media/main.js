// NL dashboard webview script. Plain browser JavaScript: the VS Code webview
// does not run TypeScript. All engine/model text is rendered with textContent.
(function () {
    'use strict';

    const vscode = acquireVsCodeApi();
    const $ = function (id) { return document.getElementById(id); };

    const statusEl = $('status');
    const projectBadge = $('project-badge');
    const modelBadge = $('model-badge');
    const execToggle = $('exec-toggle');
    const noticeEl = $('notice');
    const tabButtons = Array.prototype.slice.call(document.querySelectorAll('.nl-tab-button'));
    const panels = { chat: $('tab-chat'), missions: $('tab-missions'), agents: $('tab-agents'), engine: $('tab-engine') };

    const banner = $('mission-banner');
    const bannerTitle = $('banner-title');
    const bannerStatus = $('banner-status');
    const bannerBar = $('banner-progress-bar');
    const bannerCounts = $('banner-counts');
    const bannerStop = $('btn-banner-stop');
    const bannerResume = $('btn-banner-resume');
    const bannerDetails = $('btn-banner-details');
    const chatStop = $('btn-chat-stop');

    const researchCard = $('research-card');
    const researchOutcome = $('research-outcome');
    const researchTitle = $('research-title');
    const researchUrl = $('research-url');
    const researchMeta = $('research-meta');
    const researchText = $('research-text');
    const researchWarnings = $('research-warnings');
    const researchUse = $('research-use');
    const researchDismiss = $('research-dismiss');

    const messagesEl = $('messages');
    const composer = $('composer');
    const inputEl = $('input');
    const modeEl = $('mode');
    const providerSelectEl = $('provider-select');
    const chatModelEl = $('chat-model');
    const autoModelEl = $('auto-model');
    const autoCodingEl = $('auto-coding');
    const modelCurrentEl = $('model-current');
    const modelBar = $('model-bar');
    const contextStrip = $('context-strip');
    const editorContextEl = $('editor-context');
    const attachmentChipsEl = $('attachment-chips');
    const attachFilesEl = $('attach-files');
    const dictateEl = $('dictate');
    const attachCurrentEl = $('attach-current');
    const attachSelectionEl = $('attach-selection');
    const dropOverlay = $('drop-overlay');
    const missionFields = $('mission-fields');
    const devModelEl = $('dev-model');
    const reviewerModelEl = $('reviewer-model');
    const missionNote = $('mission-note');
    const hintEl = $('hint');
    const sendEl = $('send');
    const slashMenuEl = $('slash-menu');

    const missionListEl = $('mission-list');
    const missionDetailEl = $('mission-detail');
    const engineContent = $('engine-content');
    const sessionSelectEl = $('chat-session');
    const chatQueueEl = $('chat-queue');
    const storageListEl = $('storage-list');
    const jobsListEl = $('jobs-list');
    const probeSelectEl = $('probe-model');
    const speechEngineEl = $('speech-engine');
    const speechModelEl = $('speech-model');
    const speechStatusEl = $('speech-status');
    const speechEnginesEl = $('speech-engines');
    const accessProfileEl = $('chat-access-profile');
    const accessStatusEl = $('chat-access-status');
    const specialistSelectEl = $('specialist-list');
    const specialistProviderEl = $('specialist-provider');
    const specialistNameEl = $('specialist-name');
    const specialistModelEl = $('specialist-model');
    const specialistRoleEl = $('specialist-role');
    const specialistInstructionsEl = $('specialist-instructions');
    const specialistToolsEl = $('specialist-tools');
    const specialistEnabledEl = $('specialist-enabled');
    let storageSelected = {};
    let selectedMissionIds = Object.create(null);
    let missionSelectionProjectId = null;
    let chatControlsVisible = true;
    let contextVisible = true;
    let missionFieldsVisible = true;
    let missionListVisible = true;

    const labels = { user: 'You', assistant: 'NL', system: 'NL', error: 'Error' };
    const transcript = [];
    let state = null;
    let mode = 'chat';
    let tab = 'chat';
    let rendering = false;
    let dragDepth = 0;
    let slashMode = 'command';
    let fileMentionResults = [];
    let fileMentionSearchQuery = null;
    let fileMentionSearchTimer = null;

    function persist() {
        vscode.setState({ mode: mode, tab: tab });
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

    function append(role, text, extra) {
        const item = Object.assign({ role: role, text: String(text == null ? '' : text) }, extra || {});
        transcript.push(item);
        if (transcript.length > 400) { transcript.shift(); }
        renderMessage(item);
        return item;
    }

    function renderLinks(container, text) {
        const pattern = /https?:\/\/[^\s<>"']+|(?<![\w./-])(?:www\.)?(?:[a-z0-9-]+\.)+[a-z]{2,24}(?:\/[^\s<>"']*)?/gi;
        const fileExtensions = new Set([
            'md', 'json', 'py', 'js', 'ts', 'tsx', 'jsx', 'yaml', 'yml', 'txt',
            'html', 'css', 'sh', 'ps1', 'toml', 'lock', 'xml', 'csv', 'png',
            'jpg', 'jpeg', 'pdf', 'zip', 'sql', 'ini', 'cfg', 'env', 'go',
            'rs', 'java', 'c', 'cpp', 'h', 'hpp'
        ]);
        let last = 0;
        let match;
        while ((match = pattern.exec(text)) !== null) {
            const raw = match[0].replace(/[),.;!?]+$/, '');
            if (!raw) { continue; }
            const candidate = /^https?:\/\//i.test(raw) ? raw : 'https://' + raw;
            const parts = /^(https?):\/\/([^/?#]+)([\s\S]*)$/i.exec(candidate);
            if (!parts) { continue; }
            const hostname = parts[2].replace(/:\d+$/, '').toLowerCase();
            const tld = hostname.split('.').pop() || '';
            if (fileExtensions.has(tld)) { continue; }
            const target = candidate + (parts[3] ? '' : '/');
            if (match.index > last) {
                container.appendChild(el('span', '', text.slice(last, match.index)));
            }
            const link = el('a', 'nl-link', raw);
            link.href = target;
            link.title = 'Fetch this page through Research (explicit action, permissions apply)';
            link.addEventListener('click', function (event) {
                event.preventDefault();
                postAction('fetchUrl', { url: target });
            });
            container.appendChild(link);
            last = match.index + raw.length;
        }
        if (last < text.length) {
            container.appendChild(el('span', '', text.slice(last)));
        }
    }

    function attachmentLine(item) {
        const kind = item.kind || 'file';
        const size = item.size_bytes ? ' · ' + Math.max(1, Math.round(item.size_bytes / 1024)) + ' KB' : '';
        return kind + size;
    }

    function renderMessage(item) {
        const wrap = el('div', 'nl-message nl-message-' + item.role);
        const head = el('div', 'nl-message-head');
        head.appendChild(el('span', 'nl-message-label', labels[item.role] || item.role));
        if (item.created_at) {
            head.appendChild(el('span', 'nl-muted', String(item.created_at).replace('T', ' ').slice(0, 16)));
        }
        if (item.model) {
            head.appendChild(el('span', 'nl-message-model', 'via ' + item.model));
        }
        wrap.appendChild(head);
        const body = el('div', 'nl-message-body');
        renderLinks(body, item.text);
        wrap.appendChild(body);
        if (item.id) {
            const actions = el('div', 'nl-message-actions');
            if (item.role === 'user') {
                const edit = el('button', '', 'Edit & rewind');
                edit.title = 'Edit this request and discard it plus every later message.';
                edit.addEventListener('click', function () {
                    postAction('rewindMessage', { messageId: item.id, edit: true });
                });
                actions.appendChild(edit);
            } else if (item.role === 'assistant') {
                const rewind = el('button', '', 'Rewind');
                rewind.title = 'Discard this reply and every later message; the request before it stays.';
                rewind.addEventListener('click', function () {
                    postAction('rewindMessage', { messageId: item.id, edit: false });
                });
                actions.appendChild(rewind);
            }
            if (actions.children.length) { wrap.appendChild(actions); }
        }
        const attachments = item.attachments || [];
        if (attachments.length) {
            const chips = el('div', 'nl-message-attachments');
            attachments.forEach(function (attachment) {
                const chip = el('span', 'nl-attachment-history');
                chip.appendChild(el('span', '', attachment.name || 'attachment'));
                chip.appendChild(el('span', 'nl-muted', attachmentLine(attachment)));
                if (attachment.kind === 'image') {
                    chip.appendChild(el('span', 'nl-warning-inline', 'Vision image'));
                } else if (!attachment.has_text) {
                    chip.appendChild(el('span', 'nl-warning-inline', 'no text'));
                }
                chips.appendChild(chip);
            });
            wrap.appendChild(chips);
        }
        messagesEl.appendChild(wrap);
        messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    function renderHistory(messages) {
        clear(messagesEl);
        transcript.length = 0;
        (messages || []).forEach(function (message) {
            renderMessage({
                id: message.id,
                role: message.role,
                text: message.content,
                created_at: message.created_at,
                attachments: message.attachments,
                model: message.model || message.provider_id,
                tool_activity: message.tool_activity
            });
        });
        if (!messages || !messages.length) {
            renderMessage({
                role: 'system',
                text: 'No saved conversation for this project yet. Messages are persisted by the engine.'
            });
        }
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
        missionFields.classList.toggle('hidden', mode !== 'mission' || !missionFieldsVisible);
        missionNote.classList.toggle('hidden', mode !== 'mission' || !missionFieldsVisible);
        $('mission-fields-toggle').classList.toggle('hidden', mode !== 'mission');
        if (modelBar) { modelBar.classList.toggle('hidden', mode === 'mission' || !chatControlsVisible); }
        if (contextStrip) { contextStrip.classList.toggle('hidden', mode === 'mission' || !contextVisible); }
        sendEl.textContent = mode === 'mission' ? 'Start mission' : 'Send';
        if (state) { renderContext(state); }
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
    function fmtBytes(value) {
        const bytes = Number(value) || 0;
        return (bytes / 1024 / 1024).toFixed(2) + ' MB';
    }

    function renderSessions(current) {
        const sessions = current.chatSessions || [];
        const selected = current.currentSessionId || '';
        clear(sessionSelectEl);
        sessions.forEach(function (session) {
            const option = el('option', '', (session.title || '(untitled)') +
                (session.archived_at ? ' · archived' : '') +
                (typeof session.message_count === 'number' ? ' · ' + session.message_count : ''));
            option.value = session.id;
            if (session.id === selected) { option.selected = true; }
            sessionSelectEl.appendChild(option);
        });
        sessionSelectEl.value = selected;
        $('session-archived-toggle').checked = Boolean(current.showArchivedSessions);    }

    function renderQueue(current) {
        clear(chatQueueEl);
        const items = current.chatQueue || [];
        if (!items.length) {
            chatQueueEl.classList.add('hidden');
            return;
        }
        chatQueueEl.classList.remove('hidden');
        items.forEach(function (item) {
            const row = el('div', 'nl-queue-row');
            row.appendChild(el('span', 'nl-queue-mode', item.mode || 'queue'));
            row.appendChild(el('span', 'nl-queue-text', item.text || ''));
            const remove = el('button', '', 'Remove');
            remove.type = 'button';
            remove.addEventListener('click', function () {
                postAction('removeQueueItem', { itemId: item.id });
            });
            row.appendChild(remove);
            chatQueueEl.appendChild(row);
        });
    }

    function renderStorage(current) {
        const storage = current.storage;
        clear(storageListEl);
        if (!storage) { return; }
        $('storage-total').textContent = fmtBytes(storage.total_bytes) + ' total';
        (storage.items || []).forEach(function (item) {
            const row = el('label', 'nl-storage-row');
            const check = el('input');
            check.type = 'checkbox';
            check.disabled = !item.deletable;
            check.checked = Boolean(storageSelected[item.id]);
            check.addEventListener('change', function () {
                storageSelected[item.id] = check.checked;
            });
            row.appendChild(check);
            row.appendChild(el('span', 'nl-storage-category', item.category || ''));
            row.appendChild(el('span', 'nl-muted', fmtBytes(item.bytes) + ' · ' + item.files + ' files'));
            row.appendChild(el('span', 'nl-muted', item.deletable ? 'deletable' : 'protected'));
            storageListEl.appendChild(row);
        });
    }

    function setValueIfIdle(id, value) {
        const node = $(id);
        if (!node || document.activeElement === node) { return; }
        node.value = value === undefined || value === null ? '' : String(value);
    }

    function modelChoices(provider) {
        return (stateModelOptions() || []).filter(function (option) {
            return option.value && (!provider || option.provider === provider);
        }).map(function (option) {
            return { value: option.value, label: option.value };
        });
    }

    function populateModelSelect(node, options, selected) {
        if (!node) { return; }
        clear(node);
        const items = options.slice();
        if (selected && !items.some(function (item) { return item.value === selected; })) {
            items.push({ value: selected, label: selected });
        }
        items.forEach(function (item) {
            const option = el('option', '', item.label);
            option.value = item.value;
            node.appendChild(option);
        });
        node.value = selected || '';
    }

    function checkedValues(container) {
        if (!container) { return []; }
        return Array.prototype.slice.call(container.querySelectorAll('input[type="checkbox"]'))
            .filter(function (input) { return input.checked; })
            .map(function (input) { return input.value; })
            .filter(Boolean);
    }

    function setCheckedValues(container, values) {
        if (!container) { return; }
        const wanted = {};
        (values || []).forEach(function (value) { wanted[String(value)] = true; });
        Array.prototype.forEach.call(container.querySelectorAll('input[type="checkbox"]'), function (input) {
            input.checked = Boolean(wanted[input.value]);
        });
    }

    function fillSpecialist(agent) {
        specialistNameEl.value = agent ? (agent.name || '') : '';
        specialistProviderEl.value = agent ? (agent.provider || 'ollama') : 'ollama';
        specialistModelEl.value = agent ? (agent.model || '') : '';
        specialistRoleEl.value = agent ? (agent.role || 'assistant') : 'assistant';
        specialistInstructionsEl.value = agent ? (agent.instructions || '') : '';
        setCheckedValues(specialistToolsEl, agent ? (agent.tools || []) : []);
        specialistEnabledEl.checked = agent ? agent.enabled !== false : true;
    }

    function selectedSpecialist(current) {
        const agents = current.settings.agents.custom_agents || [];
        const id = specialistSelectEl.value;
        return agents.filter(function (agent) { return String(agent.id) === String(id); })[0];
    }

    function renderSpecialists(current) {
        const settings = current.settings;
        const agents = settings.agents.custom_agents || [];
        const providers = settings.models.providers || [];
        const projectId = Number(current.project && current.project.id || settings.project.id);
        const selected = specialistSelectEl.value;
        clear(specialistSelectEl);
        const empty = el('option', '', agents.length ? 'Select specialist…' : 'No specialist agents yet');
        empty.value = '';
        specialistSelectEl.appendChild(empty);
        agents.forEach(function (agent) {
            const active = agent.team_active === true &&
                Number(agent.project_id) === projectId;
            const scope = active ? ' · active team' :
                (agent.project_id != null && Number(agent.project_id) !== projectId
                    ? ' · another project' : '');
            const option = el('option', '', (agent.name || 'Specialist') +
                (agent.enabled === false ? ' (disabled)' : '') + scope);
            option.value = String(agent.id || '');
            specialistSelectEl.appendChild(option);
        });
        if (selected && agents.some(function (agent) { return String(agent.id) === selected; })) {
            specialistSelectEl.value = selected;
        }
        const providerSelected = specialistProviderEl.value;
        clear(specialistProviderEl);
        const seen = {};
        [{ provider_id: 'ollama', label: 'Ollama' }].concat(providers).forEach(function (provider) {
            const id = provider.provider_id || provider.id;
            if (!id || seen[id]) { return; }
            seen[id] = true;
            const option = el('option', '', (provider.label || id) + ' (' + id + ')');
            option.value = id;
            specialistProviderEl.appendChild(option);
        });
        if (providerSelected && specialistProviderEl.querySelector('option[value="' + providerSelected + '"]')) {
            specialistProviderEl.value = providerSelected;
        }
        const selectedAgent = selectedSpecialist(current);
        const chosenModel = selectedAgent ? selectedAgent.model : specialistModelEl.value;
        populateModelSelect(specialistModelEl, modelChoices(specialistProviderEl.value), chosenModel);
        const status = $('specialist-team-status');
        if (selectedAgent && selectedAgent.team_active === true &&
                Number(selectedAgent.project_id) === projectId) {
            status.textContent = 'Active in current project Supervisor team as '
                + (selectedAgent.role_id || selectedAgent.role || 'specialist')
                + '. Project Access controls all operational permissions.';
        } else if (selectedAgent && selectedAgent.project_id != null &&
                Number(selectedAgent.project_id) !== projectId) {
            status.textContent = 'This profile belongs to another project and is not used by the current Supervisor.';
        } else {
            status.textContent = 'Profile only; Generate team links Supervisor specialists to this project. Project Access controls operational permissions.';
        }
    }

    function renderJobs(current) {
        if (!jobsListEl) { return; }
        clear(jobsListEl);
        const jobs = current.jobs || [];
        if (!jobs.length) {
            jobsListEl.appendChild(el('div', 'nl-muted', 'No background jobs for this project.'));
            return;
        }
        jobs.forEach(function (job) {
            const row = el('div', 'nl-queue-row');
            row.appendChild(el('span', 'nl-queue-mode', String(job.status || 'unknown')));
            row.appendChild(el('span', 'nl-queue-text', String(job.label || job.id) +
                ' · ' + (job.argv || []).join(' ')));
            const output = el('button', '', 'Output');
            output.addEventListener('click', function () {
                postAction('jobOutput', { jobId: job.id });
            });
            row.appendChild(output);
            if (job.status === 'running' || job.status === 'starting') {
                const stop = el('button', '', 'Stop');
                stop.addEventListener('click', function () {
                    postAction('stopJob', { jobId: job.id });
                });
                row.appendChild(stop);
            }
            jobsListEl.appendChild(row);
        });
    }

    function renderSpeech(current, requestedEngine) {
        const payload = (current && current.speech) || {};
        const speech = payload.speech || payload;
        const catalog = payload.catalog || {};
        const models = catalog.models || [];
        const downloadable = catalog.downloadable_models || [];
        const active = speech.active_model || catalog.active_model || {};
        const previousEngine = speechEngineEl.value;
        const previousModel = speechModelEl.value;
        const engines = catalog.engines || [];
        clear(speechEngineEl);
        engines.forEach(function (engine) {
            const option = el('option', '', engine.engine + ' · ' +
                (engine.installed ? 'installed' : 'not installed'));
            option.value = engine.engine;
            speechEngineEl.appendChild(option);
        });
        let selectedEngine = requestedEngine;
        if (!engines.some(function (engine) { return engine.engine === selectedEngine; })) {
            selectedEngine = active.engine;
        }
        if (!engines.some(function (engine) { return engine.engine === selectedEngine; })) {
            selectedEngine = previousEngine;
        }
        if (!engines.some(function (engine) { return engine.engine === selectedEngine; })) {
            selectedEngine = (engines[0] && engines[0].engine) || '';
        }
        if (selectedEngine) { speechEngineEl.value = selectedEngine; }

        clear(speechModelEl);
        const engineModels = models.filter(function (model) {
            return model.engine === selectedEngine;
        });
        const engineDownloads = downloadable.filter(function (model) {
            return model.engine === selectedEngine &&
                !engineModels.some(function (local) { return local.model_id === model.model_id; });
        });
        const placeholder = el('option', '', 'Select a local model…');
        placeholder.value = '';
        speechModelEl.appendChild(placeholder);
        engineModels.forEach(function (model) {
            const option = el('option', '', model.model_id + ' · local');
            option.value = model.model_id;
            option.title = model.path || '';
            speechModelEl.appendChild(option);
        });
        engineDownloads.forEach(function (model) {
            const label = model.model_id + ' · download · ' + (model.language || '') + ' · ' +
                model.size_mb + ' MB · ' + (model.license || 'check license');
            const option = el('option', '', label);
            option.value = model.model_id;
            option.dataset.downloadModel = 'true';
            speechModelEl.appendChild(option);
        });
        const currentModelExists = engineModels.concat(engineDownloads).some(function (model) {
            return model.model_id === previousModel;
        });
        if (active.engine === selectedEngine && engineModels.some(function (model) {
            return model.model_id === active.model_id;
        })) {
            speechModelEl.value = active.model_id;
        } else if (currentModelExists) {
            speechModelEl.value = previousModel;
        } else if (engineModels.length) {
            speechModelEl.value = engineModels[0].model_id;
        } else {
            speechModelEl.value = '';
        }
        const selectedOption = Array.prototype.slice.call(speechModelEl.children).filter(function (option) {
            return option.value === speechModelEl.value;
        })[0];
        const downloadSelected = Boolean(selectedOption && selectedOption.dataset.downloadModel);
        $('speech-select').textContent = downloadSelected ? 'Download model' : 'Use model';
        const selectedEngineInfo = engines.filter(function (engine) {
            return engine.engine === selectedEngine;
        })[0];
        $('speech-select').disabled = !speechModelEl.value ||
            !(selectedEngineInfo && selectedEngineInfo.installed);
        const audio = speech.audio_available ? 'microphone ready' : 'no microphone backend';
        speechStatusEl.textContent = engines.length
            ? 'Local ASR · ' + audio + ' · ' + models.length + ' local model(s)'
            : 'No local ASR engine detected. Register an external folder or install a local engine.';
        if (active.path) {
            speechStatusEl.textContent += ' · active: ' + active.model_id + ' (' + active.path + ')';
        } else if (models.length) {
            speechStatusEl.textContent += ' · select a model to enable dictation';
        }
        clear(speechEnginesEl);
        engines.forEach(function (engine) {
            const row = el('div', 'nl-list-row');
            row.appendChild(el('strong', '', engine.engine));
            row.appendChild(el('span', engine.installed ? 'nl-chip ok' : 'nl-muted',
                engine.installed ? 'installed' : 'optional / not installed'));
            if (engine.hint) { row.appendChild(el('span', 'nl-muted', engine.hint)); }
            speechEnginesEl.appendChild(row);
        });
        if (!engines.length) {
            speechEnginesEl.appendChild(el('p', 'nl-muted',
                'No speech engine catalog available. Vosk, Qwen3-ASR, Faster-Whisper and Whisper.cpp can be supplied as local engines/models.'));
        }
    }

    function renderAccess(current) {
        const payload = (current && current.accessProfile) || {};
        accessProfileEl.value = payload.profile || 'auto-review';
        accessStatusEl.textContent = payload.profile
            ? 'applied to every agent' + (payload.auto_review_profile ? ' · auto-review: ' + payload.auto_review_profile : '') +
              (payload.profile === 'auto-review' ? ' · deletes move to da_eliminare' : '')
            : 'applying Auto review to every agent';
    }

    function renderSettings(current) {
        const settings = current.settings;
        if (!settings) { return; }
        renderSpecialists(current);
        renderSpeech(current);
        renderJobs(current);
        const providerSelect = $('provider-edit');
        const previous = providerSelect.value;
        clear(providerSelect);
        (settings.models.providers || []).forEach(function (provider) {
            const option = el('option', '', provider.label + ' (' + provider.provider_id + ')');
            option.value = provider.provider_id;
            providerSelect.appendChild(option);
        });
        if (previous) { providerSelect.value = previous; }
        if (!providerSelect.value && providerSelect.children.length) {
            providerSelect.value = providerSelect.children[0].value;
        }
        const providerId = providerSelect.value;
        const provider = (settings.models.providers || []).filter(function (item) {
            return item.provider_id === providerId;
        })[0];
        if (provider) {
            $('provider-enabled').checked = Boolean(provider.enabled);
            setValueIfIdle('provider-url', provider.base_url);
            setValueIfIdle('provider-id', provider.provider_id);
            $('provider-kind').value = provider.kind || 'openai_compatible';
            setValueIfIdle('provider-label', provider.label);
            setValueIfIdle('provider-api-key-env', provider.api_key_env);
        }
        const role = $('role-edit').value;
        const roleConfig = (settings.models.roles || {})[role];
        populateModelSelect($('role-model-edit'), modelChoices(''), roleConfig && roleConfig.model);
        populateModelSelect($('generation-model'), modelChoices(''),
            current.chatModel || settings.models.chat_default_spec || '');
        const generation = current.generationParams && current.generationParams.effective || {};
        setValueIfIdle('generation-temperature', generation.temperature);
        setValueIfIdle('generation-top-p', generation.top_p);
        setValueIfIdle('generation-top-k', generation.top_k);
        setValueIfIdle('generation-min-p', generation.min_p);
        setValueIfIdle('generation-repeat', generation.repeat_penalty);
        setValueIfIdle('generation-seed', generation.seed);
        setValueIfIdle('generation-max', generation.max_tokens);
        setValueIfIdle('generation-context', generation.num_ctx || '');
        const autonomy = current.autonomy || {};
        $('autonomy-mode').value = autonomy.mode || 'off';
        setValueIfIdle('autonomy-missions', autonomy.max_missions_per_run);
        setValueIfIdle('autonomy-attempts', autonomy.max_attempts_per_requirement);
        $('cloud-policy').checked = Boolean(settings.models.cloud_escalation_enabled);
        const mcp = $('mcp-json');
        if (document.activeElement !== mcp) {
            mcp.value = JSON.stringify(current.mcpConfig || { servers: {} }, null, 2);
        }
        const probe = $('probe-model');
        const probePrevious = probe.value;
        clear(probe);
        (current.modelOptions || []).forEach(function (option) {
            if (!option.value) { return; }
            const node = el('option', '', option.label);
            node.value = option.value;
            probe.appendChild(node);
        });
        if (probePrevious) { probe.value = probePrevious; }
        const result = current.capabilityProbe;
        $('probe-result').textContent = result
            ? result.provider_id + '/' + result.model + ': tools=' + result.tool_calling +
                            ', structured=' + result.structured_output + ', patch=' + result.patch_quality +
                            ', vision=' + (result.vision || 'unknown')
            : '';
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

    function routeProvider(route) {
        const slash = String(route || '').indexOf('/');
        return slash > 0 ? route.slice(0, slash) : '';
    }

    function routeModel(route) {
        const slash = String(route || '').indexOf('/');
        return slash > 0 ? route.slice(slash + 1) : String(route || '');
    }

    function renderModelBar(current) {
        const options = current.modelOptions || [];
        populateSelect(devModelEl, options, current.missionModels ? current.missionModels.developerModel : '');
        populateSelect(reviewerModelEl, options, current.missionModels ? current.missionModels.reviewerModel : '');
        const auto = !current.chatModel;
        autoModelEl.checked = auto;
        autoCodingEl.checked = Boolean(current.autoCoding);
        autoCodingEl.disabled = !current.executionEnabled;

        const providers = [{ value: '', label: 'All providers' }];
        const seenProviders = { '': true };
        function addProvider(id, label) {
            if (!id || seenProviders[id]) { return; }
            seenProviders[id] = true;
            providers.push({ value: id, label: label || id });
        }
        (current.providers || []).filter(function (provider) { return provider.enabled; })
            .forEach(function (provider) { addProvider(provider.id, provider.label); });
        options.forEach(function (option) {
            if (option.value) { addProvider(option.provider, option.provider); }
        });
        const selectedProvider = current.providerFilter || '';
        populateSelect(providerSelectEl, providers, selectedProvider);
        if (selectedProvider && !providers.some(function (provider) { return provider.value === selectedProvider; })) {
            populateSelect(providerSelectEl, providers, '');
        }
        // Keep both selectors usable even in Automatic mode: choosing a model
        // is how the user leaves Automatic, without hunting for a checkbox.
        providerSelectEl.disabled = false;
        chatModelEl.disabled = false;
        const automaticOption = {
            value: '',
            label: 'Automatic — ' + (current.defaultChatSpec || 'engine default')
                + (current.chatRole ? ' (' + current.chatRole + ')' : '')
        };
        const models = options.filter(function (option) {
            return option.value && (!selectedProvider || option.provider === selectedProvider);
        }).map(function (option) {
            return {
                value: option.value,
                label: (selectedProvider ? '' : (option.provider ? option.provider + ' · ' : ''))
                    + option.label
            };
        });
        models.unshift(automaticOption);
        populateSelect(chatModelEl, models, current.chatModel || '');
        modelCurrentEl.textContent = auto
            ? 'Automatic · ' + (current.defaultChatSpec || 'engine default')
            : 'Explicit · ' + current.chatModel;
        modelBadge.textContent = auto
            ? 'auto: ' + (current.defaultChatSpec || 'engine default')
            : 'model: ' + current.chatModel;
        modelBadge.title = current.lastRoute
            ? 'Last reply via ' + current.lastRoute.provider_id + '/' + current.lastRoute.model
            : '';
        const phaseText = {
            thinking: 'Waiting for the model…',
            attaching: 'Preparing attachment…',
            fetching: 'Fetching page through Research…',
            mission: 'Mission running…'
        }[current.busyPhase] || '';
        hintEl.textContent = phaseText || (current.busyChat
            ? 'Running — a new message is queued; start it with /steer to redirect at the next checkpoint.'
            : current.busyMission ? 'Mission running — messages are sent as steering; /mission waits.' : '');
        sendEl.disabled = current.busyPhase === 'attaching';
        sendEl.textContent = mode === 'mission' ? 'Start mission' : (current.busyChat ? 'Queue' : 'Send');
        chatStop.classList.toggle('hidden', !current.busyChat);
    }

    function renderEditorContext(current) {
        clear(editorContextEl);
        const editor = current.editor;
        if (!editor) {
            editorContextEl.appendChild(el('span', 'nl-muted', 'No active editor context'));
            return;
        }
        const label = el('span', 'nl-editor-label');
        label.appendChild(el('span', '', editor.relativePath || editor.path || 'editor'));
        if (editor.hasSelection) {
            label.appendChild(el('span', 'nl-muted', ' · ' + editor.selectionLines + ' selected line(s)'));
        }
        if (editor.dirty) {
            label.appendChild(el('span', 'nl-warning-inline', ' · unsaved'));
        }
        editorContextEl.appendChild(label);
    }

    function renderAttachments(current) {
        clear(attachmentChipsEl);
        const attachments = current.attachments || [];
        if (!attachments.length) {
            attachmentChipsEl.appendChild(el('span', 'nl-muted', 'No attachments'));
            return;
        }
        attachments.forEach(function (attachment) {
            const chip = el('span', 'nl-attachment-chip');
            chip.appendChild(el('span', 'nl-attachment-name', attachment.name || 'attachment'));
            chip.appendChild(el('span', 'nl-muted', attachmentLine(attachment)));
            if (attachment.kind === 'image') {
                const metadata = attachment.metadata || {};
                const dimensions = metadata.width && metadata.height
                    ? ' · ' + metadata.width + '×' + metadata.height
                    : '';
                chip.appendChild(el('span', 'nl-status-chip', 'Vision' + dimensions));
            } else if (!attachment.has_text) {
                chip.appendChild(el('span', 'nl-warning-inline', 'no text'));
            }
            if (attachment.preview) {
                const details = el('details', 'nl-attachment-preview');
                details.appendChild(el('summary', 'nl-muted', 'preview'));
                details.appendChild(el('pre', 'nl-output', attachment.preview));
                chip.appendChild(details);
            }
            const remove = el('button', 'nl-chip-remove', '×');
            remove.type = 'button';
            remove.title = 'Remove from this message';
            remove.addEventListener('click', function (event) {
                event.stopPropagation();
                postAction('removeAttachment', { attachmentId: attachment.id });
            });
            chip.appendChild(remove);
            attachmentChipsEl.appendChild(chip);
        });
    }

    function renderContext(current) {
        const missionMode = mode === 'mission';
        contextStrip.classList.toggle('hidden', missionMode);
        modelBar.classList.toggle('hidden', missionMode);
        missionFields.classList.toggle('hidden', !missionMode);
        missionNote.classList.toggle('hidden', !missionMode);
        if (missionMode) {
            return;
        }
        renderEditorContext(current);
        renderAttachments(current);
        const busy = Boolean(current.busyChat || current.busyMission || current.busyPhase !== 'idle');
        attachFilesEl.disabled = busy;
        attachCurrentEl.disabled = busy || !current.editor;
        attachSelectionEl.disabled = busy || !current.editor || !current.editor.hasSelection;
        if (dictateEl) {
            dictateEl.disabled = busy;
            dictateEl.textContent = current.dictating ? '■ Stop dictation' : '🎤 Dictate';
            dictateEl.classList.toggle('nl-danger', Boolean(current.dictating));
        }
    }

    function renderResearch(current) {
        const research = current.research;
        if (!research) {
            researchCard.classList.add('hidden');
            return;
        }
        researchCard.classList.remove('hidden');
        researchOutcome.textContent = research.outcome || (research.ok ? 'allowed' : 'not fetched');
        researchOutcome.dataset.kind = research.ok ? 'ok' : (research.outcome === 'needs_approval' ? 'warn' : 'bad');
        researchTitle.textContent = research.title || research.url || 'Fetched page';
        researchUrl.textContent = research.url || '';
        const meta = [];
        if (research.provenance && research.provenance.content_type) {
            meta.push(String(research.provenance.content_type));
        }
        if (research.provenance && research.provenance.size) {
            meta.push(String(research.provenance.size) + ' bytes');
        }
        if (research.text_truncated) {
            meta.push('text truncated');
        }
        if (research.source_id) {
            meta.push('research source #' + research.source_id);
        }
        researchMeta.textContent = meta.join(' · ');
        researchText.textContent = research.text || research.reason || '';
        researchWarnings.classList.toggle('hidden', !(research.injection_warnings && research.injection_warnings.length));
        researchWarnings.textContent = (research.injection_warnings && research.injection_warnings.length)
            ? 'Injection warnings (advisory): ' + research.injection_warnings.length
            : '';
        researchUse.disabled = !(research.ok && research.text);
    }

    function renderMissionList(current) {
        clear(missionListEl);
        const missions = current.missions || [];
        if (missionSelectionProjectId !== current.project.id) {
            missionSelectionProjectId = current.project.id;
            selectedMissionIds = Object.create(null);
        }
        $('mission-query').value = current.missionQuery || '';
        $('mission-status-filter').value = current.missionStatusFilter || '';
        $('mission-archived-toggle').checked = Boolean(current.missionShowArchived);
        if (!missions.length) {
            missionListEl.appendChild(el('p', 'nl-muted', 'No persistent missions for this project.'));
            updateMissionSelectionControls(missions);
            return;
        }
        missions.forEach(function (mission) {
            const row = el('div', 'nl-mission-row');
            const head = el('div', 'nl-mission-row-head');
            const select = el('input', 'nl-mission-select');
            select.type = 'checkbox';
            select.checked = Boolean(selectedMissionIds[String(mission.id)]);
            select.setAttribute('aria-label', 'Select mission #' + mission.id);
            select.addEventListener('click', function (event) { event.stopPropagation(); });
            select.addEventListener('change', function (event) {
                event.stopPropagation();
                if (select.checked) {
                    selectedMissionIds[String(mission.id)] = true;
                } else {
                    delete selectedMissionIds[String(mission.id)];
                }
                updateMissionSelectionControls(missions);
            });
            head.appendChild(select);
            head.appendChild(el('span', 'nl-mission-id', '#' + mission.id));
            head.appendChild(el('span', 'nl-mission-title', mission.title || '(untitled)'));
            head.appendChild(chip(mission.status || '—', statusKind(mission.status)));
            if (mission.archived_at) { head.appendChild(chip('archived', 'neutral')); }
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
            if (mission.status === 'running') {
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
            const remove = el('button', 'nl-danger', 'Delete');
            remove.title = 'Permanently delete this mission record; project files are not changed.';
            remove.addEventListener('click', function (event) {
                event.stopPropagation();
                postAction('deleteMission', { missionId: mission.id });
            });
            actions.appendChild(remove);
            row.appendChild(actions);
            row.addEventListener('click', function () {
                postAction('selectMission', { missionId: mission.id });
                switchTab('missions');
            });
            missionListEl.appendChild(row);
        });
        updateMissionSelectionControls(missions);
    }

    function updateMissionSelectionControls(visibleMissions) {
        const selected = Object.keys(selectedMissionIds);
        const visibleSelected = visibleMissions.filter(function (mission) {
            return Boolean(selectedMissionIds[String(mission.id)]);
        }).length;
        const selectVisible = $('mission-select-visible');
        selectVisible.checked = visibleMissions.length > 0 && visibleSelected === visibleMissions.length;
        selectVisible.indeterminate = visibleSelected > 0 && visibleSelected < visibleMissions.length;
        $('mission-selection-count').textContent = selected.length + ' selected';
        $('mission-selection-clear').disabled = selected.length === 0;
        $('mission-stop-selected').disabled = selected.length === 0;
        $('mission-archive-selected').disabled = selected.length === 0;
        $('mission-delete-selected').disabled = selected.length === 0;
    }

    function selectedMissionIdsList() {
        return Object.keys(selectedMissionIds).map(Number).filter(Number.isInteger);
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
            const mission = (detail && detail.mission) || {};
            if (mission.harness_version === 2 &&
                ['failed', 'blocked', 'interrupted', 'pending'].indexOf(task.status) >= 0 &&
                !['running', 'pending'].includes(mission.status)) {
                const retry = el('button', 'nl-task-retry', 'Retry from here');
                retry.title = 'Reset this task and every later task to pending, then resume the mission.';
                retry.addEventListener('click', function () {
                    postAction('resumeMission', { missionId: mission.id, fromTaskId: task.id });
                });
                row.appendChild(retry);
            }
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
            const metadata = attempt.metadata || {};
            if (metadata.model || metadata.duration_s || (metadata.usage && metadata.usage.total_tokens)) {
                const bits = [];
                if (metadata.model) { bits.push('model ' + metadata.model); }
                if (metadata.provider) { bits.push(metadata.provider); }
                if (metadata.duration_s !== undefined && metadata.duration_s !== null) {
                    bits.push(Number(metadata.duration_s).toFixed(1) + 's');
                }
                if (metadata.usage && metadata.usage.total_tokens) {
                    bits.push(metadata.usage.total_tokens + ' tokens');
                }
                details.appendChild(el('div', 'nl-muted nl-attempt-meta', bits.join(' · ')));
            }
            details.appendChild(el('pre', 'nl-output', (attempt.output || '') + (attempt.error ? '\nERROR: ' + attempt.error : '')));
            wrap.appendChild(details);
        });
        return wrap;
    }

    function renderModelAssignments(detail) {
        const bindings = detail.model_bindings || {};
        const roles = Object.keys(bindings).sort();
        if (!roles.length) {
            return el('p', 'nl-muted', 'No ModelRouter binding snapshot recorded for this mission.');
        }
        const wrap = el('div', 'nl-permissions');
        roles.forEach(function (role) {
            const binding = bindings[role] || {};
            const row = el('div', 'nl-permission');
            row.appendChild(el('span', '', role));
            const model = [binding.provider_id, binding.model_name].filter(Boolean).join('/');
            row.appendChild(el('span', 'nl-muted', model + (binding.source ? ' · ' + binding.source : '')));
            wrap.appendChild(row);
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
        if (mission.status === 'running') {
            const stop = el('button', '', 'Stop');
            stop.addEventListener('click', function () { postAction('cancelMission', { missionId: mission.id }); });
            actions.appendChild(stop);
        }
        if ((mission.status === 'interrupted' || mission.status === 'blocked' || mission.status === 'failed') && mission.harness_version === 2) {
            const resume = el('button', '', 'Resume');
            resume.addEventListener('click', function () { postAction('resumeMission', { missionId: mission.id }); });
            actions.appendChild(resume);
        }
        if (mission.status === 'completed' && mission.promotion_status === 'promoted') {
            const keep = el('button', 'nl-primary', 'Keep changes');
            keep.addEventListener('click', function () { postAction('acceptMission', { missionId: mission.id }); });
            actions.appendChild(keep);
            const reject = el('button', 'nl-danger', 'Reject changes');
            reject.title = 'Restore only the paths changed by this mission from its pre-mission baseline.';
            reject.addEventListener('click', function () { postAction('revertMission', { missionId: mission.id }); });
            actions.appendChild(reject);
        }
        const more = el('details', 'nl-more-actions');
        more.appendChild(el('summary', 'nl-muted', 'More mission actions'));
        const moreRow = el('div', 'nl-actions');
        if (!mission.archived_at) {
            const archive = el('button', '', 'Archive');
            archive.addEventListener('click', function () { postAction('archiveMission', { missionId: mission.id }); });
            moreRow.appendChild(archive);
        } else {
            const unarchive = el('button', '', 'Unarchive');
            unarchive.addEventListener('click', function () { postAction('unarchiveMission', { missionId: mission.id }); });
            moreRow.appendChild(unarchive);
        }
        if (['pending', 'running', 'interrupted', 'blocked'].indexOf(mission.status) >= 0) {
            const steer = el('button', '', 'Steer');
            steer.addEventListener('click', function () { postAction('steerMission', { missionId: mission.id }); });
            moreRow.appendChild(steer);
        }
        const remove = el('button', 'nl-danger', 'Delete mission');
        remove.addEventListener('click', function () { postAction('deleteMission', { missionId: mission.id }); });
        moreRow.appendChild(remove);
        more.appendChild(moreRow);
        actions.appendChild(more);
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
        missionDetailEl.appendChild(el('h3', 'nl-detail-subtitle', 'Model assignments (ModelRouter snapshot)'));
        missionDetailEl.appendChild(renderModelAssignments(detail));
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

        const researchSection = el('div', 'nl-engine-section');
        researchSection.appendChild(el('h3', '', 'Research / URL fetch'));
        const researchRow = el('div', 'nl-field');
        researchRow.appendChild(el('span', 'nl-muted', 'Auto-review profile'));
        const profileSelect = el('select');
        [{ value: 'manual', label: 'Manual (fetch reports needs_approval)' },
         { value: 'trusted-auto-review', label: 'Trusted auto review (granted web-fetch can run)' }]
            .forEach(function (option) {
                const node = el('option', '', option.label);
                node.value = option.value;
                profileSelect.appendChild(node);
            });
        profileSelect.value = current.researchProfile || 'manual';
        profileSelect.addEventListener('change', function () {
            postAction('setResearchProfile', { profile: profileSelect.value });
        });
        researchRow.appendChild(profileSelect);
        researchSection.appendChild(researchRow);
        const researchInfo = (settings.research || {});
        researchSection.appendChild(el('div', 'nl-muted',
            'Engine status: ' + (researchInfo.status || 'unknown') +
            ' · URL fetch: ' + (researchInfo.url_fetch_available ? 'available' : 'unavailable') +
            ' · web search: ' + (researchInfo.network_configured ? 'configured' : 'not configured')));
        researchSection.appendChild(el('div', 'nl-muted',
            'NETWORK grant: ' + (settings.permissions.policy.network ? 'granted' : 'denied') +
            ' · web-fetch follows the same Project Access grant'));
        researchSection.appendChild(el('div', 'nl-muted',
            'The selected Research profile controls automatic approval. Fetched page content is always treated as untrusted.'));
        engineContent.appendChild(researchSection);

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
        rendering = true;
        try {
            renderHeader(state);
            renderSessions(state);
            renderQueue(state);
            renderBanner(state);
            renderModelBar(state);
            renderAccess(state);
            renderContext(state);
            renderResearch(state);
            renderMissionList(state);
            renderMissionDetail(state);
            renderSettings(state);
            renderStorage(state);
            renderEngine(state);
        } finally {
            rendering = false;
        }
    }

    const slashCommands = [
        { name: '/mission', insert: '/mission ', label: 'Start a mission', detail: 'Plan, implement, verify and review a concrete change.' },
        { name: '/steer', insert: '/steer ', label: 'Steer the running turn', detail: 'Redirect the current Chat or mission at the next checkpoint.' },
        { name: '/fetch', insert: '/fetch ', label: 'Fetch a URL', detail: 'Paste a URL after the command; Chat fetches it as untrusted context.' },
        { name: '/agent', insert: '/agent ', label: 'Send a task to one agent', detail: 'Pick a specialist; one task runs at a time.' },
        { name: '/plan', insert: '/plan ', label: 'Plan without editing', detail: 'Analyse docs and files, then return a concrete plan; no mission starts.' },
        { name: '/team', insert: '/team', label: 'Build the specialist team', detail: 'Assign the best available models/providers to project roles.' },
        { name: '/apply', insert: '/apply', label: 'Apply the generated plan', detail: 'Create a Goal and milestones; nothing is executed.' },
        { name: '/runplan', insert: '/runplan', label: 'Run the applied plan', detail: 'Start Supervisor missions explicitly after /apply.' },
        { name: '/mcp', insert: '/mcp', label: 'List MCP servers', detail: 'Show configured MCP servers; ask the model to discover/invoke their allowed tools.' },
        { name: '/checkpoint', insert: '/checkpoint', label: 'Checkpoint files', detail: 'Save filesystem state without touching chat history.' },
        { name: '/checkpoints', insert: '/checkpoints', label: 'List checkpoints', detail: 'Show recent filesystem checkpoints.' },
        { name: '/restore', insert: '/restore ', label: 'Restore a checkpoint', detail: 'Restore files from a checkpoint id; chat history is not rewound.' },
        { name: '/help', insert: '/help', label: 'Show commands', detail: 'List the available Chat commands.' }
    ];
    let slashMatches = [];
    let slashContext = null;

    function hideSlashMenu() {
        slashMatches = [];
        slashContext = null;
        slashMode = 'command';
        fileMentionSearchQuery = null;
        if (fileMentionSearchTimer && typeof clearTimeout === 'function') {
            clearTimeout(fileMentionSearchTimer);
            fileMentionSearchTimer = null;
        }
        if (slashMenuEl) {
            slashMenuEl.classList.add('hidden');
            clear(slashMenuEl);
        }
    }

    function applySlashCommand(command) {
        if (!command || !inputEl) { return; }
        if (command.name === '/help') {
            hideSlashMenu();
            inputEl.value = '';
            postChatLocal('system', slashCommands.map(function (item) {
                return item.name + ' — ' + item.label + ': ' + item.detail;
            }).join('\n'));
            return;
        }
        const value = inputEl.value;
        const context = slashContext;
        const before = context ? value.slice(0, context.start) : '';
        const after = context ? value.slice(context.end) : '';
        inputEl.value = before + command.insert + after;
        const caret = before.length + command.insert.length;
        hideSlashMenu();
        if (command.kind === 'file') {
            postAction('mentionWorkspaceFile', { path: command.path });
        }
        if (command.name === '/mission') {
            modeEl.value = 'mission';
            setMode('mission');
        }
        inputEl.focus();
        inputEl.setSelectionRange(caret, caret);
    }

    function renderSlashMatches() {
        if (!slashMenuEl) { return; }
        clear(slashMenuEl);
        if (!slashMatches.length) {
            if (slashMode === 'file') {
                slashMenuEl.appendChild(el('div', 'nl-slash-row',
                    fileMentionSearchQuery === null ? 'Searching project files…' : 'No matching files'));
                slashMenuEl.classList.remove('hidden');
            } else {
                hideSlashMenu();
            }
            return;
        }
        slashMatches.forEach(function (command, index) {
            const row = el('button', 'nl-slash-row', '');
            row.type = 'button';
            row.setAttribute('role', 'option');
            row.appendChild(el('strong', '', command.name));
            row.appendChild(el('span', 'nl-slash-label', command.label));
            row.appendChild(el('span', 'nl-muted', command.detail));
            row.addEventListener('mousedown', function (event) {
                event.preventDefault();
                applySlashCommand(command);
            });
            if (index === 0) { row.dataset.first = 'true'; }
            slashMenuEl.appendChild(row);
        });
        slashMenuEl.classList.remove('hidden');
    }

    function currentFileMention() {
        if (!inputEl) { return null; }
        const value = inputEl.value;
        const caret = inputEl.selectionStart === null ? value.length : inputEl.selectionStart;
        const match = /(^|\s)@([^\s@]*)$/.exec(value.slice(0, caret));
        return match ? { query: match[2].toLowerCase(), caret: caret,
            start: caret - match[2].length - 1 } : null;
    }

    function updateSlashMenu() {
        if (!slashMenuEl || !inputEl) { return; }
        const value = inputEl.value;
        const caret = inputEl.selectionStart === null
            ? value.length : inputEl.selectionStart;
        const before = value.slice(0, caret);
        const mention = /(^|\s)@([^\s@]*)$/.exec(before);
        if (mention && mode === 'chat') {
            const query = mention[2].toLowerCase();
            slashMode = 'file';
            slashContext = { start: caret - mention[2].length - 1, end: caret };
            if (fileMentionSearchQuery !== query) {
                fileMentionSearchQuery = query;
                fileMentionResults = [];
                if (fileMentionSearchTimer && typeof clearTimeout === 'function') {
                    clearTimeout(fileMentionSearchTimer);
                }
                fileMentionSearchTimer = setTimeout(function () {
                    fileMentionSearchTimer = null;
                    const current = currentFileMention();
                    if (current && current.query === query) {
                        postAction('searchWorkspaceFiles', { query: query });
                    }
                }, 120);
            }
            slashMatches = fileMentionResults.filter(function (file) {
                return !query || file.path.toLowerCase().includes(query);
            }).map(function (file) {
                return {
                    kind: 'file', path: file.path, name: '@' + file.path,
                    insert: '@' + file.path + ' ', label: file.label || file.path,
                    detail: file.detail || 'Attach project file as context'
                };
            });
            renderSlashMatches();
            return;
        }
        const match = /(^|\s)\/([^\s/]*)$/.exec(before);
        if (!match) {
            hideSlashMenu();
            return;
        }
        slashMode = 'command';
        const query = match[2].toLowerCase();
        slashContext = { start: caret - match[2].length - 1, end: caret };
        slashMatches = slashCommands.filter(function (item) {
            return !query || item.name.slice(1).indexOf(query) === 0;
        });
        if (!query || 'agent'.indexOf(query) === 0) {
            const agents = (state && state.settings && state.settings.agents &&
                state.settings.agents.custom_agents) || [];
            agents.slice(0, 12).forEach(function (agent) {
                if (!agent || !agent.id) { return; }
                slashMatches.push({
                    name: '/agent ' + agent.id,
                    insert: '/agent ' + agent.id + ' ',
                    label: agent.name || agent.id,
                    detail: (agent.role || 'specialist') + ' · ' + (agent.model || 'default model')
                });
            });
        }
        renderSlashMatches();
    }

    function handleSlashKey(event) {
        if (!slashMenuEl || slashMenuEl.classList.contains('hidden')) { return false; }
        if (!slashMatches.length) { return false; }
        if (event.key === 'Tab' || event.key === 'Enter') {
            event.preventDefault();
            applySlashCommand(slashMatches[0]);
            return true;
        }
        if (event.key === 'Escape') {
            event.preventDefault();
            hideSlashMenu();
            return true;
        }
        return false;
    }

    function postChatLocal(role, text) {
        append(role, text);
    }

    function submit() {
        if (state && state.busyPhase === 'attaching') {
            showNotice('Wait for the selected file to finish attaching before sending.');
            return;
        }
        let text = inputEl.value.trim();
        if (!text) {
            return;
        }
        if (text.indexOf('/fetch ') === 0) {
            text = text.slice('/fetch '.length).trim();
        }
        if (mode === 'mission') {
            if (state && (state.busyChat || state.busyMission)) {
                hintEl.textContent = 'A turn is still running; wait before starting another mission.';
                return;
            }
            postAction('startMission', {
                goal: text,
                developerModel: devModelEl.value,
                reviewerModel: reviewerModelEl.value
            });
            append('user', text);
        } else if (text.indexOf('/mission ') === 0) {
            if (state && (state.busyChat || state.busyMission)) {
                hintEl.textContent = 'A turn is still running; wait before starting another mission.';
                return;
            }
            postAction('startMission', {
                goal: text.slice('/mission '.length).trim(),
                developerModel: devModelEl.value,
                reviewerModel: reviewerModelEl.value
            });
            append('user', text);
        } else {
            append('user', text, {
                attachments: (state && state.attachments || []).map(function (attachment) {
                    return {
                        name: attachment.name,
                        kind: attachment.kind,
                        size_bytes: attachment.size_bytes,
                        has_text: attachment.has_text
                    };
                })
            });
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
        if (handleSlashKey(event)) {
            return;
        }
        if (event.key === 'Enter' && !event.shiftKey) {
            event.preventDefault();
            submit();
        }
    });
    inputEl.addEventListener('paste', function (event) {
        const clipboard = event.clipboardData;
        const items = clipboard && clipboard.items;
        if (!items) { return; }
        let imageFile = null;
        for (let index = 0; index < items.length; index += 1) {
            const item = items[index];
            if (item.kind === 'file' && /^image\//i.test(item.type || '')) {
                imageFile = item.getAsFile();
                if (imageFile) { break; }
            }
        }
        if (!imageFile) { return; }
        if (mode !== 'chat') {
            event.preventDefault();
            showNotice('Switch to Chat mode to attach a pasted image.');
            return;
        }
        const maxImageBytes = 25 * 1024 * 1024;
        if (imageFile.size > maxImageBytes) {
            event.preventDefault();
            showNotice('Pasted image exceeds the 25 MiB limit.');
            return;
        }
        if (!(clipboard.getData('text/plain') || '').trim()) {
            event.preventDefault();
        }
        const reader = new FileReader();
        reader.addEventListener('load', function () {
            const dataUrl = String(reader.result || '');
            const separator = dataUrl.indexOf(',');
            if (separator < 0) {
                showNotice('Could not read the pasted image.');
                return;
            }
            postAction('pasteImage', { imageBase64: dataUrl.slice(separator + 1) });
        });
        reader.addEventListener('error', function () {
            showNotice('Could not read the pasted image.');
        });
        reader.readAsDataURL(imageFile);
    });
    inputEl.addEventListener('input', updateSlashMenu);
    inputEl.addEventListener('blur', function () {
        window.setTimeout(hideSlashMenu, 120);
    });

    modeEl.addEventListener('change', function () { setMode(modeEl.value); });

    function stateModelOptions() {
        return (state && state.modelOptions) || [];
    }

    function postModelRoute(route) {
        postAction('setChatModel', { value: route || '' });
    }

    providerSelectEl.addEventListener('change', function () {
        postAction('setProviderFilter', { provider: providerSelectEl.value });
    });

    chatModelEl.addEventListener('change', function () {
        if (!state) { return; }
        if (chatModelEl.value) {
            autoModelEl.checked = false;
            postModelRoute(chatModelEl.value);
        } else {
            autoModelEl.checked = true;
            postModelRoute('');
        }
    });

    autoModelEl.addEventListener('change', function () {
        if (autoModelEl.checked) {
            postModelRoute('');
            return;
        }
        const candidate = stateModelOptions().filter(function (option) { return option.value; })[0];
        if (candidate) {
            postModelRoute(candidate.value);
        } else {
            postModelRoute('');
        }
    });

    autoCodingEl.addEventListener('change', function () {
        postAction('setAutoCoding', { value: autoCodingEl.checked });
    });

    function missionModelsChanged() {
        postAction('setMissionModels', {
            developerModel: devModelEl.value,
            reviewerModel: reviewerModelEl.value
        });
    }
    devModelEl.addEventListener('change', missionModelsChanged);
    reviewerModelEl.addEventListener('change', missionModelsChanged);

    attachFilesEl.addEventListener('click', function () { postAction('attachFiles', {}); });
    attachCurrentEl.addEventListener('click', function () { postAction('attachEditor', { kind: 'file' }); });
    attachSelectionEl.addEventListener('click', function () { postAction('attachEditor', { kind: 'selection' }); });
    if (dictateEl) {
        dictateEl.addEventListener('click', function () { postAction('toggleDictation', {}); });
    }
    researchUse.addEventListener('click', function () { postAction('useResearch', {}); });
    researchDismiss.addEventListener('click', function () { postAction('dismissResearch', {}); });

    function hasFileDrag(event) {
        const types = event.dataTransfer && event.dataTransfer.types;
        return Boolean(types && (Array.prototype.indexOf.call(types, 'Files') >= 0 ||
            Array.prototype.indexOf.call(types, 'text/uri-list') >= 0));
    }
    document.addEventListener('dragenter', function (event) {
        if (!hasFileDrag(event) || mode === 'mission') { return; }
        event.preventDefault();
        dragDepth += 1;
        dropOverlay.classList.remove('hidden');
    });
    document.addEventListener('dragover', function (event) {
        if (!hasFileDrag(event) || mode === 'mission') { return; }
        event.preventDefault();
    });
    document.addEventListener('dragleave', function (event) {
        if (!hasFileDrag(event) || mode === 'mission') { return; }
        dragDepth = Math.max(0, dragDepth - 1);
        if (!dragDepth) { dropOverlay.classList.add('hidden'); }
    });
    document.addEventListener('drop', function (event) {
        if (!hasFileDrag(event) || mode === 'mission') { return; }
        event.preventDefault();
        dragDepth = 0;
        dropOverlay.classList.add('hidden');
        let text = '';
        try {
            text = event.dataTransfer.getData('text/uri-list') || event.dataTransfer.getData('text/plain') || '';
        } catch (error) {
            text = '';
        }
        const uris = text.split(/\r?\n/).map(function (line) {
            return line.trim();
        }).filter(function (line) {
            return line && line.charAt(0) !== '#';
        });
        if (uris.length) {
            postAction('dropUris', { uris: uris });
        }
    });

    sessionSelectEl.addEventListener('change', function () {
        postAction('selectChatSession', { sessionId: sessionSelectEl.value });
    });
    $('session-history').addEventListener('click', function () { postAction('showChatHistory', {}); });
    $('session-new').addEventListener('click', function () { postAction('newChatSession', {}); });
    $('session-rename').addEventListener('click', function () { postAction('renameChatSession', {}); });
    $('session-archive').addEventListener('click', function () { postAction('archiveChatSession', {}); });
    $('session-delete').addEventListener('click', function () { postAction('deleteChatSession', {}); });
    $('session-search').addEventListener('click', function () { postAction('searchChat', {}); });
    $('session-archived-toggle').addEventListener('change', function () {
        postAction('toggleArchivedSessions', {});
    });
    $('mission-apply-filter').addEventListener('click', function () {
        postAction('setMissionFilter', {
            query: $('mission-query').value,
            status: $('mission-status-filter').value,
            includeArchived: $('mission-archived-toggle').checked
        });
    });
    $('provider-edit').addEventListener('change', function () {
        const provider = ((state && state.settings && state.settings.models.providers) || []).filter(function (item) {
            return item.provider_id === $('provider-edit').value;
        })[0];
        if (provider) {
            $('provider-enabled').checked = Boolean(provider.enabled);
            $('provider-url').value = provider.base_url || '';
            $('provider-id').value = provider.provider_id || '';
            $('provider-kind').value = provider.kind || 'openai_compatible';
            $('provider-label').value = provider.label || '';
            $('provider-api-key-env').value = provider.api_key_env || '';
        }
    });
    $('role-edit').addEventListener('change', function () {
        const roles = (state && state.settings && state.settings.models.roles) || {};
        const role = roles[$('role-edit').value] || {};
        $('role-model-edit').value = role.model || '';
    });
    $('provider-new').addEventListener('click', function () {
        postAction('addProviderDialog', {});
    });
    $('speech-refresh').addEventListener('click', function () { postAction('refreshSpeech', {}); });
    speechEngineEl.addEventListener('change', function () {
        renderSpeech(state, speechEngineEl.value);
    });
    speechModelEl.addEventListener('change', function () {
        const option = Array.prototype.slice.call(speechModelEl.children).filter(function (item) {
            return item.value === speechModelEl.value;
        })[0];
        $('speech-select').textContent =
            option && option.dataset.downloadModel ? 'Download model' : 'Use model';
        const engines = ((state && state.speech && state.speech.catalog) || {}).engines || [];
        const engine = engines.filter(function (item) {
            return item.engine === speechEngineEl.value;
        })[0];
        $('speech-select').disabled = !speechModelEl.value || !(engine && engine.installed);
    });
    $('speech-select').addEventListener('click', function () {
        const option = Array.prototype.slice.call(speechModelEl.children).filter(function (item) {
            return item.value === speechModelEl.value;
        })[0];
        postAction(option && option.dataset.downloadModel ? 'downloadSpeechModel' : 'selectSpeechModel',
            { modelId: speechModelEl.value, engine: speechEngineEl.value });
    });
    $('speech-external').addEventListener('click', function () {
        postAction('setSpeechExternalHome', { path: $('speech-home').value });
    });
    $('speech-browse').addEventListener('click', function () {
        postAction('browseSpeechFolder', {});
    });
    $('specialist-tools-all').addEventListener('click', function () {
        const values = Array.prototype.slice.call(
            specialistToolsEl.querySelectorAll('input[type="checkbox"]'))
            .map(function (input) { return input.value; });
        setCheckedValues(specialistToolsEl, values);
    });
    accessProfileEl.addEventListener('change', function () {
        postAction('setAccessMode', { profile: accessProfileEl.value });
    });
    $('provider-save').addEventListener('click', function () {
        postAction('saveProviderSettings', {
            providerId: $('provider-id').value || $('provider-edit').value,
            enabled: $('provider-enabled').checked,
            baseUrl: $('provider-url').value,
            kind: $('provider-kind').value,
            label: $('provider-label').value,
            apiKeyEnv: $('provider-api-key-env').value
        });
    });
    $('role-save').addEventListener('click', function () {
        postAction('saveRoleSettings', {
            role: $('role-edit').value,
            model: $('role-model-edit').value
        });
    });
    specialistSelectEl.addEventListener('change', function () {
        if (!state) { return; }
        fillSpecialist(selectedSpecialist(state));
    });
    $('specialist-new').addEventListener('click', function () {
        specialistSelectEl.value = '';
        fillSpecialist(null);
        specialistNameEl.focus();
    });
    specialistProviderEl.addEventListener('change', function () {
        populateModelSelect(specialistModelEl, modelChoices(specialistProviderEl.value), '');
    });
    $('specialist-generate').addEventListener('click', function () {
        postAction('generateSpecialists', {});
    });
    $('specialist-save').addEventListener('click', function () {
        postAction('saveSpecialistAgent', {
            id: specialistSelectEl.value || undefined,
            name: specialistNameEl.value,
            provider: specialistProviderEl.value,
            model: specialistModelEl.value,
            role: specialistRoleEl.value,
            instructions: specialistInstructionsEl.value,
            tools: checkedValues(specialistToolsEl),
            enabled: specialistEnabledEl.checked
        });
    });
    $('specialist-duplicate').addEventListener('click', function () {
        if (specialistSelectEl.value) {
            postAction('duplicateSpecialistAgent', { agentId: specialistSelectEl.value });
        }
    });
    $('specialist-delete').addEventListener('click', function () {
        if (specialistSelectEl.value) {
            postAction('deleteSpecialistAgent', { agentId: specialistSelectEl.value });
        }
    });
    $('generation-save').addEventListener('click', function () {
        function numberOrNull(id) {
            const value = $(id).value;
            return value === '' ? null : Number(value);
        }
        postAction('saveGenerationParameters', {
            scope: $('generation-scope').value,
            modelName: $('generation-model').value,
            role: $('generation-role').value,
            temperature: numberOrNull('generation-temperature'),
            top_p: numberOrNull('generation-top-p'),
            top_k: numberOrNull('generation-top-k'),
            min_p: numberOrNull('generation-min-p'),
            repeat_penalty: numberOrNull('generation-repeat'),
            seed: numberOrNull('generation-seed'),
            max_tokens: numberOrNull('generation-max'),
            num_ctx: numberOrNull('generation-context')
        });
    });
    $('permission-grant').addEventListener('click', function () {
        postAction('savePermission', { scope: $('permission-scope').value, granted: true });
    });
    $('permission-revoke').addEventListener('click', function () {
        postAction('savePermission', { scope: $('permission-scope').value, granted: false });
    });
    $('cloud-save').addEventListener('click', function () {
        postAction('saveCloudPolicy', { enabled: $('cloud-policy').checked });
    });
    $('autonomy-save').addEventListener('click', function () {
        postAction('saveAutonomy', {
            mode: $('autonomy-mode').value,
            maxMissions: $('autonomy-missions').value ? Number($('autonomy-missions').value) : undefined,
            attempts: $('autonomy-attempts').value ? Number($('autonomy-attempts').value) : undefined
        });
    });
    $('mcp-save').addEventListener('click', function () {
        let config = {};
        try {
            config = JSON.parse($('mcp-json').value || '{}');
        } catch (error) {
            showNotice('MCP JSON is invalid: ' + error.message);
            return;
        }
        postAction('saveMcpConfig', { config: config });
    });
    $('probe-run').addEventListener('click', function () {
        postAction('probeModel', { model: $('probe-model').value });
    });
    $('storage-scan').addEventListener('click', function () { postAction('scanStorage', {}); });
    $('jobs-refresh').addEventListener('click', function () { postAction('refreshJobs', {}); });
    $('storage-vacuum').addEventListener('click', function () { postAction('vacuumStorage', {}); });
    $('storage-cleanup-orphans').addEventListener('click', function () {
        postAction('cleanupChatSessions', { scope: 'orphaned' });
    });
    $('storage-cleanup-archived').addEventListener('click', function () {
        postAction('cleanupChatSessions', { scope: 'archived' });
    });
    $('storage-purge').addEventListener('click', function () {
        const ids = Object.keys(storageSelected).filter(function (id) { return storageSelected[id]; });
        postAction('purgeStorage', { ids: ids });
    });
    $('chat-controls-toggle').addEventListener('click', function () {
        chatControlsVisible = !chatControlsVisible;
        $('model-bar').classList.toggle('hidden', !chatControlsVisible || mode === 'mission');
        $('chat-controls-toggle').textContent = (chatControlsVisible ? '▾' : '▸') + ' model controls';
    });
    $('context-toggle').addEventListener('click', function () {
        contextVisible = !contextVisible;
        $('context-strip').classList.toggle('hidden', !contextVisible || mode === 'mission');
        $('context-toggle').textContent = (contextVisible ? '▾' : '▸') + ' attachments';
    });
    $('mission-fields-toggle').addEventListener('click', function () {
        missionFieldsVisible = !missionFieldsVisible;
        $('mission-fields').classList.toggle('hidden', mode !== 'mission' || !missionFieldsVisible);
        $('mission-note').classList.toggle('hidden', mode !== 'mission' || !missionFieldsVisible);
        $('mission-fields-toggle').textContent =
            (missionFieldsVisible ? '▾' : '▸') + ' mission model selection';
    });
    $('mission-list-toggle').addEventListener('click', function () {
        missionListVisible = !missionListVisible;
        $('mission-list').classList.toggle('hidden', !missionListVisible);
        $('mission-list-toggle').textContent = (missionListVisible ? '▾' : '▸') + ' mission list';
    });
    $('mission-select-visible').addEventListener('change', function () {
        const missions = (state && state.missions) || [];
        missions.forEach(function (mission) {
            if ($('mission-select-visible').checked) {
                selectedMissionIds[String(mission.id)] = true;
            } else {
                delete selectedMissionIds[String(mission.id)];
            }
        });
        renderMissionList(state);
    });
    $('mission-selection-clear').addEventListener('click', function () {
        selectedMissionIds = Object.create(null);
        renderMissionList(state);
    });
    $('mission-stop-selected').addEventListener('click', function () {
        postAction('stopSelectedMissions', { missionIds: selectedMissionIdsList() });
    });
    $('mission-archive-selected').addEventListener('click', function () {
        postAction('archiveSelectedMissions', { missionIds: selectedMissionIdsList() });
    });
    $('mission-delete-selected').addEventListener('click', function () {
        postAction('deleteSelectedMissions', { missionIds: selectedMissionIdsList() });
    });

    tabButtons.forEach(function (button) {
        button.addEventListener('click', function () { switchTab(button.dataset.tab); });
    });

    execToggle.addEventListener('click', function () { postAction('toggleExecution', {}); });
    $('refresh-missions').addEventListener('click', function () { postAction('refreshMissions', {}); });
    $('refresh-engine').addEventListener('click', function () { postAction('refreshEngine', {}); });
    $('refresh-models').addEventListener('click', function () { postAction('refreshEngine', {}); });
    $('chat-refresh-models').addEventListener('click', function () { postAction('refreshModels', {}); });
    bannerStop.addEventListener('click', function () {
        if (state && state.activeMissionId) { postAction('cancelMission', { missionId: state.activeMissionId }); }
    });
    chatStop.addEventListener('click', function () { postAction('stopChat', {}); });
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
        } else if (message.type === 'history') {
            const payload = message.payload || {};
            renderHistory(payload.messages || []);
        } else if (message.type === 'chat') {
            append(message.role || 'system', message.text);
        } else if (message.type === 'navigate' && message.tab) {
            switchTab(message.tab);
        } else if (message.type === 'status') {
            setStatus(message.label || '', message.state || '');
        } else if (message.type === 'focus') {
            inputEl.focus();
        } else if (message.type === 'setComposer') {
            inputEl.value = String(message.text || '');
            inputEl.focus();
            updateSlashMenu();
        } else if (message.type === 'fileMentions') {
            const current = currentFileMention();
            const query = String(message.query || '').toLowerCase();
            if (!current || current.query !== query || slashMode !== 'file') { return; }
            fileMentionResults = Array.isArray(message.files) ? message.files : [];
            slashMatches = fileMentionResults.map(function (file) {
                return {
                    kind: 'file', path: file.path, name: '@' + file.path,
                    insert: '@' + file.path + ' ', label: file.label || file.path,
                    detail: file.detail || 'Attach project file as context'
                };
            });
            renderSlashMatches();
        } else if (message.type === 'clearMissionSelection') {
            selectedMissionIds = Object.create(null);
            if (state) { renderMissionList(state); }
        }
    });

    const saved = vscode.getState();
    if (saved && saved.tab && panels[saved.tab]) {
        switchTab(saved.tab);
    }
    if (saved && saved.mode) {
        setMode(saved.mode);
    }

    setStatus('Connecting to NL Coder…', 'connecting');
    setTimeout(function () { inputEl.focus(); }, 50);
    vscode.postMessage({ type: 'ready' });
})();
