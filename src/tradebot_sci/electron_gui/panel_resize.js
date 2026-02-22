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

    function initResizeHandles() {
        const handles = document.querySelectorAll('.panel-resize-handle');
        const savedSizes = loadSavedSizes();

        // Restore saved panel heights
        Object.entries(savedSizes).forEach(([id, height]) => {
            const el = document.getElementById(id);
            if (el) {
                el.style.flex = 'none';
                el.style.height = height + 'px';
            }
        });

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

                // Switch from flex to fixed height during drag
                aboveEl.style.flex = 'none';
                belowEl.style.flex = 'none';
                aboveEl.style.height = startAboveH + 'px';
                belowEl.style.height = startBelowH + 'px';

                // Visual feedback
                handle.style.background = 'rgba(20, 184, 166, 0.15)';
                document.body.style.cursor = 'row-resize';
                document.body.style.userSelect = 'none';

                const onMove = (e2) => {
                    const dy = e2.clientY - startY;
                    const newAbove = Math.max(MIN_HEIGHT, startAboveH + dy);
                    const newBelow = Math.max(MIN_HEIGHT, startBelowH - dy);

                    // Only apply if both are above minimum
                    if (newAbove >= MIN_HEIGHT && newBelow >= MIN_HEIGHT) {
                        aboveEl.style.height = newAbove + 'px';
                        belowEl.style.height = newBelow + 'px';
                    }

                    // Trigger chart resize if the chart panel is being resized
                    if (aboveId === 'chart-panel' || belowId === 'chart-panel') {
                        if (typeof chart !== 'undefined' && chart && chart.resize) {
                            const chartArea = document.getElementById('chart-area');
                            if (chartArea) {
                                chart.resize(chartArea.clientWidth, chartArea.clientHeight);
                            }
                        }
                    }
                };

                const onUp = () => {
                    document.removeEventListener('mousemove', onMove);
                    document.removeEventListener('mouseup', onUp);
                    handle.style.background = '';
                    document.body.style.cursor = '';
                    document.body.style.userSelect = '';

                    // Save current sizes
                    const sizes = loadSavedSizes();
                    sizes[aboveId] = aboveEl.getBoundingClientRect().height;
                    sizes[belowId] = belowEl.getBoundingClientRect().height;
                    saveSizes(sizes);

                    // Final chart resize
                    if (aboveId === 'chart-panel' || belowId === 'chart-panel') {
                        if (typeof chart !== 'undefined' && chart && chart.resize) {
                            const chartArea = document.getElementById('chart-area');
                            if (chartArea) {
                                setTimeout(() => chart.resize(chartArea.clientWidth, chartArea.clientHeight), 50);
                            }
                        }
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
