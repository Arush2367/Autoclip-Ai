(function () {
    'use strict';

    const panel = document.createElement('section');
    panel.className = 'panel meta-publishing-panel';
    panel.id = 'meta-publishing-panel';
    panel.setAttribute('aria-labelledby', 'meta-publishing-heading');
    panel.innerHTML = `
        <div class="section-heading">
            <div>
                <p class="eyebrow">MILESTONE 05 / META INTEGRATION FOUNDATION</p>
                <h2 id="meta-publishing-heading">Instagram &amp; Facebook Reels</h2>
            </div>
            <span class="status-pill" id="meta-integration-pill">CHECKING</span>
        </div>
        <p class="meta-publishing-intro">
            The app-side integration foundation is installed. Instagram and Facebook account
            authorization and real publishing will be connected in the next phase.
        </p>
        <div class="meta-platform-grid">
            <article class="meta-platform-card" id="meta-instagram-card">
                <div class="meta-platform-top">
                    <h3 class="meta-platform-name">Instagram Reels</h3>
                    <span class="meta-platform-state" id="meta-instagram-state">CHECKING</span>
                </div>
                <p class="meta-platform-detail" id="meta-instagram-detail">Reading local integration status…</p>
            </article>
            <article class="meta-platform-card" id="meta-facebook-card">
                <div class="meta-platform-top">
                    <h3 class="meta-platform-name">Facebook Reels</h3>
                    <span class="meta-platform-state" id="meta-facebook-state">CHECKING</span>
                </div>
                <p class="meta-platform-detail" id="meta-facebook-detail">Reading local integration status…</p>
            </article>
        </div>
        <div class="meta-integration-footer">
            <p class="meta-integration-message" id="meta-integration-message" role="status" aria-live="polite">
                No Meta API calls or uploads are made in this preparation phase.
            </p>
            <button class="small-button meta-refresh-button" id="meta-refresh-button" type="button">Refresh status ↻</button>
        </div>
    `;

    const footer = document.querySelector('main.shell > footer');
    if (footer) footer.before(panel);

    const refreshButton = panel.querySelector('#meta-refresh-button');
    const integrationPill = panel.querySelector('#meta-integration-pill');
    const integrationMessage = panel.querySelector('#meta-integration-message');

    function updatePlatform(platform, info, credentialsConfigured) {
        const state = panel.querySelector(`#meta-${platform}-state`);
        const detail = panel.querySelector(`#meta-${platform}-detail`);
        if (!state || !detail) return;

        const connected = Boolean(info && info.connected);
        state.textContent = connected ? 'CONNECTED' : 'READY FOR CONNECTION';
        state.classList.toggle('connected', connected);

        if (connected) {
            detail.textContent = `Connected account: ${info.account_name || info.account_id || 'Account linked'}. Publishing controls will be enabled when the Meta API publishing phase is installed.`;
        } else if (credentialsConfigured) {
            detail.textContent = 'Meta app credentials are detected locally. Account authorization is the next integration step.';
        } else {
            detail.textContent = 'App-side support is prepared. Meta app credentials and account authorization will be connected in the next phase.';
        }
    }

    async function loadMetaStatus() {
        refreshButton.disabled = true;
        integrationPill.textContent = 'CHECKING';
        try {
            const response = await fetch('/api/v1/meta/status', { headers: { Accept: 'application/json' } });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || 'Could not load Meta integration status.');

            const credentialsConfigured = Boolean(data.credentials && data.credentials.credentials_configured);
            updatePlatform('instagram', data.platforms && data.platforms.instagram, credentialsConfigured);
            updatePlatform('facebook', data.platforms && data.platforms.facebook, credentialsConfigured);
            integrationPill.textContent = data.integration_ready ? 'INTEGRATION READY' : 'NEEDS ATTENTION';
            integrationPill.className = `status-pill ${data.integration_ready ? 'connected' : ''}`;
            integrationMessage.textContent = data.message || 'Meta API connection is the next phase. No upload was started.';
        } catch (error) {
            integrationPill.textContent = 'STATUS UNAVAILABLE';
            integrationMessage.textContent = error.message || 'Could not read Meta integration status.';
        } finally {
            refreshButton.disabled = false;
        }
    }

    refreshButton.addEventListener('click', loadMetaStatus);
    loadMetaStatus();
})();
