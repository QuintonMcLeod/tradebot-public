/**
 * panel_resize.js — Drag-to-resize logic for vertically stacked panels.
 *
 * Each .panel-resize-handle element has data-above and data-below attributes
 * pointing to the panel IDs above and below it. Dragging the handle resizes
 * both panels, and the preferred sizes are saved to localStorage.
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

    /**
     * Resize the LightweightCharts canvas to match its container.
     * Uses requestAnimationFrame to ensure the DOM has reflowed first.
     */
    let _rafId = null;
    function triggerChartResize() {
        if (_rafId) cancelAnimationFrame(_rafId);
        _rafId = requestAnimationFrame(() => {
            _rafId = null;
            if (typeof chart !== 'undefined' && chart) {
                const chartArea = document.getElementById('chart-area');
                if (chartArea) {
                    const w = chartArea.clientWidth;
                    const h = chartArea.clientHeight;
                    if (w > 0 && h > 0) {
                        chart.applyOptions({ width: w, height: h });
                    }
                }
            }
        });
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

        // Delayed chart resize after restoring saved sizes
        setTimeout(triggerChartResize, 300);

        handles.forEach(handle => {
            const aboveId = handle.dataset.above;
            const belowId = handle.dataset.below;
            if (!aboveId || !belowId) return;

            handle.addEventListener('mousedown', (e) => {
                e.preventDefault();
                const aboveEl = document.getElementById(aboveId);
                const belowEl = document.getElementById(belowId);
                if (!aboveEl || !belowEl) return;

                const startY = e.clientY;
                const startAboveH = aboveEl.getBoundingClientRect().height;
                const startBelowH = belowEl.getBoundingClientRect().height;

                // Lock both panels to their current pixel sizes
                forceHeight(aboveEl, startAboveH);
                forceHeight(belowEl, startBelowH);

                // Visual feedback
                const dot = handle.querySelector('div');
                if (dot) dot.style.background = 'rgba(20, 184, 166, 0.6)';
                document.body.style.cursor = 'row-resize';
                document.body.style.userSelect = 'none';
                document.body.style.webkitUserSelect = 'none';

                const onMove = (e2) => {
                    const dy = e2.clientY - startY;
                    const newAbove = Math.max(MIN_HEIGHT, startAboveH + dy);
                    const newBelow = Math.max(MIN_HEIGHT, startBelowH - dy);

                    // Enforce total conservation
                    const total = startAboveH + startBelowH;
                    if (newAbove + newBelow > total + 2) return;

                    forceHeight(aboveEl, newAbove);
                    forceHeight(belowEl, newBelow);

                    // Live chart resize on every frame
                    if (aboveId === 'chart-panel' || belowId === 'chart-panel') {
                        triggerChartResize();
                    }
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
                    sizes[belowId] = Math.round(belowEl.getBoundingClientRect().height);
                    saveSizes(sizes);

                    // Final chart resize (double-tap to be safe)
                    if (aboveId === 'chart-panel' || belowId === 'chart-panel') {
                        triggerChartResize();
                        setTimeout(triggerChartResize, 100);
                    }
                };

                document.addEventListener('mousemove', onMove);
                document.addEventListener('mouseup', onUp);
            });
        });
    }

    // Initialize after DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initResizeHandles);
    } else {
        initResizeHandles();
    }
})();
