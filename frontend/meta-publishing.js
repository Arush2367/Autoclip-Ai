(function () {
    'use strict';

    const panel = document.createElement('section');
    panel.className = 'panel meta-publishing-panel';
    panel.id = 'meta-publishing-panel';
    panel.setAttribute('aria-labelledby', 'meta-publishing-heading');
    panel.innerHTML = `
        <div class="section-heading">
            <div>
                <p class="eyebrow">MILESTONE 05 / OFFICIAL META APIs</p>
                <h2 id="meta-publishing-heading">Instagram &amp; Facebook Reels</h2>
            </div>
            <span class="status-pill" id="meta-integration-pill">CHECKING</span>
        </div>
        <p class="meta-publishing-intro">Instagram uses your Meta Instagram API with Unified Login token. Facebook Reels uses a separate Facebook Page access token. You can connect Instagram first and add Facebook later.</p>
        <div class="meta-platform-grid">
            <article class="meta-platform-card">
                <div class="meta-platform-top"><h3 class="meta-platform-name">Instagram Reels</h3><span class="meta-platform-state" id="meta-instagram-state">CHECKING</span></div>
                <p class="meta-platform-detail" id="meta-instagram-detail">Checking local connection…</p>
            </article>
            <article class="meta-platform-card">
                <div class="meta-platform-top"><h3 class="meta-platform-name">Facebook Reels</h3><span class="meta-platform-state" id="meta-facebook-state">CHECKING</span></div>
                <p class="meta-platform-detail" id="meta-facebook-detail">Checking local connection…</p>
            </article>
        </div>
        <form class="meta-credential-form" id="meta-credential-form">
            <label class="meta-field">
                <span>Instagram Unified Login access token <strong>(required for Instagram)</strong></span>
                <input id="meta-instagram-token" type="password" autocomplete="off" spellcheck="false" placeholder="Paste the newly generated token from Meta" />
            </label>
            <label class="meta-field">
                <span>Facebook Page access token <strong>(optional; for Facebook Reels)</strong></span>
                <input id="meta-facebook-token" type="password" autocomplete="off" spellcheck="false" placeholder="Add separately when your Page token is ready" />
            </label>
            <button class="primary-button meta-connect-button" id="meta-connect-button" type="submit">Validate &amp; save locally <span aria-hidden="true">→</span></button>
        </form>
        <div class="meta-account-actions">
            <button class="small-button" id="meta-disconnect-button" type="button" hidden>Remove locally saved Meta tokens</button>
            <button class="small-button meta-refresh-button" id="meta-refresh-button" type="button">Refresh status ↻</button>
        </div>
        <div class="meta-integration-footer">
            <p class="meta-integration-message" id="meta-integration-message" role="status" aria-live="polite">Checking Meta connection…</p>
        </div>
        <p class="meta-security-note">Tokens are sent only to this local AutoClips server and stored in the ignored storage/secrets/meta_auth.json file. They are never returned to the browser, logged, included in this ZIP, or committed to GitHub. Keep AutoClips bound to 127.0.0.1.</p>
    `;

    const footer = document.querySelector('main.shell > footer');
    if (footer) footer.before(panel);

    const $ = selector => panel.querySelector(selector);
    const refreshButton = $('#meta-refresh-button');
    const connectButton = $('#meta-connect-button');
    const disconnectButton = $('#meta-disconnect-button');
    const form = $('#meta-credential-form');
    const instagramTokenInput = $('#meta-instagram-token');
    const facebookTokenInput = $('#meta-facebook-token');
    const integrationPill = $('#meta-integration-pill');
    const integrationMessage = $('#meta-integration-message');
    let metaStatus = null;

    function setNotice(message, kind = '') {
        integrationMessage.textContent = message;
        integrationMessage.className = `meta-integration-message ${kind}`.trim();
    }

    function updatePlatform(platform, info) {
        const state = $(`#meta-${platform}-state`);
        const detail = $(`#meta-${platform}-detail`);
        const connected = Boolean(info && info.connected);
        state.textContent = connected ? 'CONNECTED' : 'NOT CONNECTED';
        state.classList.toggle('connected', connected);
        if (connected) {
            detail.textContent = `Connected destination: ${info.account_name || info.account_id || 'Account linked'}`;
        } else if (platform === 'instagram') {
            detail.textContent = 'Add the Business Integration System User access token generated under Instagram API → Unified Login → Generate access tokens.';
        } else {
            detail.textContent = 'Add a Facebook Page access token separately. Instagram Unified Login does not automatically grant Facebook Page publishing access.';
        }
    }

    async function loadMetaStatus() {
        refreshButton.disabled = true;
        integrationPill.textContent = 'CHECKING';
        try {
            const response = await fetch('/api/v1/meta/status', { headers: { Accept: 'application/json' } });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Could not load Meta status.');
            metaStatus = data;
            updatePlatform('instagram', data.platforms && data.platforms.instagram);
            updatePlatform('facebook', data.platforms && data.platforms.facebook);
            const instagramConnected = Boolean(data.platforms?.instagram?.connected);
            const facebookConnected = Boolean(data.platforms?.facebook?.connected);
            integrationPill.textContent = instagramConnected && facebookConnected ? 'BOTH CONNECTED' :
                instagramConnected || facebookConnected ? 'PARTIALLY CONNECTED' : 'READY TO CONNECT';
            integrationPill.className = `status-pill ${instagramConnected || facebookConnected ? 'connected' : ''}`;
            disconnectButton.hidden = !(instagramConnected || facebookConnected);
            setNotice(data.message || 'Meta connection status loaded.', instagramConnected || facebookConnected ? 'success' : '');
            refreshClipControls();
        } catch (error) {
            integrationPill.textContent = 'STATUS UNAVAILABLE';
            setNotice(error.message || 'Could not read Meta connection status.', 'error');
        } finally {
            refreshButton.disabled = false;
        }
    }

    form.addEventListener('submit', async event => {
        event.preventDefault();
        const instagramAccessToken = instagramTokenInput.value.trim();
        const facebookPageAccessToken = facebookTokenInput.value.trim();
        if (!instagramAccessToken && !facebookPageAccessToken) {
            setNotice('Enter the Instagram token. The Facebook Page token can be added later.', 'warning');
            return;
        }
        connectButton.disabled = true;
        connectButton.querySelector('span').textContent = 'Validating with Meta…';
        setNotice('Validating credentials with Meta. Tokens are not displayed or logged.', '');
        try {
            const response = await fetch('/api/v1/meta/connect', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
                body: JSON.stringify({
                    instagram_access_token: instagramAccessToken || null,
                    facebook_page_access_token: facebookPageAccessToken || null,
                }),
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Meta credential validation failed.');
            instagramTokenInput.value = '';
            facebookTokenInput.value = '';
            setNotice(data.message || 'Meta credentials validated and saved locally.', 'success');
            await loadMetaStatus();
        } catch (error) {
            setNotice(error.message || 'Meta credential validation failed.', 'error');
        } finally {
            // Do not retain access tokens in the page after validation, even if Meta rejects them.
            instagramTokenInput.value = '';
            facebookTokenInput.value = '';
            connectButton.disabled = false;
            connectButton.querySelector('span').textContent = '→';
        }
    });

    disconnectButton.addEventListener('click', async () => {
        if (!window.confirm('Remove locally saved Instagram and Facebook access tokens? This does not delete Reels already published.')) return;
        disconnectButton.disabled = true;
        try {
            const response = await fetch('/api/v1/meta/disconnect', { method: 'POST' });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Could not remove Meta tokens.');
            setNotice(data.message || 'Local tokens removed.', 'success');
            await loadMetaStatus();
        } catch (error) {
            setNotice(error.message, 'error');
        } finally {
            disconnectButton.disabled = false;
        }
    });

    refreshButton.addEventListener('click', loadMetaStatus);

    function makeConsent(text, extraClass = '') {
        const label = document.createElement('label');
        label.className = `meta-consent ${extraClass}`.trim();
        const input = document.createElement('input');
        input.type = 'checkbox';
        const span = document.createElement('span');
        span.textContent = text;
        label.append(input, span);
        return { label, input };
    }

    function canPublish(platform) {
        return Boolean(metaStatus && metaStatus.platforms && metaStatus.platforms[platform] && metaStatus.platforms[platform].connected);
    }

    function addClipControls(card) {
        if (card.dataset.metaControlsAdded === '1' || !card.querySelector('.generated-clip-video')) return;
        card.dataset.metaControlsAdded = '1';
        const clipId = card.dataset.clipId;
        const section = document.createElement('section');
        section.className = 'meta-clip-controls';
        const heading = document.createElement('h4');
        heading.textContent = 'Publish this clip to Meta';
        const state = document.createElement('p');
        state.className = 'meta-clip-state';
        state.textContent = metaStatus && metaStatus.publishing_enabled
            ? 'Choose Instagram, Facebook, or both. Each selected destination is published separately.'
            : 'Connect at least one Meta destination above to enable publishing.';

        const captionLabel = document.createElement('label');
        captionLabel.className = 'meta-field';
        const captionTitle = document.createElement('span');
        captionTitle.textContent = 'Caption (up to 2,200 characters)';
        const caption = document.createElement('textarea');
        caption.rows = 3;
        caption.maxLength = 2200;
        caption.placeholder = 'Write a caption for this Reel…';
        captionLabel.append(captionTitle, caption);

        const platformWrap = document.createElement('div');
        platformWrap.className = 'meta-publish-targets';
        const targets = {};
        for (const [key, labelText] of [['instagram', 'Instagram Reels'], ['facebook', 'Facebook Reels']]) {
            const label = document.createElement('label');
            label.className = 'meta-target';
            const input = document.createElement('input');
            input.type = 'checkbox';
            input.value = key;
            input.disabled = !canPublish(key);
            const text = document.createElement('span');
            text.textContent = labelText;
            label.append(input, text);
            platformWrap.append(label);
            targets[key] = input;
        }
        const ai = makeConsent('This video is AI-generated or materially altered (disclose this to Meta).', 'meta-consent-ai');
        const rights = makeConsent('I own this clip or have permission to publish it.');
        const guidelines = makeConsent('I confirm this clip follows Instagram and Facebook content rules.');
        const approval = makeConsent('I approve publishing this exact clip and caption to the selected destinations.');
        const retry = makeConsent('I checked the destination and confirmed the previous attempt did not publish this clip.', 'meta-retry-consent');
        retry.label.hidden = true;

        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'small-button meta-publish-button';
        button.textContent = 'Publish selected destinations';
        button.disabled = true;

        const updateButton = () => {
            const anyAvailableSelected = Object.entries(targets).some(([key, input]) => input.checked && canPublish(key));
            const retryRequired = !retry.label.hidden;
            button.disabled = !(anyAvailableSelected && rights.input.checked && guidelines.input.checked &&
                approval.input.checked && caption.value.trim() && (!retryRequired || retry.input.checked));
        };
        Object.values(targets).forEach(input => input.addEventListener('change', updateButton));
        [rights.input, guidelines.input, approval.input, caption].forEach(input => {
            input.addEventListener('input', updateButton);
            input.addEventListener('change', updateButton);
        });
        retry.input.addEventListener('change', updateButton);

        button.addEventListener('click', async () => {
            const platforms = Object.entries(targets).filter(([key, input]) => input.checked && canPublish(key)).map(([key]) => key);
            if (!platforms.length) {
                state.textContent = 'No connected destination selected. Connect Instagram or Facebook above first.';
                return;
            }
            button.disabled = true;
            button.textContent = 'Queueing Meta upload…';
            try {
                const response = await fetch(`/api/v1/meta/clips/${encodeURIComponent(clipId)}/publish`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        platforms,
                        caption: caption.value,
                        is_ai_generated: ai.input.checked,
                        rights_confirmed: rights.input.checked,
                        guidelines_confirmed: guidelines.input.checked,
                        consent_to_publish: approval.input.checked,
                        confirm_retry_after_check: retry.input.checked,
                    }),
                });
                const data = await response.json();
                if (!response.ok) throw new Error(data.detail || 'Could not start Meta publishing.');
                state.textContent = data.message || 'Meta publishing queued.';
                button.textContent = 'Publishing…';
                pollClipPublications(clipId, state, button, retry, section);
            } catch (error) {
                state.textContent = error.message;
                state.classList.add('error-text');
                button.textContent = 'Publish selected destinations';
                updateButton();
            }
        });

        section.append(heading, state, captionLabel, platformWrap, ai.label, rights.label, guidelines.label, approval.label, retry.label, button);
        const youtubeControls = card.querySelector('.youtube-upload-controls');
        if (youtubeControls) youtubeControls.after(section);
        else card.append(section);
        updateButton();
        pollClipPublications(clipId, state, button, retry, section);
    }

    async function pollClipPublications(clipId, state, button, retry, section) {
        try {
            const response = await fetch(`/api/v1/meta/clips/${encodeURIComponent(clipId)}/publications`);
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Could not load Meta publication status.');
            const items = data.items || [];
            if (!items.length) return;
            state.textContent = items.map(item => `${item.platform}: ${item.status}${item.progress ? ` ${item.progress}%` : ''}${item.error_message ? ` (${item.error_message})` : ''}`).join(' · ');
            state.classList.toggle('error-text', items.some(item => ['FAILED', 'INTERRUPTED'].includes(item.status)));
            for (const item of items) {
                const target = section.querySelector(`.meta-target input[value="${item.platform}"]`);
                if (target && item.status === 'COMPLETED') {
                    target.checked = false;
                    target.dataset.published = '1';
                    target.disabled = true;
                } else if (target && ['FAILED', 'INTERRUPTED'].includes(item.status) && canPublish(item.platform)) {
                    target.checked = true;
                    target.dataset.published = '0';
                    target.disabled = false;
                }
            }
            if (items.some(item => ['QUEUED', 'UPLOADING', 'PROCESSING'].includes(item.status))) {
                button.textContent = 'Publishing…';
                button.disabled = true;
                window.setTimeout(() => pollClipPublications(clipId, state, button, retry, section), 5000);
                return;
            }
            const failed = items.some(item => ['FAILED', 'INTERRUPTED'].includes(item.status));
            const completed = items.filter(item => item.status === 'COMPLETED').length;
            if (failed) {
                retry.label.hidden = false;
                retry.input.checked = false;
                button.textContent = 'Retry only after checking Meta';
                button.disabled = true;
                return;
            }
            if (completed === items.length) {
                button.textContent = 'Published to selected platforms';
                button.disabled = true;
            }
        } catch (error) {
            state.textContent = error.message;
            state.classList.add('error-text');
        }
    }

    function refreshClipControls() {
        document.querySelectorAll('.generated-clip-card').forEach(card => {
            const section = card.querySelector('.meta-clip-controls');
            if (!section) {
                addClipControls(card);
                return;
            }
            section.querySelectorAll('.meta-target input').forEach(input => {
                if (input.dataset.published !== '1') input.disabled = !canPublish(input.value);
                const label = input.closest('label');
                if (label) label.classList.toggle('unavailable', input.disabled);
            });
        });
    }

    const clipList = document.getElementById('generated-clip-list');
    if (clipList) {
        const observer = new MutationObserver(() => refreshClipControls());
        observer.observe(clipList, { childList: true, subtree: true });
    }

    refreshButton.addEventListener('click', loadMetaStatus);
    loadMetaStatus();
})();
