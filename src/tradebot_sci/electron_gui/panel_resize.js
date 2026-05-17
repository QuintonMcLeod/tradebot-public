/**
 * panel_resize.js — Drag-to-resize logic for vertically stacked panels.
 *
 * Each .panel-resize-handle element has data-above and data-below attributes
 * pointing to the panel IDs above and below it. Dragging the handle resizes
 * both panels, and the preferred sizes are saved to localStorage.
 *
 * Chart resizing is handled automatically by LightweightCharts' autoSize
 * option + overflow:hidden on chart-area.
 */
(function () {
    'use strict';

    const STORAGE_KEY = 'panelResizeSizes';
    const MIN_HEIGHT = 80; // px — smallest any panel can shrink to

    function loadSavedSizes() {
        try {
            return JSON.parse(localStorage.getItem(STORAGE_KEY)) || {};
        } catch { return {}; }
    }

    function saveSizes(sizes) {
        try { localStorage.setItem(STORAGE_KEY, JSON.stringify(sizes)); } catch { }
    }

    /**
     * Force a panel to a specific pixel height, overriding any Tailwind
     * flex classes (flex-[3], flex-1, etc.) that would otherwise win.
     */
    function forceHeight(el, h) {
        el.style.setProperty('flex', '0 0 ' + h + 'px', 'important');
        el.style.setProperty('height', h + 'px', 'important');
        el.style.setProperty('max-height', h + 'px', 'important');
        el.style.setProperty('min-height', MIN_HEIGHT + 'px', 'important');
        el.style.setProperty('overflow', 'hidden');
    }

    function initResizeHandles() {
        const handles = document.querySelectorAll('.panel-resize-handle');
        const savedSizes = loadSavedSizes();

        // Restore saved panel heights
        Object.entries(savedSizes).forEach(([id, height]) => {
            const el = document.getElementById(id);
            if (el && height > MIN_HEIGHT) {
                forceHeight(el, height);
            }
        });

        handles.forEach(handle => {
            const aboveId = handle.dataset.above;
            const belowId = handle.dataset.below;
            if (!aboveId) return;

            handle.addEventListener('mousedown', (e) => {
                e.preventDefault();
                const aboveEl = document.getElementById(aboveId);
                const belowEl = belowId ? document.getElementById(belowId) : null;
                if (!aboveEl) return;

                const startY = e.clientY;
                const startAboveH = aboveEl.getBoundingClientRect().height;
                const startBelowH = belowEl ? belowEl.getBoundingClientRect().height : 0;

                // Lock both panels to their current pixel sizes
                forceHeight(aboveEl, startAboveH);
                if (belowEl) forceHeight(belowEl, startBelowH);

                // Visual feedback
                const dot = handle.querySelector('div');
                if (dot) dot.style.background = 'rgba(20, 184, 166, 0.6)';
                document.body.style.cursor = 'row-resize';
                document.body.style.userSelect = 'none';
                document.body.style.webkitUserSelect = 'none';

                const onMove = (e2) => {
                    const dy = e2.clientY - startY;
                    const newAbove = Math.max(MIN_HEIGHT, startAboveH + dy);

                    if (belowEl) {
                        const newBelow = Math.max(MIN_HEIGHT, startBelowH - dy);
                        // Enforce total conservation
                        const total = startAboveH + startBelowH;
                        if (newAbove + newBelow > total + 2) return;
                        forceHeight(belowEl, newBelow);
                    }

                    forceHeight(aboveEl, newAbove);
                };

                const onUp = () => {
                    document.removeEventListener('mousemove', onMove);
                    document.removeEventListener('mouseup', onUp);
                    const dot2 = handle.querySelector('div');
                    if (dot2) dot2.style.background = '';
                    document.body.style.cursor = '';
                    document.body.style.userSelect = '';
                    document.body.style.webkitUserSelect = '';

                    // Save current sizes
                    const sizes = loadSavedSizes();
                    sizes[aboveId] = Math.round(aboveEl.getBoundingClientRect().height);
                    if (belowEl) sizes[belowId] = Math.round(belowEl.getBoundingClientRect().height);
                    saveSizes(sizes);
                };

                document.addEventListener('mousemove', onMove);
                document.addEventListener('mouseup', onUp);
            });
        });
    }

    window.resetPanelLayout = function () {
        localStorage.removeItem(STORAGE_KEY);
        localStorage.removeItem('tradebot_panel_heights');
        ['chart-panel', 'decisions-panel', 'log-panel'].forEach(id => {
            const el = document.getElementById(id);
            if (!el) return;
            el.style.flex = '';
            el.style.height = '';
            el.style.maxHeight = '';
            el.style.minHeight = '';
            el.style.overflow = '';
        });
        setTimeout(() => {
            if (window.chart) {
                const container = document.getElementById('chart-area');
                if (container) window.chart.applyOptions({ width: container.clientWidth, height: container.clientHeight });
            }
        }, 100);
        console.log('[UI] Panel layout reset to defaults');
    };

    // Initialize after DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initResizeHandles);
    } else {
        initResizeHandles();
    }
})();
