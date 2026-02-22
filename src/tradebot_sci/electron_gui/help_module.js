// ═══════════════════════════════════════════════════════════════
// HELP MODULE — Documentation viewer with markdown rendering
// ═══════════════════════════════════════════════════════════════
window.helpModule = (() => {
    let initialized = false;
    let docCatalog = [];
    let activeDoc = null;

    // ── Markdown → HTML Renderer ─────────────────────────────
    function renderMarkdown(md) {
        // Phase 1: Extract code blocks to protect them from inline processing
        const codeBlocks = [];
        let processed = md.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
            const idx = codeBlocks.length;
            const escaped = escapeHtml(code.trimEnd());
            const langLabel = lang ? `<div class="help-code-lang">${lang}</div>` : '';
            codeBlocks.push(`<div class="help-code-block">${langLabel}<pre><code>${escaped}</code></pre></div>`);
            return `%%CODEBLOCK_${idx}%%`;
        });

        // Phase 2: Process line by line
        const lines = processed.split('\n');
        let html = '';
        let inTable = false;
        let tableRows = [];
        let inList = false;
        let listType = '';
        let listItems = [];
        let inBlockquote = false;
        let blockquoteLines = [];
        let alertType = null;

        function flushTable() {
            if (!inTable) return;
            inTable = false;
            if (tableRows.length < 2) { tableRows = []; return; }
            let t = '<div class="help-table-wrap"><table class="help-table"><thead><tr>';
            const headers = tableRows[0].split('|').map(c => c.trim()).filter(Boolean);
            headers.forEach(h => { t += `<th>${inlineFormat(h)}</th>`; });
            t += '</tr></thead><tbody>';
            for (let i = 2; i < tableRows.length; i++) {
                const cells = tableRows[i].split('|').map(c => c.trim()).filter(Boolean);
                t += '<tr>';
                cells.forEach(c => { t += `<td>${inlineFormat(c)}</td>`; });
                t += '</tr>';
            }
            t += '</tbody></table></div>';
            html += t;
            tableRows = [];
        }

        function flushList() {
            if (!inList) return;
            inList = false;
            const tag = listType === 'ol' ? 'ol' : 'ul';
            html += `<${tag} class="help-list">`;
            listItems.forEach(item => {
                html += `<li>${inlineFormat(item)}</li>`;
            });
            html += `</${tag}>`;
            listItems = [];
        }

        function flushBlockquote() {
            if (!inBlockquote) return;
            inBlockquote = false;

            const content = blockquoteLines.join('\n');
            blockquoteLines = [];

            // Check for GitHub-style alerts
            const alertMatch = content.match(/^\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*\n?([\s\S]*)/);
            if (alertMatch) {
                const type = alertMatch[1].toLowerCase();
                const body = alertMatch[2].trim();
                const icons = {
                    note: 'info', tip: 'lightbulb', important: 'priority_high',
                    warning: 'warning', caution: 'dangerous'
                };
                const colors = {
                    note: 'var(--accent, #14b8a6)',
                    tip: '#22c55e',
                    important: '#a78bfa',
                    warning: '#f59e0b',
                    caution: '#ef4444'
                };
                html += `<div class="help-alert help-alert-${type}" style="border-left-color: ${colors[type]};">
                    <div class="help-alert-header" style="color: ${colors[type]};">
                        <span class="material-symbols-outlined" style="font-size: 16px;">${icons[type]}</span>
                        <span>${type.toUpperCase()}</span>
                    </div>
                    <div class="help-alert-body">${inlineFormat(body)}</div>
                </div>`;
            } else {
                html += `<blockquote class="help-blockquote">${inlineFormat(content)}</blockquote>`;
            }
        }

        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            const trimmed = line.trim();

            // Code block placeholder
            if (trimmed.match(/^%%CODEBLOCK_\d+%%$/)) {
                flushTable(); flushList(); flushBlockquote();
                const idx = parseInt(trimmed.match(/\d+/)[0]);
                html += codeBlocks[idx];
                continue;
            }

            // Horizontal rule
            if (/^(-{3,}|\*{3,}|_{3,})$/.test(trimmed)) {
                flushTable(); flushList(); flushBlockquote();
                html += '<hr class="help-hr">';
                continue;
            }

            // Table row
            if (trimmed.includes('|') && !trimmed.startsWith('>')) {
                flushList(); flushBlockquote();
                if (!inTable) inTable = true;
                tableRows.push(trimmed);
                continue;
            } else {
                flushTable();
            }

            // Blockquote
            if (trimmed.startsWith('>')) {
                flushTable(); flushList();
                if (!inBlockquote) inBlockquote = true;
                blockquoteLines.push(trimmed.replace(/^>\s?/, ''));
                continue;
            } else {
                flushBlockquote();
            }

            // List items (unordered: - or *, ordered: 1.)
            const ulMatch = trimmed.match(/^[-*]\s+(.*)/);
            const olMatch = trimmed.match(/^\d+\.\s+(.*)/);
            if (ulMatch || olMatch) {
                flushTable(); flushBlockquote();
                const newType = ulMatch ? 'ul' : 'ol';
                if (inList && listType !== newType) flushList();
                inList = true;
                listType = newType;
                listItems.push(ulMatch ? ulMatch[1] : olMatch[1]);
                continue;
            } else if (inList && trimmed === '') {
                flushList();
                continue;
            } else if (inList && /^\s{2,}/.test(line)) {
                // Continuation / nested
                listItems[listItems.length - 1] += ' ' + trimmed;
                continue;
            } else {
                flushList();
            }

            // Headers
            const headerMatch = trimmed.match(/^(#{1,6})\s+(.*)/);
            if (headerMatch) {
                flushTable(); flushList(); flushBlockquote();
                const level = headerMatch[1].length;
                const text = headerMatch[2];
                const id = text.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/-+$/, '');
                html += `<h${level} class="help-h${level}" id="h-${id}">${inlineFormat(text)}</h${level}>`;
                continue;
            }

            // Empty line → paragraph break
            if (trimmed === '') {
                continue;
            }

            // Regular paragraph
            html += `<p class="help-p">${inlineFormat(trimmed)}</p>`;
        }

        // Flush remaining
        flushTable(); flushList(); flushBlockquote();
        return html;
    }

    function escapeHtml(str) {
        return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    function inlineFormat(text) {
        if (!text) return '';
        // Process inline elements (order matters)
        return text
            // Images
            .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, '<img src="$2" alt="$1" class="help-img">')
            // Links
            .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" class="help-link" target="_blank" rel="noopener">$1</a>')
            // Bold + italic
            .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
            // Bold
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            // Italic
            .replace(/\*(.+?)\*/g, '<em>$1</em>')
            // Inline code
            .replace(/`([^`]+)`/g, '<code class="help-inline-code">$1</code>')
            // Emoji shortcuts (common ones in the docs)
            .replace(/⭐/g, '<span style="color: #f59e0b;">⭐</span>');
    }

    // ── CSS for the markdown content, using theme variables ──
    function injectStyles() {
        if (document.getElementById('help-module-styles')) return;
        const style = document.createElement('style');
        style.id = 'help-module-styles';
        style.textContent = `
            /* ── Doc Picker Items ── */
            .help-doc-item {
                display: flex;
                align-items: center;
                gap: 0.75rem;
                padding: 0.625rem 0.875rem;
                border-radius: 0.625rem;
                cursor: pointer;
                transition: all 0.2s ease;
                border: 1px solid transparent;
                color: var(--text-secondary, #94a3b8);
                font-size: 0.8125rem;
                font-weight: 500;
            }
            .help-doc-item:hover {
                background: rgba(255,255,255,0.04);
                color: var(--text-primary, #e2e8f0);
            }
            .help-doc-item.active {
                background: var(--accent-dim, rgba(20,184,166,0.15));
                color: var(--accent, #14b8a6);
                border-color: var(--accent-glow, rgba(20,184,166,0.3));
                font-weight: 700;
            }
            .help-doc-item .doc-icon {
                font-size: 1.125rem;
                flex-shrink: 0;
                color: inherit;
                opacity: 0.7;
            }
            .help-doc-item.active .doc-icon {
                opacity: 1;
            }
            .help-doc-item .doc-title {
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .help-category-label {
                font-size: 0.5625rem;
                font-weight: 900;
                text-transform: uppercase;
                letter-spacing: 0.15em;
                color: var(--text-muted, #64748b);
                padding: 1rem 0.875rem 0.375rem;
            }

            /* ── Markdown Content Styles ── */
            .help-h1 {
                font-size: 2.125rem;
                font-weight: 800;
                color: var(--text-primary, #e2e8f0);
                margin: 0 0 1rem 0;
                padding-bottom: 0.75rem;
                border-bottom: 2px solid var(--accent-dim, rgba(20,184,166,0.15));
                line-height: 1.3;
            }
            .help-h2 {
                font-size: 1.625rem;
                font-weight: 700;
                color: var(--text-primary, #e2e8f0);
                margin: 2rem 0 0.75rem 0;
                padding-bottom: 0.5rem;
                border-bottom: 1px solid rgba(255,255,255,0.06);
                line-height: 1.3;
            }
            .help-h3 {
                font-size: 1.325rem;
                font-weight: 700;
                color: var(--accent, #14b8a6);
                margin: 1.5rem 0 0.5rem 0;
                line-height: 1.3;
            }
            .help-h4, .help-h5, .help-h6 {
                font-size: 1.125rem;
                font-weight: 700;
                color: var(--text-primary, #e2e8f0);
                margin: 1.25rem 0 0.375rem 0;
                line-height: 1.3;
            }
            .help-p {
                font-size: 1.0625rem;
                line-height: 1.75;
                color: var(--text-secondary, #94a3b8);
                margin: 0.5rem 0;
            }
            .help-p strong {
                color: var(--text-primary, #e2e8f0);
                font-weight: 700;
            }
            .help-p em {
                color: var(--text-primary, #e2e8f0);
                font-style: italic;
            }
            .help-link {
                color: var(--accent, #14b8a6);
                text-decoration: none;
                font-weight: 600;
                border-bottom: 1px solid var(--accent-dim, rgba(20,184,166,0.3));
                transition: all 0.15s ease;
            }
            .help-link:hover {
                border-bottom-color: var(--accent, #14b8a6);
            }
            .help-inline-code {
                background: rgba(0,0,0,0.35);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 4px;
                padding: 0.125rem 0.375rem;
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 0.8em;
                color: var(--accent, #14b8a6);
            }
            .help-code-block {
                position: relative;
                margin: 1rem 0;
                border-radius: 0.75rem;
                overflow: hidden;
                border: 1px solid rgba(255,255,255,0.06);
                background: rgba(0,0,0,0.4);
            }
            .help-code-lang {
                position: absolute;
                top: 0;
                right: 0;
                padding: 0.25rem 0.75rem;
                font-size: 0.625rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                color: var(--text-muted, #64748b);
                background: rgba(0,0,0,0.3);
                border-bottom-left-radius: 0.5rem;
            }
            .help-code-block pre {
                margin: 0;
                padding: 1rem 1.25rem;
                overflow-x: auto;
            }
            .help-code-block code {
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 0.9375rem;
                line-height: 1.6;
                color: var(--text-primary, #e2e8f0);
            }

            /* ── Tables ── */
            .help-table-wrap {
                overflow-x: auto;
                margin: 1rem 0;
                border-radius: 0.75rem;
                border: 1px solid rgba(255,255,255,0.06);
            }
            .help-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 1.0rem;
            }
            .help-table th {
                text-align: left;
                padding: 0.625rem 1rem;
                font-weight: 700;
                font-size: 0.8125rem;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: var(--accent, #14b8a6);
                background: rgba(0,0,0,0.3);
                border-bottom: 1px solid rgba(255,255,255,0.06);
            }
            .help-table td {
                padding: 0.5rem 1rem;
                color: var(--text-secondary, #94a3b8);
                border-bottom: 1px solid rgba(255,255,255,0.03);
                line-height: 1.5;
            }
            .help-table td strong {
                color: var(--text-primary, #e2e8f0);
            }
            .help-table tr:hover td {
                background: rgba(255,255,255,0.02);
            }
            .help-table tr:last-child td {
                border-bottom: none;
            }

            /* ── Blockquotes ── */
            .help-blockquote {
                border-left: 3px solid var(--accent-dim, rgba(20,184,166,0.3));
                padding: 0.5rem 1rem;
                margin: 1rem 0;
                color: var(--text-secondary, #94a3b8);
                font-size: 1.0625rem;
                font-style: italic;
                background: rgba(0,0,0,0.15);
                border-radius: 0 0.5rem 0.5rem 0;
            }
            .help-blockquote strong {
                color: var(--text-primary, #e2e8f0);
            }

            /* ── GitHub-style alerts ── */
            .help-alert {
                border-left: 3px solid;
                padding: 0.75rem 1rem;
                margin: 1rem 0;
                border-radius: 0 0.5rem 0.5rem 0;
                background: rgba(0,0,0,0.2);
            }
            .help-alert-header {
                display: flex;
                align-items: center;
                gap: 0.375rem;
                font-size: 0.875rem;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 0.05em;
                margin-bottom: 0.375rem;
            }
            .help-alert-body {
                font-size: 1.0rem;
                line-height: 1.6;
                color: var(--text-secondary, #94a3b8);
            }
            .help-alert-body strong {
                color: var(--text-primary, #e2e8f0);
            }

            /* ── Lists ── */
            .help-list {
                margin: 0.625rem 0;
                padding-left: 1.5rem;
                font-size: 1.0625rem;
                line-height: 1.75;
                color: var(--text-secondary, #94a3b8);
            }
            .help-list li {
                margin: 0.25rem 0;
            }
            .help-list li strong {
                color: var(--text-primary, #e2e8f0);
            }
            .help-list li code {
                background: rgba(0,0,0,0.35);
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 4px;
                padding: 0.125rem 0.375rem;
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 0.8em;
                color: var(--accent, #14b8a6);
            }
            ul.help-list {
                list-style-type: disc;
            }
            ul.help-list li::marker {
                color: var(--accent, #14b8a6);
            }
            ol.help-list {
                list-style-type: decimal;
            }
            ol.help-list li::marker {
                color: var(--accent, #14b8a6);
                font-weight: 700;
            }

            /* ── Horizontal Rule ── */
            .help-hr {
                border: none;
                border-top: 1px solid rgba(255,255,255,0.06);
                margin: 2rem 0;
            }

            /* ── Images ── */
            .help-img {
                max-width: 100%;
                border-radius: 0.5rem;
                margin: 0.5rem 0;
            }

            /* ── Search highlight ── */
            .help-search-highlight {
                background: var(--accent-dim, rgba(20,184,166,0.3));
                color: var(--accent, #14b8a6);
                padding: 0.05rem 0.2rem;
                border-radius: 2px;
                font-weight: 700;
            }

            /* ── Smooth scroll for content ── */
            #help-content {
                scroll-behavior: smooth;
            }

            /* ══════════════════════════════════════ */
            /* ── Magazine Landing Page ──            */
            /* ══════════════════════════════════════ */
            .help-magazine {
                padding: 1.5rem 2rem;
                max-width: 1400px;
                margin: 0 auto;
            }
            .help-mag-header {
                margin-bottom: 1.25rem;
                display: flex;
                align-items: baseline;
                gap: 1rem;
            }
            .help-mag-header h1 {
                font-size: 1.35rem;
                font-weight: 800;
                color: var(--text-primary, #e2e8f0);
                margin: 0;
                letter-spacing: -0.02em;
            }
            .help-mag-header p {
                font-size: 0.75rem;
                color: var(--text-muted, #64748b);
                margin: 0;
            }

            /* ── Masonry grid ── */
            .help-mag-grid {
                display: grid;
                grid-template-columns: repeat(4, 1fr);
                gap: 16px;
            }

            /* Size variants */
            .help-mag-card.mag-lg {
                grid-column: span 2;
                min-height: 220px;
            }
            .help-mag-card.mag-md {
                grid-column: span 1;
                min-height: 180px;
            }
            .help-mag-card.mag-sm {
                grid-column: span 1;
                min-height: 140px;
            }

            /* Base card */
            .help-mag-card {
                position: relative;
                border-radius: 14px;
                border: 1px solid rgba(255,255,255,0.06);
                background: rgba(255,255,255,0.025);
                backdrop-filter: blur(12px);
                -webkit-backdrop-filter: blur(12px);
                cursor: pointer;
                transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
                overflow: hidden;
                display: flex;
                flex-direction: column;
            }
            .help-mag-card:hover {
                border-color: var(--accent-glow, rgba(20,184,166,0.3));
                background: rgba(255,255,255,0.05);
                transform: translateY(-4px);
                box-shadow: 0 16px 48px rgba(0,0,0,0.35);
            }

            /* Card inner layout */
            .help-mag-card-inner {
                position: relative;
                z-index: 1;
                display: flex;
                flex-direction: column;
                flex: 1;
                padding: 1.25rem 1.375rem;
            }

            /* Top row: icon + badge */
            .help-mag-card-top {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 0.75rem;
            }
            .help-mag-card-top .material-symbols-outlined {
                font-size: 1.75rem;
                color: var(--accent, #14b8a6);
                opacity: 0.85;
            }
            .mag-lg .help-mag-card-top .material-symbols-outlined {
                font-size: 2.25rem;
            }
            .mag-badge {
                display: inline-flex;
                align-items: center;
                gap: 0.2rem;
                padding: 0.15rem 0.5rem;
                border-radius: 999px;
                font-size: 0.5rem;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 0.12em;
                border: 1px solid rgba(255,255,255,0.1);
                color: var(--text-muted, #64748b);
            }
            .mag-badge.featured {
                background: var(--accent, #14b8a6);
                border-color: transparent;
                color: #000;
            }

            /* Title + description */
            .help-mag-card h3 {
                font-size: 0.875rem;
                font-weight: 700;
                color: var(--text-primary, #e2e8f0);
                margin: 0 0 0.375rem 0;
                line-height: 1.35;
            }
            .mag-lg h3 {
                font-size: 1.0625rem;
            }
            .help-mag-card .mag-desc {
                font-size: 0.6875rem;
                color: var(--text-muted, #64748b);
                margin: 0;
                line-height: 1.65;
                flex: 1;
            }
            .mag-lg .mag-desc {
                font-size: 0.75rem;
            }

            /* Read more label — reveal on hover */
            .mag-read {
                display: inline-flex;
                align-items: center;
                gap: 0.3rem;
                font-size: 0.625rem;
                font-weight: 700;
                color: var(--accent, #14b8a6);
                margin-top: auto;
                padding-top: 0.75rem;
                opacity: 0;
                transform: translateY(4px);
                transition: all 0.25s ease;
            }
            .help-mag-card:hover .mag-read {
                opacity: 1;
                transform: translateY(0);
            }

            /* Section divider */
            .help-mag-section {
                grid-column: 1 / -1;
                font-size: 0.5625rem;
                font-weight: 900;
                text-transform: uppercase;
                letter-spacing: 0.2em;
                color: var(--text-muted, #64748b);
                display: flex;
                align-items: center;
                gap: 0.75rem;
                padding: 0.5rem 0 0;
            }
            .help-mag-section::after {
                content: '';
                flex: 1;
                height: 1px;
                background: rgba(255,255,255,0.06);
            }

            /* Back button */
            .help-back-btn {
                display: inline-flex;
                align-items: center;
                gap: 0.25rem;
                padding: 0.375rem 0.5rem;
                font-size: 0.6875rem;
                font-weight: 600;
                color: var(--text-muted, #64748b);
                background: transparent;
                border: none;
                cursor: pointer;
                transition: color 0.15s ease;
            }
            .help-back-btn:hover {
                color: var(--text-primary, #e2e8f0);
            }
        `;
        document.head.appendChild(style);
    }

    // ── Magazine Landing Page ────────────────────────────────
    function renderMagazine() {
        const welcomeEl = document.getElementById('help-welcome');
        const markdownEl = document.getElementById('help-markdown');
        const titleEl = document.getElementById('help-doc-title');

        if (markdownEl) markdownEl.classList.add('hidden');
        if (titleEl) titleEl.textContent = 'Knowledge Base';

        if (!welcomeEl) return;
        welcomeEl.classList.remove('hidden');

        console.log('[HELP] renderMagazine: catalog has', docCatalog.length, 'docs');

        let html = `<div class="help-magazine">`;

        // Header
        html += `<div class="help-mag-header">
            <h1>Knowledge Base</h1>
            <p>Everything you need to master TradeBot SCI Enterprise</p>
        </div>`;

        // Build masonry grid — all cards in one grid
        html += `<div class="help-mag-grid">`;

        docCatalog.forEach((doc, i) => {
            // Assign size: featured = large, certain important ones = medium, rest = small
            let sizeClass = 'mag-sm';
            if (doc.featured) {
                sizeClass = 'mag-lg';
            } else if (doc.size === 'md' || ['RTFM/06_PANIC_BUTTON.md', 'RTFM/05_COOKBOOK.md', 'RTFM/08_API_SETUP.md'].includes(doc.filename)) {
                sizeClass = 'mag-md';
            }

            const icon = doc.icon || 'article';
            const badgeLabel = doc.featured ? '⭐ Featured' : (doc.category === 'guide' ? 'Quick Start' : (doc.category === 'adr' ? 'ADR' : 'RTFM'));
            const badgeClass = doc.featured ? 'mag-badge featured' : 'mag-badge';

            html += `
                <div class="help-mag-card ${sizeClass}" data-filename="${doc.filename}">
                    <div class="help-mag-card-inner">
                        <div class="help-mag-card-top">
                            <span class="material-symbols-outlined">${icon}</span>
                            <span class="${badgeClass}">${badgeLabel}</span>
                        </div>
                        <h3>${doc.title}</h3>
                        <p class="mag-desc">${doc.description || ''}</p>
                        <div class="mag-read">Read article <span class="material-symbols-outlined" style="font-size: 13px;">arrow_forward</span></div>
                    </div>
                </div>`;
        });

        html += `</div></div>`;
        welcomeEl.innerHTML = html;

        // Attach click handlers
        welcomeEl.querySelectorAll('[data-filename]').forEach(card => {
            card.addEventListener('click', (e) => {
                console.log('[HELP] Card clicked:', card.dataset.filename);
                loadDoc(card.dataset.filename);
            });
        });
        console.log('[HELP] Attached click handlers to', welcomeEl.querySelectorAll('[data-filename]').length, 'cards');
    }

    // Show magazine (reset from article view)
    function showMagazine() {
        activeDoc = null;
        renderMagazine();

        const contentArea = document.getElementById('help-content');
        if (contentArea) contentArea.scrollTop = 0;

        const backBtn = document.getElementById('help-back-btn');
        if (backBtn) backBtn.classList.add('hidden');

        // Show search box on magazine landing
        const searchWrap = document.getElementById('help-search-wrap');
        if (searchWrap) searchWrap.style.display = '';
        // Clear search on return
        const searchInput = document.getElementById('help-search-input');
        if (searchInput) searchInput.value = '';
    }

    // ── Load a document ──────────────────────────────────────
    async function loadDoc(filename) {
        console.log('[HELP] loadDoc called with:', filename, 'API available:', !!window.api?.readHelpDoc);
        if (!window.api?.readHelpDoc) {
            console.warn('[HELP] readHelpDoc API not available!');
            return;
        }

        activeDoc = filename;

        const titleEl = document.getElementById('help-doc-title');
        const welcomeEl = document.getElementById('help-welcome');
        const markdownEl = document.getElementById('help-markdown');
        if (titleEl) titleEl.textContent = 'Loading...';

        // Show back button
        const backBtn = document.getElementById('help-back-btn');
        if (backBtn) backBtn.classList.remove('hidden');

        // Hide search box when viewing an article
        const searchWrap = document.getElementById('help-search-wrap');
        if (searchWrap) searchWrap.style.display = 'none';

        try {
            const result = await window.api.readHelpDoc(filename);
            if (!result.success) {
                if (titleEl) titleEl.textContent = 'Error';
                if (markdownEl) markdownEl.innerHTML = `<div class="help-p" style="color: #ef4444;">Failed to load: ${result.error}</div>`;
                return;
            }

            const { title, content } = result.data;
            if (titleEl) titleEl.textContent = title;
            if (welcomeEl) welcomeEl.classList.add('hidden');
            if (markdownEl) {
                markdownEl.classList.remove('hidden');
                markdownEl.innerHTML = renderMarkdown(content);
            }

            const contentArea = document.getElementById('help-content');
            if (contentArea) contentArea.scrollTop = 0;

        } catch (err) {
            console.error('[HELP] Error loading doc:', err);
            if (titleEl) titleEl.textContent = 'Error';
        }
    }

    // ── Scroll to top button ────────────────────────────────
    function setupScrollTop() {
        const btn = document.getElementById('help-scroll-top');
        const contentArea = document.getElementById('help-content');
        if (btn && contentArea) {
            btn.addEventListener('click', () => {
                contentArea.scrollTop = 0;
            });
        }
    }

    // ── Search filter ────────────────────────────────────────
    function setupHelpSearch() {
        const input = document.getElementById('help-search-input');
        if (!input) return;

        input.addEventListener('input', () => {
            const query = input.value.trim().toLowerCase();
            const cards = document.querySelectorAll('.help-mag-card');

            cards.forEach(card => {
                if (!query) {
                    // No query — show all cards
                    card.style.display = '';
                    card.style.opacity = '1';
                    return;
                }

                const filename = (card.dataset.filename || '').toLowerCase();
                // Find the matching catalog entry for richer matching
                const catEntry = docCatalog.find(d => d.filename === card.dataset.filename);
                const title = catEntry ? catEntry.title.toLowerCase() : '';
                const desc = catEntry ? (catEntry.description || '').toLowerCase() : '';

                const matches = title.includes(query) || desc.includes(query) || filename.includes(query);
                card.style.display = matches ? '' : 'none';
                card.style.opacity = matches ? '1' : '0';
            });
        });
    }

    // ── Init ─────────────────────────────────────────────────
    async function init() {
        if (initialized) return;
        initialized = true;

        injectStyles();

        // Load doc catalog
        if (window.api?.listHelpDocs) {
            try {
                const result = await window.api.listHelpDocs();
                if (result.success) {
                    docCatalog = result.data;
                }
            } catch (err) {
                console.error('[HELP] Failed to load catalog:', err);
            }
        }

        // Fallback catalog if IPC isn't available (for debugging)
        if (docCatalog.length === 0) {
            docCatalog = [
                { filename: 'HOW_TO_USE.md', title: 'First Time? Everything You Need to Launch Your First Trade', category: 'guide', icon: 'rocket_launch', description: 'The practical, no-fluff guide to getting the bot running and making trades.', featured: true },
                { filename: 'RTFM/01_PHILOSOPHY.md', title: 'Born From Late-Stage Capitalism: Why This Bot Exists', category: 'rtfm', icon: 'psychology', description: '"The economy is in shambles. The rent is too damn high."' },
                { filename: 'RTFM/02_SKELETON_ARCH.md', title: 'Inside the Machine: The Complete Skeletal Architecture', category: 'rtfm', icon: 'account_tree', description: '"It\'s alive! ...mostly." The anatomy of the application.' },
                { filename: 'RTFM/03_FUNCTIONS_DATA.md', title: 'Under the Hood: Every Function, Every Data Packet', category: 'rtfm', icon: 'data_object', description: '"The devil is in the details. And the bugs."' },
                { filename: 'RTFM/04_MAP_TOC.md', title: 'Lost in the Codebase? The Complete Navigation Map', category: 'rtfm', icon: 'map', description: '"Where is main.py again?"' },
                { filename: 'RTFM/05_COOKBOOK.md', title: 'Recipes for Traders: A Cookbook of Common Tasks', category: 'rtfm', icon: 'menu_book', description: '"Give a man a fish, he trades for a day."' },
                { filename: 'RTFM/06_PANIC_BUTTON.md', title: 'Something Is Wrong — The Emergency Panic Protocol', category: 'rtfm', icon: 'emergency', description: '"Something is wrong. Make it stop."' },
                { filename: 'RTFM/07_COCKPIT_CONTROLS.md', title: 'What Does This Button Do? The Complete Cockpit Guide', category: 'rtfm', icon: 'tune', description: '"What does this button do?" — Last words of a former trader.' },
                { filename: 'RTFM/08_API_SETUP.md', title: 'Connecting to the World: Every Broker, Every API Key', category: 'rtfm', icon: 'key', description: '"The bot is only as smart as its connection."' },
                { filename: 'RTFM/09_FEET_WET_STRATEGY.md', title: '20 Weapons of War: The Complete Strategy Arsenal', category: 'rtfm', icon: 'strategy', description: '"One strategy doesn\'t fit all markets."', featured: true },
                { filename: 'RTFM/14_READING_THE_SCOREBOARD.md', title: 'Am I Winning? How to Read Your Performance Metrics', category: 'rtfm', icon: 'monitoring', description: '"If you can\'t measure it, you can\'t improve it."' },
                { filename: 'RTFM/11_GHOST_IN_MACHINE.md', title: 'I Think, Therefore I Trade: The AI Decision Engine', category: 'rtfm', icon: 'smart_toy', description: '"I think, therefore I trade."' },
                { filename: 'RTFM/12_TIME_MACHINE.md', title: 'I Have to Go Back: The Trinity of Backtesting', category: 'rtfm', icon: 'history', description: '"I have to go back."' },
                { filename: 'RTFM/13_ENV_VARS.md', title: 'Every Toggle, Every Flag: The Environment Variable Bible', category: 'rtfm', icon: 'settings_applications', description: 'The complete env var reference.' },
                { filename: 'RTFM/31_SEASONED_TRADER.md', title: 'The Bot Is a 20-Year Seasoned Trader', category: 'rtfm', icon: 'military_tech', description: '"You spent 20 years learning to read price action. The bot learned it in 200 milliseconds."', featured: true },
                { filename: 'WHAT_S_PLUS_MEANS.md', title: 'What Does S+ Grade Mean For You?', category: 'guide', icon: 'workspace_premium', description: 'A plain-English guide for humans who trade, not humans who type-check.', featured: true, size: 'md' },
                { filename: 'adr/001-strategy-registry.md', title: 'ADR-001: The Strategy Registry', category: 'adr', icon: 'extension', description: '"Please Stop Adding Elif Branches."' },
                { filename: 'adr/002-safety-guard-architecture.md', title: 'ADR-002: Safety Guard Architecture', category: 'adr', icon: 'shield', description: '"The $52/Day Incident."', size: 'md' },
                { filename: 'adr/003-broker-abstraction.md', title: 'ADR-003: Broker Abstraction Layer', category: 'adr', icon: 'hub', description: '"Why We Don\'t Have if broker == OANDA Everywhere."' },
                { filename: 'adr/004-position-hold-lock.md', title: 'ADR-004: Position Hold Lock', category: 'adr', icon: 'lock', description: '"Stop Flipping Like a Pancake."', size: 'md' },
            ];
        }

        renderMagazine();
        setupScrollTop();
        setupHelpSearch();

        // Back button
        const backBtn = document.getElementById('help-back-btn');
        if (backBtn) {
            backBtn.addEventListener('click', () => showMagazine());
        }
    }

    return { init };
})();
