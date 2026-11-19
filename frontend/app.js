const fileInput = document.getElementById('video-file');
const dropzone = document.getElementById('dropzone');
const rightsCheckbox = document.getElementById('rights-confirmed');
const uploadButton = document.getElementById('upload-button');
const selectedFilePanel = document.getElementById('selected-file');
const notice = document.getElementById('notice');
const progressWrap = document.getElementById('progress-wrap');
let selectedFile = null;
let uploadInProgress = false;
let activeAnalysisTimer = null;
let activeRenderTimer = null;
let activeRenderAnalysisId = null;
let youtubeConnected = false;
let latestRenderedClips = [];

const MAX_UPLOAD_BYTES = 2048 * 1024 * 1024;
const ALLOWED_EXTENSIONS = ['.mp4', '.mov', '.m4v', '.mkv', '.webm', '.avi'];

function formatBytes(bytes) {
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function showNotice(message, type = '') {
    notice.textContent = message;
    notice.className = `notice ${type}`;
}

function refreshUploadButton() {
    uploadButton.disabled = !selectedFile || !rightsCheckbox.checked || uploadInProgress;
}

function setSelectedFile(file) {
    if (!file) return;
    const extension = `.${file.name.split('.').pop().toLowerCase()}`;
    if (!ALLOWED_EXTENSIONS.includes(extension)) {
        showNotice('Unsupported file type. Choose MP4, MOV, M4V, MKV, WEBM or AVI.', 'error');
        return;
    }
    if (file.size > MAX_UPLOAD_BYTES) {
        showNotice('This file exceeds the 2048 MB upload limit.', 'error');
        return;
    }
    if (file.size === 0) {
        showNotice('The selected file is empty.', 'error');
        return;
    }

    selectedFile = file;
    document.getElementById('selected-name').textContent = file.name;
    document.getElementById('selected-size').textContent = formatBytes(file.size);
    selectedFilePanel.classList.remove('hidden');
    document.getElementById('file-prompt').textContent = 'Video selected';
    notice.classList.add('hidden');
    refreshUploadButton();
}

fileInput.addEventListener('change', () => setSelectedFile(fileInput.files[0]));
rightsCheckbox.addEventListener('change', refreshUploadButton);

document.getElementById('remove-file').addEventListener('click', () => {
    selectedFile = null;
    fileInput.value = '';
    selectedFilePanel.classList.add('hidden');
    document.getElementById('file-prompt').textContent = 'Drop your video here';
    refreshUploadButton();
});

for (const eventName of ['dragenter', 'dragover']) {
    dropzone.addEventListener(eventName, event => {
        event.preventDefault();
        dropzone.classList.add('dragover');
    });
}
for (const eventName of ['dragleave', 'drop']) {
    dropzone.addEventListener(eventName, event => {
        event.preventDefault();
        dropzone.classList.remove('dragover');
    });
}
dropzone.addEventListener('drop', event => setSelectedFile(event.dataTransfer.files[0]));
uploadButton.addEventListener('click', uploadVideo);
document.getElementById('refresh-button').addEventListener('click', loadSources);

function uploadVideo() {
    if (!selectedFile || !rightsCheckbox.checked || uploadInProgress) return;

    const formData = new FormData();
    formData.append('file', selectedFile);
    formData.append('rights_confirmed', 'true');

    uploadInProgress = true;
    refreshUploadButton();
    notice.classList.add('hidden');
    progressWrap.classList.remove('hidden');
    document.getElementById('progress-text').textContent = 'Uploading source video…';
    document.getElementById('progress-percent').textContent = '0%';
    document.getElementById('progress-fill').style.width = '0%';

    const request = new XMLHttpRequest();
    request.open('POST', '/api/v1/sources/upload');
    request.upload.addEventListener('progress', event => {
        if (!event.lengthComputable) return;
        const percent = Math.min(100, Math.round((event.loaded / event.total) * 100));
        document.getElementById('progress-percent').textContent = `${percent}%`;
        document.getElementById('progress-fill').style.width = `${percent}%`;
    });
    request.addEventListener('load', () => {
        uploadInProgress = false;
        refreshUploadButton();
        let response;
        try { response = JSON.parse(request.responseText); }
        catch { response = { detail: 'The server returned an unreadable response.' }; }

        if (request.status >= 200 && request.status < 300) {
            document.getElementById('progress-text').textContent = 'Upload complete';
            const validationMessage = response.validation_status === 'verified'
                ? 'The video stream was verified with FFprobe.'
                : 'Only the file signature was checked. FFprobe will refresh metadata during analysis.';
            showNotice(`Saved ${response.original_filename}. ${validationMessage} Source ID: ${response.source_id}`, 'success');
            selectedFile = null;
            fileInput.value = '';
            selectedFilePanel.classList.add('hidden');
            document.getElementById('file-prompt').textContent = 'Drop your video here';
            loadSources();
        } else {
            progressWrap.classList.add('hidden');
            showNotice(response.detail || 'Upload failed. Check the server terminal for details.', 'error');
        }
    });
    request.addEventListener('error', () => {
        uploadInProgress = false;
        refreshUploadButton();
        progressWrap.classList.add('hidden');
        showNotice('Could not reach the local server. Make sure the backend is running.', 'error');
    });
    request.send(formData);
}

function createButton(label, className, handler) {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = className;
    button.textContent = label;
    button.addEventListener('click', handler);
    return button;
}

function loadSources() {
    const list = document.getElementById('source-list');
    fetch('/api/v1/sources')
        .then(response => {
            if (!response.ok) throw new Error('Could not load sources');
            return response.json();
        })
        .then(data => {
            if (!data.items.length) {
                list.innerHTML = '<div class="empty-state">No videos yet. Upload your first authorized source above.</div>';
                return;
            }
            list.replaceChildren();
            for (const item of data.items) {
                const row = document.createElement('div');
                row.className = 'source-row';
                const main = document.createElement('div');
                main.className = 'source-main';
                const name = document.createElement('strong');
                name.textContent = item.original_filename;
                const meta = document.createElement('span');
                meta.className = 'source-meta';
                const size = formatBytes(item.size_bytes);
                const duration = item.duration_seconds ? ` · ${Number(item.duration_seconds).toFixed(1)} sec` : '';
                meta.textContent = `${size}${duration} · ${new Date(item.created_at).toLocaleString()} · ${item.validation_status}`;
                main.append(name, meta);

                const actions = document.createElement('div');
                actions.className = 'source-actions';
                const status = document.createElement('span');
                status.className = 'status-pill';
                status.textContent = item.latest_analysis_status || item.status;
                actions.append(status);
                const actionLabel = item.latest_analysis_status === 'COMPLETED' ? 'View results' :
                    ['QUEUED', 'RUNNING'].includes(item.latest_analysis_status) ? 'View progress' : 'Analyze video';
                actions.append(createButton(actionLabel, 'small-button', () => {
                    if (['COMPLETED', 'QUEUED', 'RUNNING'].includes(item.latest_analysis_status)) {
                        showAnalysisPanel();
                        pollAnalysis(item.latest_analysis_id);
                    } else {
                        startAnalysis(item.id);
                    }
                }));
                row.append(main, actions);
                list.append(row);
            }
        })
        .catch(() => {
            list.innerHTML = '<div class="empty-state">Unable to load the library. Is the backend running?</div>';
        });
}

function showAnalysisPanel() {
    document.getElementById('analysis-panel').classList.remove('hidden');
    document.getElementById('analysis-panel').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function createField(labelText, element) {
    const wrapper = document.createElement('label');
    wrapper.className = 'youtube-field';
    const label = document.createElement('span');
    label.textContent = labelText;
    wrapper.append(label, element);
    return wrapper;
}

function createConsent(labelText, className = '') {
    const wrapper = document.createElement('label');
    wrapper.className = `youtube-consent ${className}`.trim();
    const input = document.createElement('input');
    input.type = 'checkbox';
    const text = document.createElement('span');
    text.textContent = labelText;
    wrapper.append(input, text);
    return { wrapper, input };
}

function renderYouTubeUploadControls(clip) {
    const panel = document.createElement('section');
    panel.className = 'youtube-upload-controls';
    const heading = document.createElement('h4');
    heading.textContent = 'Publish this clip to YouTube';
    panel.append(heading);

    const state = document.createElement('p');
    state.className = 'youtube-upload-state';
    state.textContent = youtubeConnected
        ? 'Choose the metadata and visibility for this specific upload.'
        : 'Connect YouTube in the publishing panel above before uploading.';
    panel.append(state);

    if (!youtubeConnected) return panel;

    const titleInput = document.createElement('input');
    titleInput.type = 'text';
    titleInput.maxLength = 100;
    titleInput.value = String(clip.title || 'AutoClips highlight').slice(0, 100);
    titleInput.required = true;
    const descriptionInput = document.createElement('textarea');
    descriptionInput.rows = 3;
    descriptionInput.maxLength = 5000;
    descriptionInput.placeholder = 'Optional description (up to 5,000 characters)';
    const tagsInput = document.createElement('input');
    tagsInput.type = 'text';
    tagsInput.maxLength = 500;
    tagsInput.placeholder = 'Optional comma-separated tags';
    const privacySelect = document.createElement('select');
    for (const [value, label] of [
        ['private', 'Private — only you can view'],
        ['unlisted', 'Unlisted — anyone with the link'],
        ['public', 'Public — visible to everyone'],
    ]) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        privacySelect.append(option);
    }
    privacySelect.value = 'private';

    const madeForKidsSelect = document.createElement('select');
    const madeForKidsPlaceholder = document.createElement('option');
    madeForKidsPlaceholder.value = '';
    madeForKidsPlaceholder.textContent = 'Choose whether this video is made for kids';
    madeForKidsSelect.append(madeForKidsPlaceholder);
    for (const [value, label] of [
        ['false', 'No — this video is not made for kids'],
        ['true', 'Yes — this video is made for kids'],
    ]) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        madeForKidsSelect.append(option);
    }

    const syntheticSelect = document.createElement('select');
    for (const [value, label] of [
        ['', 'Not specified — decide in YouTube Studio'],
        ['true', 'Yes — disclose realistic altered/synthetic content'],
        ['false', 'No — this disclosure does not apply'],
    ]) {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = label;
        syntheticSelect.append(option);
    }

    panel.append(
        createField('Title (editable; maximum 100 characters)', titleInput),
        createField('Description', descriptionInput),
        createField('Tags', tagsInput),
        createField('Visibility (required)', privacySelect),
        createField('Audience (required)', madeForKidsSelect),
        createField('Altered or synthetic content disclosure', syntheticSelect),
    );

    const rights = createConsent('I own this clip or have permission to upload and distribute it.');
    const guidelines = createConsent('I confirm this video complies with YouTube Community Guidelines.');
    const approval = createConsent('I explicitly approve uploading this exact clip with the title, description and visibility selected above.');
    panel.append(rights.wrapper, guidelines.wrapper, approval.wrapper);

    const retry = createConsent('I checked YouTube Studio and confirmed the previous attempt did not create a video.', 'youtube-retry-confirm hidden');
    panel.append(retry.wrapper);

    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'small-button youtube-upload-button';
    button.textContent = 'Upload this clip to YouTube';
    button.disabled = true;
    panel.append(button);

    const enableButton = () => {
        const retryIsRequired = !retry.wrapper.classList.contains('hidden');
        const retryConfirmed = !retryIsRequired || retry.input.checked;
        button.disabled = !(
            rights.input.checked && guidelines.input.checked && approval.input.checked &&
            titleInput.value.trim() && madeForKidsSelect.value !== '' && retryConfirmed
        );
    };
    [rights.input, guidelines.input, approval.input, titleInput].forEach(element => {
        element.addEventListener('input', enableButton);
        element.addEventListener('change', enableButton);
    });
    madeForKidsSelect.addEventListener('change', enableButton);
    retry.input.addEventListener('change', enableButton);

    button.addEventListener('click', async () => {
        button.disabled = true;
        button.textContent = 'Queueing YouTube upload…';
        const payload = {
            title: titleInput.value,
            description: descriptionInput.value,
            tags: tagsInput.value,
            privacy_status: privacySelect.value,
            contains_synthetic_media: syntheticSelect.value === '' ? null : syntheticSelect.value === 'true',
            rights_confirmed: rights.input.checked,
            guidelines_confirmed: guidelines.input.checked,
            consent_to_upload: approval.input.checked,
            made_for_kids: madeForKidsSelect.value === 'true',
            confirm_retry_after_check: retry.input.checked,
        };
        try {
            const response = await fetch(`/api/v1/clips/${encodeURIComponent(clip.id)}/youtube-upload`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Could not start YouTube upload.');
            state.textContent = data.message || 'YouTube upload queued.';
            button.textContent = 'Upload queued';
            await pollYouTubePublication(clip.id, state, retry, button);
        } catch (error) {
            state.textContent = error.message;
            state.classList.add('error-text');
            button.textContent = 'Try upload again';
            button.disabled = false;
        }
    });

    pollYouTubePublication(clip.id, state, retry, button);
    return panel;
}

async function pollYouTubePublication(clipId, stateElement, retryControl, uploadButton) {
    try {
        const response = await fetch(`/api/v1/clips/${encodeURIComponent(clipId)}/youtube-upload`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Could not read YouTube upload status.');
        const publication = data.publication;
        if (!publication) return;
        stateElement.classList.remove('error-text');
        stateElement.textContent = `${publication.status} · ${publication.progress || 0}%`;
        if (publication.status === 'COMPLETED' && publication.youtube_url) {
            const link = document.createElement('a');
            link.href = publication.youtube_url;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = 'Open uploaded YouTube video';
            link.className = 'youtube-result-link';
            stateElement.replaceChildren(document.createTextNode('Upload complete · '), link);
            uploadButton.textContent = 'Already uploaded';
            uploadButton.disabled = true;
            retryControl.wrapper.classList.add('hidden');
            return;
        }
        if (['QUEUED', 'UPLOADING'].includes(publication.status)) {
            if (publication.status === 'UPLOADING') stateElement.textContent += ' · keep AutoClips AI running';
            setTimeout(() => pollYouTubePublication(clipId, stateElement, retryControl, uploadButton), 1800);
            return;
        }
        if (['FAILED', 'INTERRUPTED'].includes(publication.status)) {
            stateElement.textContent = `${publication.status}: ${publication.error_message || 'Upload needs attention.'}`;
            stateElement.classList.add('error-text');
            retryControl.wrapper.classList.remove('hidden');
            uploadButton.textContent = 'Retry after checking YouTube Studio';
            uploadButton.disabled = true;
            return;
        }
    } catch (error) {
        stateElement.textContent = error.message;
        stateElement.classList.add('error-text');
    }
}

async function loadYouTubeStatus() {
    const pill = document.getElementById('youtube-connection-pill');
    const message = document.getElementById('youtube-connection-message');
    const setupNote = document.getElementById('youtube-setup-note');
    const connectButton = document.getElementById('youtube-connect-button');
    const disconnectButton = document.getElementById('youtube-disconnect-button');
    try {
        const response = await fetch('/api/v1/youtube/status');
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Could not check YouTube connection.');
        youtubeConnected = Boolean(data.connected);
        pill.textContent = youtubeConnected ? 'CONNECTED' : 'NOT CONNECTED';
        pill.className = `status-pill ${youtubeConnected ? 'connected' : ''}`;
        connectButton.classList.toggle('hidden', youtubeConnected);
        disconnectButton.classList.toggle('hidden', !youtubeConnected);
        if (youtubeConnected) {
            message.textContent = `Connected channel: ${data.channel_title || 'YouTube channel'} · ID ${data.channel_id || 'not available'}. Each upload still requires your explicit approval and a selected visibility setting.`;
            setupNote.textContent = 'Uploads use the official YouTube Data API v3. Permissions: upload videos and read the connected channel name so the destination is visible before publishing.';
        } else if (!data.libraries_installed) {
            message.textContent = 'YouTube API packages are not installed. Run setup_windows.bat.';
        } else if (!data.client_configured) {
            message.textContent = 'OAuth Desktop-app credentials are not configured yet.';
        } else {
            message.textContent = data.message || 'OAuth credentials are ready. Connect your account to continue.';
        }
        document.querySelectorAll('.generated-clip-card').forEach(card => {
            const controls = card.querySelector('.youtube-upload-controls');
            if (controls) controls.replaceWith(renderYouTubeUploadControls(
                latestRenderedClips.find(item => card.dataset.clipId === item.id) || { id: card.dataset.clipId, title: 'Generated highlight' }
            ));
        });
    } catch (error) {
        youtubeConnected = false;
        pill.textContent = 'STATUS UNAVAILABLE';
        message.textContent = error.message;
    }
}

async function connectYouTube() {
    const button = document.getElementById('youtube-connect-button');
    const notice = document.getElementById('youtube-notice');
    button.disabled = true;
    button.querySelector('span').textContent = 'Opening Google authorization…';
    notice.classList.add('hidden');
    try {
        const response = await fetch('/api/v1/youtube/connect', { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'YouTube connection failed.');
        notice.textContent = data.message || 'YouTube connected.';
        notice.className = 'notice success';
        await loadYouTubeStatus();
    } catch (error) {
        notice.textContent = error.message;
        notice.className = 'notice error';
    } finally {
        button.disabled = false;
        button.querySelector('span').textContent = '→';
    }
}

async function disconnectYouTube() {
    if (!confirm('Remove the locally saved YouTube authorization? This does not delete videos already uploaded.')) return;
    try {
        const response = await fetch('/api/v1/youtube/disconnect', { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Could not disconnect YouTube.');
        await loadYouTubeStatus();
    } catch (error) {
        const notice = document.getElementById('youtube-notice');
        notice.textContent = error.message;
        notice.className = 'notice error';
    }
}

function renderGeneratedClips(clips) {
    latestRenderedClips = clips;
    const panel = document.getElementById('generated-clips');
    const list = document.getElementById('generated-clip-list');
    list.replaceChildren();
    if (!clips.length) {
        panel.classList.add('hidden');
        return;
    }
    panel.classList.remove('hidden');

    for (const clip of clips) {
        const card = document.createElement('article');
        card.className = 'generated-clip-card';
        card.dataset.clipId = clip.id;
        const details = document.createElement('div');
        details.className = 'generated-clip-details';
        const heading = document.createElement('strong');
        heading.textContent = clip.title || 'Generated highlight';
        const status = document.createElement('span');
        status.className = `clip-status ${String(clip.status || '').toLowerCase()}`;
        status.textContent = clip.status || 'UNKNOWN';
        const meta = document.createElement('p');
        const duration = Number(clip.duration_seconds || (clip.end_seconds - clip.start_seconds) || 0);
        meta.textContent = `${formatTimestamp(clip.start_seconds)} – ${formatTimestamp(clip.end_seconds)} · ${duration.toFixed(1)} sec · score ${clip.score}/100`;
        details.append(heading, status, meta);
        card.append(details);

        if (clip.status === 'COMPLETED') {
            const video = document.createElement('video');
            video.className = 'generated-clip-video';
            video.controls = true;
            video.preload = 'metadata';
            video.playsInline = true;
            video.src = clip.preview_url;
            const footer = document.createElement('div');
            footer.className = 'generated-clip-footer';
            const quality = document.createElement('span');
            quality.textContent = `${clip.width} × ${clip.height} · ${clip.video_codec || 'video'} · ${clip.subtitle_status === 'burned_in' ? 'subtitles added' : 'no speech captions'}`;
            const download = document.createElement('a');
            download.className = 'small-button';
            download.href = clip.download_url;
            download.textContent = 'Download MP4';
            footer.append(quality, download);
            card.append(video, footer);
            card.append(renderYouTubeUploadControls(clip));
        } else if (clip.status === 'FAILED') {
            const error = document.createElement('p');
            error.className = 'clip-error';
            error.textContent = clip.error_message || 'This clip could not be rendered.';
            card.append(error);
        } else {
            const pending = document.createElement('p');
            pending.className = 'clip-pending';
            pending.textContent = 'Rendering locally. Keep AutoClips AI running until this finishes.';
            card.append(pending);
        }
        list.append(card);
    }
}

async function loadGeneratedClips(analysisId) {
    if (activeRenderTimer) clearTimeout(activeRenderTimer);
    activeRenderTimer = null;
    activeRenderAnalysisId = analysisId;
    try {
        const response = await fetch(`/api/v1/analysis/${encodeURIComponent(analysisId)}/clips`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Could not load generated clips.');
        const clips = data.items || [];
        renderGeneratedClips(clips);
        const pending = clips.some(item => ['QUEUED', 'RENDERING'].includes(item.status));
        const button = document.getElementById('generate-clips-button');
        if (pending) {
            button.disabled = true;
            button.querySelector('span').textContent = 'Rendering clips…';
            if (activeRenderTimer) clearTimeout(activeRenderTimer);
            activeRenderTimer = setTimeout(() => loadGeneratedClips(analysisId), 2500);
        } else {
            if (activeRenderTimer) clearTimeout(activeRenderTimer);
            activeRenderTimer = null;
            button.disabled = !document.querySelectorAll('#highlight-list .highlight-card').length;
            button.querySelector('span').textContent = clips.length ? 'Render again' : 'Generate vertical clips';
            if (clips.some(item => item.status === 'COMPLETED')) loadSources();
        }
    } catch (error) {
        showNotice(error.message, 'error');
    }
}

async function startClipRendering(analysisId) {
    const button = document.getElementById('generate-clips-button');
    button.disabled = true;
    button.querySelector('span').textContent = 'Queueing render…';
    try {
        const response = await fetch(`/api/v1/analysis/${encodeURIComponent(analysisId)}/render`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Could not start clip rendering.');
        renderGeneratedClips(data.clips || []);
        await loadGeneratedClips(analysisId);
    } catch (error) {
        button.disabled = false;
        button.querySelector('span').textContent = 'Generate vertical clips';
        showNotice(error.message, 'error');
    }
}

document.getElementById('generate-clips-button').addEventListener('click', () => {
    if (activeRenderAnalysisId) startClipRendering(activeRenderAnalysisId);
});

function renderAnalysis(analysis) {
    const status = analysis.status || 'UNKNOWN';
    document.getElementById('analysis-status').textContent = status;
    document.getElementById('analysis-message').textContent = analysis.message || 'Processing…';
    document.getElementById('analysis-progress-fill').style.width = `${Math.max(0, Math.min(100, analysis.progress || 0))}%`;
    document.getElementById('analysis-title').textContent = `Video intelligence · ${analysis.stage || 'queued'}`;
    const meta = document.getElementById('analysis-meta');
    meta.textContent = analysis.error_message ? `Error: ${analysis.error_message}` :
        `Progress: ${analysis.progress || 0}% · Job: ${analysis.id}`;

    const resultsPanel = document.getElementById('analysis-results');
    if (status !== 'COMPLETED' || !analysis.result) {
        resultsPanel.classList.add('hidden');
        return;
    }

    const result = analysis.result;
    const transcriptCount = result.transcript?.segments?.length || 0;
    const sceneCount = result.scene_count || 0;
    const highlights = result.highlights?.items || [];
    document.getElementById('analysis-stats').innerHTML = '';
    for (const [label, value] of [
        ['Duration', `${Number(result.metadata?.duration_seconds || 0).toFixed(1)} sec`],
        ['Transcript segments', transcriptCount],
        ['Detected scenes', sceneCount],
        ['Highlight candidates', highlights.length],
    ]) {
        const card = document.createElement('div');
        card.className = 'analysis-stat';
        const strong = document.createElement('strong');
        strong.textContent = value;
        const caption = document.createElement('span');
        caption.textContent = label;
        card.append(strong, caption);
        document.getElementById('analysis-stats').append(card);
    }

    const highlightList = document.getElementById('highlight-list');
    highlightList.replaceChildren();
    if (!highlights.length) {
        const empty = document.createElement('p');
        empty.className = 'empty-state';
        empty.textContent = result.highlights?.note || 'No eligible highlight candidates were found.';
        highlightList.append(empty);
    } else {
        highlights.forEach((clip, index) => {
            const card = document.createElement('article');
            card.className = 'highlight-card';
            const heading = document.createElement('strong');
            heading.textContent = `${String(index + 1).padStart(2, '0')} · ${clip.title}`;
            const time = document.createElement('span');
            time.textContent = `${formatTimestamp(clip.start)} – ${formatTimestamp(clip.end)} · ${clip.duration.toFixed(1)} sec · score ${clip.score}/100`;
            const reason = document.createElement('p');
            reason.textContent = clip.reason;
            card.append(heading, time, reason);
            highlightList.append(card);
        });
    }
    document.getElementById('analysis-note').textContent = result.highlights?.note || '';
    const generateButton = document.getElementById('generate-clips-button');
    generateButton.disabled = highlights.length === 0;
    generateButton.querySelector('span').textContent = highlights.length
        ? `Generate ${highlights.length} vertical clip${highlights.length === 1 ? '' : 's'}`
        : 'No eligible clips to render';
    activeRenderAnalysisId = analysis.id;
    resultsPanel.classList.remove('hidden');
    loadGeneratedClips(analysis.id);
}

function formatTimestamp(seconds) {
    const total = Math.max(0, Math.floor(Number(seconds) || 0));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const secs = total % 60;
    return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${String(secs).padStart(2, '0')}` :
        `${minutes}:${String(secs).padStart(2, '0')}`;
}

async function startAnalysis(sourceId) {
    showAnalysisPanel();
    document.getElementById('analysis-title').textContent = 'Starting local analysis';
    document.getElementById('analysis-message').textContent = 'Checking dependencies and queuing the analysis job…';
    document.getElementById('analysis-status').textContent = 'QUEUED';
    document.getElementById('analysis-results').classList.add('hidden');
    try {
        const response = await fetch(`/api/v1/sources/${encodeURIComponent(sourceId)}/analyze`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Could not start analysis.');
        const analysisId = data.analysis_id || data.analysis?.id;
        if (!analysisId) throw new Error('The server did not return an analysis ID.');
        await pollAnalysis(analysisId);
    } catch (error) {
        document.getElementById('analysis-status').textContent = 'ERROR';
        document.getElementById('analysis-message').textContent = error.message;
    }
}

async function pollAnalysis(analysisId) {
    if (activeAnalysisTimer) clearTimeout(activeAnalysisTimer);
    try {
        const response = await fetch(`/api/v1/analysis/${encodeURIComponent(analysisId)}`);
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || 'Could not read analysis status.');
        renderAnalysis(data);
        if (['QUEUED', 'RUNNING'].includes(data.status)) {
            activeAnalysisTimer = setTimeout(() => pollAnalysis(analysisId), 2500);
        } else {
            loadSources();
        }
    } catch (error) {
        document.getElementById('analysis-status').textContent = 'ERROR';
        document.getElementById('analysis-message').textContent = error.message;
    }
}

async function loadSystemStatus() {
    try {
        const [healthResponse, capabilityResponse] = await Promise.all([
            fetch('/api/v1/health'),
            fetch('/api/v1/analysis/capabilities'),
        ]);
        if (!healthResponse.ok || !capabilityResponse.ok) throw new Error('Health check failed');
        const health = await healthResponse.json();
        const capabilities = await capabilityResponse.json();
        const mediaReady = health.ffmpeg_available && health.ffprobe_available;
        const analysisReady = capabilities.faster_whisper_installed && capabilities.scenedetect_installed;
        const parts = ['API ONLINE', mediaReady ? 'MEDIA READY' : 'MEDIA TOOLS MISSING', analysisReady ? 'AI PACKAGES READY' : 'RUN SETUP_WINDOWS.BAT', mediaReady ? 'CLIP RENDERER READY' : 'RENDERER UNAVAILABLE'];
        document.getElementById('system-status').textContent = parts.join(' · ');
    } catch {
        document.getElementById('system-status').textContent = 'API OFFLINE';
    }
}

document.getElementById('youtube-connect-button').addEventListener('click', connectYouTube);
document.getElementById('youtube-disconnect-button').addEventListener('click', disconnectYouTube);

loadSystemStatus();
loadSources();
loadYouTubeStatus();
