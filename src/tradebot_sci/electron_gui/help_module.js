// ═══════════════════════════════════════════════════════════════
// HELP MODULE — Documentation viewer with markdown rendering
// ═══════════════════════════════════════════════════════════════
window.helpModule = (() => {
    let initialized = false;
    let docCatalog = [];
    let activeDoc = null;
    let helpSortOption = 'newbie';

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

            // Raw HTML passthrough (e.g. <table> dialogue boxes with avatars)
            if (trimmed.startsWith('<')) {
                flushTable(); flushList(); flushBlockquote();
                html += trimmed;
                continue;
            }

            // Standalone image line → full-width screenshot figure
            const soloImgMatch = trimmed.match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
            if (soloImgMatch) {
                const alt = soloImgMatch[1];
                const src = soloImgMatch[2];
                html += `<figure class="help-screenshot-figure"><img src="${src}" alt="${alt}" class="help-screenshot"><figcaption class="help-screenshot-caption">${alt}</figcaption></figure>`;
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

            /* ══════════════════════════════════════════════ */
            /* ── Magazine-Style Article Layout ──             */
            /* ══════════════════════════════════════════════ */

            /* ── Article Container ── */
            #help-markdown {
                position: relative;
                max-width: 800px;
                margin: 0 auto;
                padding: 0 2rem 3rem 2rem;
            }
            #help-markdown::before {
                content: '';
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                height: 4px;
                background: linear-gradient(90deg, #14b8a6 0%, #0ea5e9 50%, #8b5cf6 100%);
                border-radius: 2px;
            }

            /* ── Chapter Title (H1) ── */
            .help-h1 {
                font-size: 2.5rem;
                font-weight: 900;
                color: #f1f5f9;
                margin: 2rem 0 1.5rem 0;
                padding-bottom: 1rem;
                line-height: 1.2;
                letter-spacing: -0.02em;
                border-bottom: none;
                position: relative;
                text-shadow: 0 2px 12px rgba(20,184,166,0.15);
            }
            .help-h1::after {
                content: '';
                display: block;
                width: 80px;
                height: 4px;
                background: linear-gradient(90deg, #14b8a6, #0ea5e9);
                border-radius: 2px;
                margin-top: 0.75rem;
            }

            /* ── Section Header (H2) ── */
            .help-h2 {
                font-size: 1.5rem;
                font-weight: 800;
                color: var(--text-primary, #e2e8f0);
                margin: 3rem 0 1rem 0;
                padding: 0.75rem 0 0.75rem 1.25rem;
                line-height: 1.3;
                letter-spacing: -0.01em;
                border-left: 4px solid #14b8a6;
                background: linear-gradient(90deg, rgba(20,184,166,0.08) 0%, transparent 70%);
                border-radius: 0 0.5rem 0.5rem 0;
                position: relative;
            }
            .help-h2::before {
                content: '◆';
                position: absolute;
                left: -0.7rem;
                top: 50%;
                transform: translateY(-50%);
                color: #14b8a6;
                font-size: 0.625rem;
                background: var(--bg-primary, #0f172a);
                padding: 2px 0;
            }

            /* ── Subsection Header (H3) ── */
            .help-h3 {
                font-size: 1.25rem;
                font-weight: 700;
                color: var(--accent, #14b8a6);
                margin: 2rem 0 0.75rem 0;
                padding-bottom: 0.5rem;
                line-height: 1.3;
                border-bottom: 1px solid rgba(20,184,166,0.15);
                font-style: italic;
            }

            /* ── Minor Headers ── */
            .help-h4, .help-h5, .help-h6 {
                font-size: 1.1rem;
                font-weight: 700;
                color: var(--text-primary, #e2e8f0);
                margin: 1.5rem 0 0.5rem 0;
                line-height: 1.3;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                font-size: 0.9rem;
            }

            /* ── Body Paragraphs ── */
            .help-p {
                font-size: 1.05rem;
                line-height: 1.85;
                color: var(--text-secondary, #94a3b8);
                margin: 0.75rem 0;
                max-width: 70ch;
            }
            .help-p strong {
                color: var(--text-primary, #e2e8f0);
                font-weight: 700;
            }
            .help-p em {
                color: var(--text-primary, #e2e8f0);
                font-style: italic;
            }

            /* ── Drop Cap — first paragraph after H1 ── */
            .help-h1 + .help-p::first-letter {
                font-size: 3.5em;
                font-weight: 900;
                float: left;
                line-height: 0.85;
                margin: 0.05em 0.12em 0 0;
                color: #14b8a6;
                text-shadow: 0 2px 8px rgba(20,184,166,0.3);
            }

            /* ── Links ── */
            .help-link {
                color: var(--accent, #14b8a6);
                text-decoration: none;
                font-weight: 600;
                border-bottom: 1px solid rgba(20,184,166,0.3);
                transition: all 0.2s ease;
            }
            .help-link:hover {
                border-bottom-color: #14b8a6;
                text-shadow: 0 0 8px rgba(20,184,166,0.3);
            }

            /* ── Inline Code ── */
            .help-inline-code {
                background: rgba(20,184,166,0.08);
                border: 1px solid rgba(20,184,166,0.15);
                border-radius: 4px;
                padding: 0.15rem 0.4rem;
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 0.85em;
                color: var(--accent, #14b8a6);
            }

            /* ── Code Blocks ── */
            .help-code-block {
                position: relative;
                margin: 1.25rem 0;
                border-radius: 0.75rem;
                overflow: hidden;
                border: 1px solid rgba(255,255,255,0.08);
                background: rgba(0,0,0,0.45);
                backdrop-filter: blur(8px);
            }
            .help-code-lang {
                position: absolute;
                top: 0;
                right: 0;
                padding: 0.3rem 0.75rem;
                font-size: 0.625rem;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.1em;
                color: var(--accent, #14b8a6);
                background: rgba(20,184,166,0.1);
                border-bottom-left-radius: 0.5rem;
            }
            .help-code-block pre {
                margin: 0;
                padding: 1.25rem 1.5rem;
                overflow-x: auto;
            }
            .help-code-block code {
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 0.9rem;
                line-height: 1.7;
                color: var(--text-primary, #e2e8f0);
            }

            /* ── Data Tables ── */
            .help-table-wrap {
                overflow-x: auto;
                margin: 1.25rem 0;
                border-radius: 0.75rem;
                border: 1px solid rgba(255,255,255,0.08);
                background: rgba(0,0,0,0.15);
            }
            .help-table {
                width: 100%;
                border-collapse: collapse;
                font-size: 1.0rem;
            }
            .help-table th {
                text-align: left;
                padding: 0.75rem 1rem;
                font-weight: 700;
                font-size: 0.8rem;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                color: var(--accent, #14b8a6);
                background: rgba(20,184,166,0.06);
                border-bottom: 2px solid rgba(20,184,166,0.15);
            }
            .help-table td {
                padding: 0.625rem 1rem;
                color: var(--text-secondary, #94a3b8);
                border-bottom: 1px solid rgba(255,255,255,0.04);
                line-height: 1.6;
            }
            .help-table td strong {
                color: var(--text-primary, #e2e8f0);
            }
            .help-table tr:hover td {
                background: rgba(20,184,166,0.03);
            }
            .help-table tr:last-child td {
                border-bottom: none;
            }

            /* ── Blockquotes → Pull Quotes ── */
            .help-blockquote {
                position: relative;
                border-left: none;
                border: 1px solid rgba(255,255,255,0.06);
                padding: 1.5rem 1.75rem 1.25rem 2.5rem;
                margin: 1.5rem 1rem;
                color: var(--text-secondary, #94a3b8);
                font-size: 1.1rem;
                font-style: italic;
                line-height: 1.8;
                background: rgba(0,0,0,0.2);
                border-radius: 0.75rem;
                backdrop-filter: blur(4px);
            }
            .help-blockquote::before {
                content: '"';
                position: absolute;
                top: -0.1rem;
                left: 0.75rem;
                font-size: 3.5rem;
                font-weight: 900;
                color: rgba(20,184,166,0.25);
                font-family: Georgia, serif;
                line-height: 1;
            }
            .help-blockquote strong {
                color: var(--text-primary, #e2e8f0);
            }

            /* ── GitHub-style Alert Callouts ── */
            .help-alert {
                border-left: 4px solid;
                padding: 1rem 1.25rem;
                margin: 1.5rem 0;
                border-radius: 0 0.75rem 0.75rem 0;
                background: rgba(0,0,0,0.2);
                backdrop-filter: blur(4px);
            }
            .help-alert-header {
                display: flex;
                align-items: center;
                gap: 0.5rem;
                font-size: 0.85rem;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                margin-bottom: 0.5rem;
            }
            .help-alert-body {
                font-size: 1.0rem;
                line-height: 1.7;
                color: var(--text-secondary, #94a3b8);
            }
            .help-alert-body strong {
                color: var(--text-primary, #e2e8f0);
            }

            /* ── Lists → Premium Styled ── */
            .help-list {
                margin: 1rem 0;
                padding-left: 0;
                font-size: 1.05rem;
                line-height: 1.85;
                color: var(--text-secondary, #94a3b8);
                list-style: none;
            }
            .help-list li {
                margin: 0.5rem 0;
                padding-left: 1.75rem;
                position: relative;
            }
            .help-list li strong {
                color: var(--text-primary, #e2e8f0);
            }
            .help-list li code {
                background: rgba(20,184,166,0.08);
                border: 1px solid rgba(20,184,166,0.15);
                border-radius: 4px;
                padding: 0.125rem 0.375rem;
                font-family: 'JetBrains Mono', 'Fira Code', monospace;
                font-size: 0.85em;
                color: var(--accent, #14b8a6);
            }
            /* Unordered: accent diamond bullets */
            ul.help-list li::before {
                content: '◆';
                position: absolute;
                left: 0;
                color: #14b8a6;
                font-size: 0.5rem;
                top: 0.6em;
            }
            /* Ordered: accent numbered circles */
            ol.help-list {
                counter-reset: ol-counter;
            }
            ol.help-list li {
                counter-increment: ol-counter;
                padding-left: 2.5rem;
            }
            ol.help-list li::before {
                content: counter(ol-counter);
                position: absolute;
                left: 0;
                top: 0.1em;
                width: 1.6rem;
                height: 1.6rem;
                border-radius: 50%;
                background: rgba(20,184,166,0.12);
                border: 1px solid rgba(20,184,166,0.25);
                color: #14b8a6;
                font-weight: 700;
                font-size: 0.8rem;
                display: flex;
                align-items: center;
                justify-content: center;
                line-height: 1;
            }

            /* ── Horizontal Rule → Decorative Divider ── */
            .help-hr {
                border: none;
                height: 1px;
                background: linear-gradient(90deg, transparent 0%, rgba(20,184,166,0.3) 20%, rgba(20,184,166,0.3) 80%, transparent 100%);
                margin: 2.5rem auto;
                max-width: 60%;
                position: relative;
            }
            .help-hr::after {
                content: '◆';
                position: absolute;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                font-size: 0.5rem;
                color: #14b8a6;
                background: var(--bg-primary, #0f172a);
                padding: 0 0.75rem;
            }

            /* ── Images (standalone inline) ── */
            .help-img {
                max-width: 100%;
                border-radius: 0.75rem;
                margin: 0.75rem 0;
                border: 1px solid rgba(255,255,255,0.06);
            }
            .help-p .help-img {
                display: inline-block;
                width: 160px;
                height: 160px;
                border-radius: 50%;
                margin: 0.5rem 0.75rem 0.5rem 0;
                border: 3px solid rgba(20,184,166,0.3);
                object-fit: cover;
                vertical-align: middle;
            }

            /* ── Full-width Screenshots ── */
            .help-screenshot-figure {
                margin: 1.5rem 0;
                padding: 0;
                text-align: center;
            }
            .help-screenshot {
                width: 100%;
                max-width: 100%;
                height: auto;
                border-radius: 0.75rem;
                border: 1px solid rgba(20,184,166,0.2);
                box-shadow: 0 4px 24px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.04);
                display: block;
                margin: 0 auto;
            }
            .help-screenshot-caption {
                margin-top: 0.5rem;
                font-size: 0.8rem;
                font-style: italic;
                color: var(--text-muted, #64748b);
                letter-spacing: 0.01em;
            }

            /* ══════════════════════════════════════════ */
            /* ── Character Dialogue — Chat Bubbles ──   */
            /* ══════════════════════════════════════════ */

            /* Dialogue table container */
            #help-markdown table:not(.help-table) {
                width: 100%;
                border-collapse: collapse;
                margin: 1rem 0;
                background: transparent;
                border-radius: 0;
                overflow: visible;
                border: none;
            }
            #help-markdown table:not(.help-table) tr {
                display: flex;
                align-items: flex-start;
                gap: 0;
                margin-bottom: 0.25rem;
            }
            /* Avatar cell */
            #help-markdown table:not(.help-table) td:first-child {
                padding: 0;
                vertical-align: top;
                width: 120px;
                min-width: 120px;
                flex-shrink: 0;
            }
            /* Transparent avatar — character floats */
            #help-markdown table:not(.help-table) img {
                display: block;
                width: 110px;
                height: 110px;
                margin: 0 auto;
                object-fit: contain;
                image-rendering: -webkit-optimize-contrast;
                -webkit-backface-visibility: hidden;
                transform: translateZ(0) scale(1);
                transition: transform 0.3s ease, filter 0.3s ease;
                cursor: pointer;
                filter: drop-shadow(0 3px 10px rgba(0,0,0,0.5));
            }
            #help-markdown table:not(.help-table) img:hover {
                transform: translateZ(0) scale(1.25);
                filter: drop-shadow(0 4px 16px rgba(20,184,166,0.3)) drop-shadow(0 8px 24px rgba(0,0,0,0.5));
                z-index: 10;
                position: relative;
            }
            /* Speech bubble cell */
            #help-markdown table:not(.help-table) td:last-child {
                padding: 0.75rem 1.25rem;
                color: var(--text-secondary, #94a3b8);
                font-size: 1.0rem;
                line-height: 1.7;
                background: rgba(255,255,255,0.03);
                border: 1px solid rgba(255,255,255,0.06);
                border-radius: 0 1rem 1rem 1rem;
                position: relative;
                flex: 1;
                margin-top: 0.5rem;
                backdrop-filter: blur(4px);
            }
            /* Speech bubble arrow */
            #help-markdown table:not(.help-table) td:last-child::before {
                content: '';
                position: absolute;
                left: -8px;
                top: 14px;
                width: 0;
                height: 0;
                border-top: 6px solid transparent;
                border-bottom: 6px solid transparent;
                border-right: 8px solid rgba(255,255,255,0.06);
            }
            /* Character name — accent badge */
            #help-markdown table:not(.help-table) b {
                display: inline-block;
                color: #14b8a6;
                font-weight: 800;
                font-size: 0.75rem;
                text-transform: uppercase;
                letter-spacing: 0.06em;
                background: rgba(20,184,166,0.1);
                padding: 0.15rem 0.5rem;
                border-radius: 4px;
                margin-bottom: 0.25rem;
            }
            /* Dialogue text emphases */
            #help-markdown table:not(.help-table) em {
                color: var(--text-primary, #e2e8f0);
                font-style: italic;
            }

            /* ── Search highlight ── */
            .help-search-highlight {
                background: var(--accent-dim, rgba(20,184,166,0.3));
                color: var(--accent, #14b8a6);
                padding: 0.05rem 0.2rem;
                border-radius: 2px;
                font-weight: 700;
            }

            /* scrolling handled by JS kinetic scroll */
            #help-content {
                scroll-behavior: auto;
            }
            #help-content::-webkit-scrollbar {
                width: 10px;
            }
            #help-content::-webkit-scrollbar-thumb {
                background: rgba(255,255,255,0.15);
                border-radius: 5px;
            }
            #help-content::-webkit-scrollbar-thumb:hover {
                background: rgba(255,255,255,0.3);
            }
            #help-content::-webkit-scrollbar-track {
                background: rgba(0,0,0,0.1);
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

            /* NEW badge for unread articles */
            .mag-badge-new {
                position: absolute;
                top: 10px;
                right: 10px;
                display: inline-flex;
                align-items: center;
                gap: 0.25rem;
                padding: 0.2rem 0.6rem;
                border-radius: 999px;
                font-size: 0.6rem;
                font-weight: 900;
                text-transform: uppercase;
                letter-spacing: 0.15em;
                background: linear-gradient(135deg, #f59e0b, #ef4444);
                color: #fff;
                box-shadow: 0 2px 8px rgba(245, 158, 11, 0.4);
                z-index: 5;
                animation: newBadgePulse 2s ease-in-out infinite;
            }
            @keyframes newBadgePulse {
                0%, 100% { transform: scale(1); box-shadow: 0 2px 8px rgba(245, 158, 11, 0.4); }
                50% { transform: scale(1.08); box-shadow: 0 3px 12px rgba(245, 158, 11, 0.6); }
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
        html += `<div class="help-mag-header" style="justify-content: space-between; align-items: flex-end;">
            <div>
                <h1>Knowledge Base</h1>
                <p>Everything you need to master TradeBot SCI Enterprise</p>
            </div>
            <div class="help-sort-control" style="display: flex; gap: 8px; align-items: center;">
                <label style="font-size: 0.7rem; color: var(--text-muted); font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em;">Sort By:</label>
                <select id="help-sort-select" style="background: var(--bg-primary, #0f172a); border: 1px solid var(--border-color, rgba(255,255,255,0.1)); color: var(--text-primary); padding: 6px 12px; border-radius: 6px; font-size: 0.8rem; cursor: pointer; outline: none;">
                    <option style="background: var(--bg-primary, #0f172a); color: var(--text-primary, #e2e8f0);" value="newbie" ${helpSortOption === 'newbie' ? 'selected' : ''}>Newbie (By Order)</option>
                    <option style="background: var(--bg-primary, #0f172a); color: var(--text-primary, #e2e8f0);" value="newest" ${helpSortOption === 'newest' ? 'selected' : ''}>Newest First</option>
                    <option style="background: var(--bg-primary, #0f172a); color: var(--text-primary, #e2e8f0);" value="oldest" ${helpSortOption === 'oldest' ? 'selected' : ''}>Oldest First</option>
                    <option style="background: var(--bg-primary, #0f172a); color: var(--text-primary, #e2e8f0);" value="featured" ${helpSortOption === 'featured' ? 'selected' : ''}>Featured First</option>
                </select>
            </div>
        </div>`;

        // Build masonry grid — all cards in one grid
        html += `<div class="help-mag-grid">`;

        // Read tracking via localStorage
        const readKey = 'tradebot-help-read-docs';
        let readDocs = [];
        try { readDocs = JSON.parse(localStorage.getItem(readKey) || '[]'); } catch (e) { readDocs = []; }

        // Sort: based on user selection
        const sortedCatalog = [...docCatalog].sort((a, b) => {
            const aUnread = !readDocs.includes(a.filename) ? 1 : 0;
            const bUnread = !readDocs.includes(b.filename) ? 1 : 0;

            const aName = a.filename || '';
            const bName = b.filename || '';

            if (helpSortOption === 'newbie') {
                const aIsAdr = a.category === 'adr' || aName.toLowerCase().includes('adr');
                const bIsAdr = b.category === 'adr' || bName.toLowerCase().includes('adr');
                if (aIsAdr !== bIsAdr) return aIsAdr ? 1 : -1;
                return aName.localeCompare(bName);
            } else if (helpSortOption === 'newest') {
                if (aUnread !== bUnread) return bUnread - aUnread; // Float unread to top
                return bName.localeCompare(aName);
            } else if (helpSortOption === 'oldest') {
                return aName.localeCompare(bName);
            } else if (helpSortOption === 'featured') {
                if (a.featured && !b.featured) return -1;
                if (!a.featured && b.featured) return 1;
                if (aUnread !== bUnread) return bUnread - aUnread;
                return bName.localeCompare(aName);
            }
            return 0;
        });

        sortedCatalog.forEach((doc, i) => {
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
            const isUnread = !readDocs.includes(doc.filename);

            html += `
                <div class="help-mag-card ${sizeClass}" data-filename="${doc.filename}">
                    ${isUnread ? '<span class="mag-badge-new">✨ NEW</span>' : ''}
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

        // Attach sorting handler
        const sortSelect = document.getElementById('help-sort-select');
        if (sortSelect) {
            sortSelect.addEventListener('change', (e) => {
                helpSortOption = e.target.value;
                renderMagazine(); // Re-render to apply sort
            });
        }

        // Attach click handlers + mark as read
        welcomeEl.querySelectorAll('[data-filename]').forEach(card => {
            card.addEventListener('click', (e) => {
                const fn = card.dataset.filename;
                console.log('[HELP] Card clicked:', fn);

                // Mark as read in localStorage
                if (!readDocs.includes(fn)) {
                    readDocs.push(fn);
                    localStorage.setItem(readKey, JSON.stringify(readDocs));
                    // Remove the NEW badge immediately
                    const badge = card.querySelector('.mag-badge-new');
                    if (badge) badge.remove();
                }

                loadDoc(fn);
            });
        });
        console.log('[HELP] Attached click handlers to', welcomeEl.querySelectorAll('[data-filename]').length, 'cards');
    }

    // Show magazine (reset from article view)
    function showMagazine() {
        activeDoc = null;
        renderMagazine();

        const contentArea = document.getElementById('help-content');
        if (contentArea) {
            setTimeout(() => {
                contentArea.scrollTo({ top: 0, behavior: 'smooth' });
            }, 100);
        }

        const backBtn = document.getElementById('help-back-btn');
        if (backBtn) backBtn.classList.add('hidden');

        const nextBtn = document.getElementById('help-next-btn');
        if (nextBtn) nextBtn.classList.add('hidden');

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

        // Show next button and determine if it should be enabled
        const nextBtn = document.getElementById('help-next-btn');
        if (nextBtn) {
            const sortedCatalog = [...docCatalog].sort((a, b) => {
                const aName = a.filename || '';
                const bName = b.filename || '';
                const aIsAdr = a.category === 'adr' || aName.toLowerCase().includes('adr');
                const bIsAdr = b.category === 'adr' || bName.toLowerCase().includes('adr');
                if (aIsAdr !== bIsAdr) return aIsAdr ? 1 : -1;
                return aName.localeCompare(bName);
            });
            const currentIndex = sortedCatalog.findIndex(d => d.filename === filename);
            if (currentIndex >= 0 && currentIndex < sortedCatalog.length - 1) {
                nextBtn.classList.remove('hidden');
                nextBtn.dataset.nextFilename = sortedCatalog[currentIndex + 1].filename;
            } else {
                nextBtn.classList.add('hidden');
            }
        }

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
            if (contentArea) {
                setTimeout(() => {
                    contentArea.scrollTo({ top: 0, behavior: 'smooth' });
                }, 100);
            }

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
                contentArea.scrollTo({ top: 0, behavior: 'smooth' });
            });
        }
    }

    // ── Smooth Scrolling (target-based lerp) ──────────────────
    // Each wheel tick pushes a target further; an animation loop
    // eases the actual scroll position toward the target so
    // multiple ticks blend into one fluid, decelerating glide.
    function setupKineticScroll() {
        const el = document.getElementById('help-content');
        if (!el) return;

        // Force instant scrollTop so our lerp loop works
        el.style.scrollBehavior = 'auto';

        let target = el.scrollTop;
        let running = false;
        const speed = 400;   // pixels per wheel notch (generous throw)
        const ease = 0.04;  // lerp factor (lower = longer rolling stop)

        el.addEventListener('wheel', (e) => {
            e.preventDefault();

            // Normalize delta
            let d = e.deltaY;
            if (e.deltaMode === 1) d *= 20;            // line mode
            else if (e.deltaMode === 2) d *= el.clientHeight;  // page mode

            // Push the target (direction only, fixed step size for consistency)
            target += Math.sign(d) * speed;

            // Clamp to scrollable range
            const max = el.scrollHeight - el.clientHeight;
            target = Math.max(0, Math.min(target, max));

            if (!running) { running = true; step(); }
        }, { passive: false });

        // Sync target when user drags the scrollbar manually
        let wheelActive = false;
        el.addEventListener('wheel', () => { wheelActive = true; }, { passive: true });
        el.addEventListener('scroll', () => {
            if (!wheelActive && !running) {
                target = el.scrollTop;
            }
            wheelActive = false;
        });

        function step() {
            const diff = target - el.scrollTop;
            if (Math.abs(diff) < 1) {
                el.scrollTop = target;
                running = false;
                return;
            }
            el.scrollTop += diff * ease;
            requestAnimationFrame(step);
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
            console.error('[HELP] IPC listHelpDocs failed or returned empty. Make sure the backend is running to parse frontmatter from markdown files.');
        }

        renderMagazine();
        setupScrollTop();
        setupKineticScroll();
        setupHelpSearch();

        // Back button
        const backBtn = document.getElementById('help-back-btn');
        if (backBtn) {
            backBtn.addEventListener('click', () => showMagazine());
        }

        // Next button
        const nextBtn = document.getElementById('help-next-btn');
        if (nextBtn) {
            nextBtn.addEventListener('click', () => {
                if (nextBtn.dataset.nextFilename) {
                    loadDoc(nextBtn.dataset.nextFilename);
                }
            });
        }
    }

    return { init };
})();
