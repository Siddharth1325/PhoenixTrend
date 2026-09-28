/* ================================================================
   PHOENIXTREND — TERMINAL RUNTIME
   Progressive UI enhancement only. Trading/business logic remains
   in Blazor + backend APIs. This file never invents trading data.
   ================================================================ */
(function () {
    "use strict";

    const VERSION = "1.0.0";
    const PAGE_ROOTS = [
        ".trade-layout",
        ".portfolio-layout",
        ".risk-layout",
        ".ai-layout",
        ".activity-layout",
        ".analytics-layout",
        ".settings-layout"
    ];

    const state = {
        initialized: false,
        observer: null,
        resizeObserver: null,
        scrollButton: null,
        cleanup: [],
        tableWrappers: new WeakMap(),
        lastFocused: null,
        mutationQueued: false
    };

    function all(selector, root) {
        return Array.from((root || document).querySelectorAll(selector));
    }

    function one(selector, root) {
        return (root || document).querySelector(selector);
    }

    function isElement(value) {
        return value instanceof Element;
    }

    function isVisible(element) {
        if (!isElement(element)) {
            return false;
        }

        const style = window.getComputedStyle(element);

        return style.display !== "none" &&
            style.visibility !== "hidden" &&
            element.getClientRects().length > 0;
    }

    function pageIsSupported() {
        return PAGE_ROOTS.some(function (selector) {
            return Boolean(one(selector));
        });
    }

    function safeCall(callback) {
        try {
            return callback();
        } catch (error) {
            console.error("[PhoenixTrend terminal runtime]", error);
            return undefined;
        }
    }

    function listen(target, eventName, handler, options) {
        if (!target || !target.addEventListener) {
            return function () {};
        }

        target.addEventListener(eventName, handler, options);

        const cleanup = function () {
            target.removeEventListener(eventName, handler, options);
        };

        state.cleanup.push(cleanup);
        return cleanup;
    }

    function normalizeText(value) {
        return String(value || "")
            .replace(/\s+/g, " ")
            .trim();
    }

    function setAttributeIfMissing(element, name, value) {
        if (!isElement(element)) {
            return;
        }

        if (!element.hasAttribute(name)) {
            element.setAttribute(name, value);
        }
    }

    function enhanceButtons(root) {
        all("button", root).forEach(function (button) {
            setAttributeIfMissing(button, "type", "button");

            if (!button.hasAttribute("aria-label")) {
                const label = normalizeText(button.textContent);

                if (label) {
                    button.setAttribute("aria-label", label);
                }
            }

            if (button.disabled) {
                button.setAttribute("aria-disabled", "true");
            } else {
                button.removeAttribute("aria-disabled");
            }
        });
    }

    function enhanceInputs(root) {
        all("input, select, textarea", root).forEach(function (input) {
            if (input.disabled) {
                input.setAttribute("aria-disabled", "true");
            } else {
                input.removeAttribute("aria-disabled");
            }

            if (input.required) {
                input.setAttribute("aria-required", "true");
            }

            if (input instanceof HTMLInputElement) {
                if (input.type === "number") {
                    input.setAttribute("inputmode", "decimal");
                }

                if (input.type === "search") {
                    input.setAttribute("autocomplete", "off");
                    input.setAttribute("spellcheck", "false");
                }
            }
        });
    }

    function enhanceTabs(root) {
        all(".tabbar, .ai-modebar", root).forEach(function (bar) {
            setAttributeIfMissing(bar, "role", "tablist");

            const buttons = all("button", bar);

            buttons.forEach(function (button, index) {
                button.setAttribute("role", "tab");
                button.setAttribute("aria-selected", button.classList.contains("active") ? "true" : "false");
                button.setAttribute("tabindex", button.classList.contains("active") ? "0" : "-1");
                button.dataset.ptTabIndex = String(index);
            });

            if (bar.dataset.ptKeyboardTabs === "1") {
                return;
            }

            bar.dataset.ptKeyboardTabs = "1";

            listen(bar, "keydown", function (event) {
                if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) {
                    return;
                }

                const currentButtons = all("button:not(:disabled)", bar);

                if (!currentButtons.length) {
                    return;
                }

                const currentIndex = Math.max(0, currentButtons.indexOf(document.activeElement));
                let nextIndex = currentIndex;

                if (event.key === "ArrowLeft") {
                    nextIndex = (currentIndex - 1 + currentButtons.length) % currentButtons.length;
                }

                if (event.key === "ArrowRight") {
                    nextIndex = (currentIndex + 1) % currentButtons.length;
                }

                if (event.key === "Home") {
                    nextIndex = 0;
                }

                if (event.key === "End") {
                    nextIndex = currentButtons.length - 1;
                }

                event.preventDefault();
                currentButtons[nextIndex].focus();
            });
        });
    }

    function wrapTable(table) {
        if (!isElement(table)) {
            return;
        }

        if (state.tableWrappers.has(table)) {
            return;
        }

        if (table.parentElement && table.parentElement.classList.contains("pt-runtime-table-wrap")) {
            state.tableWrappers.set(table, table.parentElement);
            return;
        }

        const wrapper = document.createElement("div");
        wrapper.className = "pt-runtime-table-wrap";
        wrapper.setAttribute("role", "region");
        wrapper.setAttribute("aria-label", "Scrollable data table");
        wrapper.setAttribute("tabindex", "0");

        table.parentNode.insertBefore(wrapper, table);
        wrapper.appendChild(table);
        state.tableWrappers.set(table, wrapper);
    }

    function enhanceTables(root) {
        all("table.data-table", root).forEach(function (table) {
            wrapTable(table);

            setAttributeIfMissing(table, "role", "table");

            all("thead th", table).forEach(function (cell) {
                setAttributeIfMissing(cell, "scope", "col");
            });
        });
    }

    function enhanceStatus(root) {
        all(".status-list", root).forEach(function (list) {
            setAttributeIfMissing(list, "role", "status");
            setAttributeIfMissing(list, "aria-live", "polite");
        });

        all(".connect-message", root).forEach(function (message) {
            setAttributeIfMissing(message, "role", "status");
            setAttributeIfMissing(message, "aria-live", "polite");
        });
    }

    function enhanceCharts(root) {
        all(".hero-chart, .trading-chart, .ai-chart", root).forEach(function (chart) {
            setAttributeIfMissing(chart, "role", "img");
            setAttributeIfMissing(chart, "aria-label", "PhoenixTrend market visualization");
        });
    }

    function enhanceScrollableBars(root) {
        all(".tabbar, .ai-modebar, .symbol-strip", root).forEach(function (bar) {
            if (bar.dataset.ptWheelScroll === "1") {
                return;
            }

            bar.dataset.ptWheelScroll = "1";

            listen(bar, "wheel", function (event) {
                if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) {
                    return;
                }

                if (bar.scrollWidth <= bar.clientWidth) {
                    return;
                }

                bar.scrollLeft += event.deltaY;
                event.preventDefault();
            }, { passive: false });
        });
    }

    function enhanceNumericCells(root) {
        all(".data-table td, .metric-grid *, .performance-kpis *, .detail-kpis *", root).forEach(function (element) {
            const text = normalizeText(element.textContent);

            if (/^[+$\-]?\s*[\d,.]+(?:%|\s*[A-Z]{3})?$/.test(text)) {
                element.classList.add("pt-runtime-mono");
            }
        });
    }

    function enhanceModals(root) {
        all('[role="dialog"], .modal, .modal-backdrop, .dialog', root).forEach(function (modal) {
            if (modal.matches('[role="dialog"]')) {
                setAttributeIfMissing(modal, "aria-modal", "true");
            }
        });
    }

    function flash(element) {
        if (!isElement(element)) {
            return;
        }

        element.classList.remove("pt-runtime-flash");
        void element.offsetWidth;
        element.classList.add("pt-runtime-flash");

        window.setTimeout(function () {
            element.classList.remove("pt-runtime-flash");
        }, 560);
    }

    function markBusy(element, busy) {
        if (!isElement(element)) {
            return;
        }

        element.classList.toggle("pt-runtime-busy", Boolean(busy));
        element.setAttribute("aria-busy", busy ? "true" : "false");
    }

    function findNearestPanel(element) {
        if (!isElement(element)) {
            return null;
        }

        return element.closest(
            ".trade-layout > *, .portfolio-layout > *, .risk-layout > *, .ai-layout > *, .activity-layout > *, .analytics-layout > *, .settings-layout > *, .settings-main"
        );
    }

    function onGlobalClick(event) {
        const target = event.target;

        if (!isElement(target)) {
            return;
        }

        const button = target.closest("button");

        if (!button || button.disabled) {
            return;
        }

        if (button.closest(".tabbar, .ai-modebar, .order-types, .buy-sell")) {
            const panel = findNearestPanel(button);

            if (panel) {
                window.requestAnimationFrame(function () {
                    flash(panel);
                });
            }
        }
    }

    function createScrollButton() {
        if (state.scrollButton || !document.body) {
            return;
        }

        const button = document.createElement("button");
        button.type = "button";
        button.className = "pt-runtime-scroll-top";
        button.setAttribute("aria-label", "Scroll to top");
        button.setAttribute("title", "Scroll to top");
        button.textContent = "↑";

        listen(button, "click", function () {
            window.scrollTo({
                top: 0,
                behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth"
            });
        });

        document.body.appendChild(button);
        state.scrollButton = button;
        updateScrollButton();
    }

    function updateScrollButton() {
        if (!state.scrollButton) {
            return;
        }

        state.scrollButton.classList.toggle("is-visible", window.scrollY > 520 && pageIsSupported());
    }

    function preserveFocusBeforeMutation() {
        const active = document.activeElement;

        if (!isElement(active)) {
            state.lastFocused = null;
            return;
        }

        state.lastFocused = {
            id: active.id || null,
            name: active.getAttribute("name"),
            aria: active.getAttribute("aria-label"),
            tag: active.tagName
        };
    }

    function restoreFocusAfterMutation() {
        const snapshot = state.lastFocused;

        if (!snapshot) {
            return;
        }

        if (document.activeElement && document.activeElement !== document.body) {
            return;
        }

        let candidate = null;

        if (snapshot.id) {
            candidate = document.getElementById(snapshot.id);
        }

        if (!candidate && snapshot.name) {
            candidate = one(snapshot.tag.toLowerCase() + '[name="' + CSS.escape(snapshot.name) + '"]');
        }

        if (!candidate && snapshot.aria) {
            candidate = one(snapshot.tag.toLowerCase() + '[aria-label="' + CSS.escape(snapshot.aria) + '"]');
        }

        if (candidate && isVisible(candidate)) {
            candidate.focus({ preventScroll: true });
        }
    }

    function enhance(root) {
        const scope = root && root.querySelectorAll ? root : document;

        safeCall(function () {
            enhanceButtons(scope);
        });

        safeCall(function () {
            enhanceInputs(scope);
        });

        safeCall(function () {
            enhanceTabs(scope);
        });

        safeCall(function () {
            enhanceTables(scope);
        });

        safeCall(function () {
            enhanceStatus(scope);
        });

        safeCall(function () {
            enhanceCharts(scope);
        });

        safeCall(function () {
            enhanceScrollableBars(scope);
        });

        safeCall(function () {
            enhanceNumericCells(scope);
        });

        safeCall(function () {
            enhanceModals(scope);
        });
    }

    function queueEnhancement() {
        if (state.mutationQueued) {
            return;
        }

        state.mutationQueued = true;

        window.requestAnimationFrame(function () {
            state.mutationQueued = false;
            enhance(document);
            restoreFocusAfterMutation();
            updateScrollButton();
        });
    }

    function startMutationObserver() {
        if (state.observer || !document.body) {
            return;
        }

        state.observer = new MutationObserver(function (mutations) {
            let relevant = false;

            for (const mutation of mutations) {
                if (mutation.type === "childList" && (mutation.addedNodes.length || mutation.removedNodes.length)) {
                    relevant = true;
                    break;
                }

                if (mutation.type === "attributes") {
                    relevant = true;
                    break;
                }
            }

            if (!relevant) {
                return;
            }

            preserveFocusBeforeMutation();
            queueEnhancement();
        });

        state.observer.observe(document.body, {
            childList: true,
            subtree: true,
            attributes: true,
            attributeFilter: ["class", "disabled", "aria-selected"]
        });
    }

    function startResizeObserver() {
        if (state.resizeObserver || typeof ResizeObserver === "undefined") {
            return;
        }

        state.resizeObserver = new ResizeObserver(function (entries) {
            entries.forEach(function (entry) {
                const element = entry.target;

                if (!isElement(element)) {
                    return;
                }

                element.dataset.ptWidth = String(Math.round(entry.contentRect.width));
            });
        });

        PAGE_ROOTS.forEach(function (selector) {
            all(selector).forEach(function (element) {
                state.resizeObserver.observe(element);
            });
        });
    }

    function onKeyDown(event) {
        if (event.key !== "Escape") {
            return;
        }

        const active = document.activeElement;

        if (active instanceof HTMLInputElement || active instanceof HTMLTextAreaElement || active instanceof HTMLSelectElement) {
            active.blur();
        }
    }

    function initialize() {
        if (state.initialized) {
            enhance(document);
            return;
        }

        state.initialized = true;

        enhance(document);
        createScrollButton();
        startMutationObserver();
        startResizeObserver();

        listen(document, "click", onGlobalClick, true);
        listen(document, "keydown", onKeyDown, true);
        listen(window, "scroll", updateScrollButton, { passive: true });
        listen(window, "resize", updateScrollButton, { passive: true });

        document.documentElement.dataset.ptTerminalRuntime = VERSION;
    }

    function destroy() {
        if (state.observer) {
            state.observer.disconnect();
            state.observer = null;
        }

        if (state.resizeObserver) {
            state.resizeObserver.disconnect();
            state.resizeObserver = null;
        }

        while (state.cleanup.length) {
            const cleanup = state.cleanup.pop();
            safeCall(cleanup);
        }

        if (state.scrollButton && state.scrollButton.parentNode) {
            state.scrollButton.parentNode.removeChild(state.scrollButton);
        }

        state.scrollButton = null;
        state.initialized = false;
        delete document.documentElement.dataset.ptTerminalRuntime;
    }

    function refresh() {
        enhance(document);
        updateScrollButton();
    }

    window.PhoenixTrendTerminal = Object.freeze({
        version: VERSION,
        initialize: initialize,
        refresh: refresh,
        destroy: destroy,
        flash: flash,
        markBusy: markBusy
    });

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initialize, { once: true });
    } else {
        initialize();
    }
})();

/* Trade page hook: returns the current rendered root without caching stale Blazor DOM. */
window.PhoenixTrendTerminalTrade = Object.freeze({
    root: function () {
        return document.querySelector(".trade-layout");
    },
    refresh: function () {
        if (window.PhoenixTrendTerminal) {
            window.PhoenixTrendTerminal.refresh();
        }
    }
});

/* Portfolio page hook: returns the current rendered root without caching stale Blazor DOM. */
window.PhoenixTrendTerminalPortfolio = Object.freeze({
    root: function () {
        return document.querySelector(".portfolio-layout");
    },
    refresh: function () {
        if (window.PhoenixTrendTerminal) {
            window.PhoenixTrendTerminal.refresh();
        }
    }
});

/* Risk page hook: returns the current rendered root without caching stale Blazor DOM. */
window.PhoenixTrendTerminalRisk = Object.freeze({
    root: function () {
        return document.querySelector(".risk-layout");
    },
    refresh: function () {
        if (window.PhoenixTrendTerminal) {
            window.PhoenixTrendTerminal.refresh();
        }
    }
});

/* Ai page hook: returns the current rendered root without caching stale Blazor DOM. */
window.PhoenixTrendTerminalAI = Object.freeze({
    root: function () {
        return document.querySelector(".ai-layout");
    },
    refresh: function () {
        if (window.PhoenixTrendTerminal) {
            window.PhoenixTrendTerminal.refresh();
        }
    }
});

/* Activity page hook: returns the current rendered root without caching stale Blazor DOM. */
window.PhoenixTrendTerminalActivity = Object.freeze({
    root: function () {
        return document.querySelector(".activity-layout");
    },
    refresh: function () {
        if (window.PhoenixTrendTerminal) {
            window.PhoenixTrendTerminal.refresh();
        }
    }
});

/* Analytics page hook: returns the current rendered root without caching stale Blazor DOM. */
window.PhoenixTrendTerminalAnalytics = Object.freeze({
    root: function () {
        return document.querySelector(".analytics-layout");
    },
    refresh: function () {
        if (window.PhoenixTrendTerminal) {
            window.PhoenixTrendTerminal.refresh();
        }
    }
});

/* Settings page hook: returns the current rendered root without caching stale Blazor DOM. */
window.PhoenixTrendTerminalSettings = Object.freeze({
    root: function () {
        return document.querySelector(".settings-layout");
    },
    refresh: function () {
        if (window.PhoenixTrendTerminal) {
            window.PhoenixTrendTerminal.refresh();
        }
    }
});

/* =================================================================
   DOM utilities exposed for page-specific scripts.
   These helpers manipulate presentation only; they never submit trades.
   ================================================================= */
(function () {
    "use strict";

    function debounce(callback, wait) {
        let timer = 0;

        return function () {
            const context = this;
            const args = arguments;

            window.clearTimeout(timer);

            timer = window.setTimeout(function () {
                callback.apply(context, args);
            }, wait);
        };
    }

    function throttle(callback, wait) {
        let last = 0;
        let timer = 0;

        return function () {
            const now = Date.now();
            const remaining = wait - (now - last);
            const context = this;
            const args = arguments;

            if (remaining <= 0) {
                window.clearTimeout(timer);
                timer = 0;
                last = now;
                callback.apply(context, args);
                return;
            }

            if (!timer) {
                timer = window.setTimeout(function () {
                    last = Date.now();
                    timer = 0;
                    callback.apply(context, args);
                }, remaining);
            }
        };
    }

    function announce(message, priority) {
        const id = "pt-runtime-announcer";
        let region = document.getElementById(id);

        if (!region) {
            region = document.createElement("div");
            region.id = id;
            region.style.position = "fixed";
            region.style.width = "1px";
            region.style.height = "1px";
            region.style.overflow = "hidden";
            region.style.clip = "rect(0 0 0 0)";
            region.style.whiteSpace = "nowrap";
            region.setAttribute("aria-live", priority === "assertive" ? "assertive" : "polite");
            region.setAttribute("aria-atomic", "true");
            document.body.appendChild(region);
        }

        region.textContent = "";

        window.setTimeout(function () {
            region.textContent = String(message || "");
        }, 20);
    }

    function serializeForm(form) {
        if (!(form instanceof HTMLFormElement)) {
            return {};
        }

        const output = {};
        const data = new FormData(form);

        data.forEach(function (value, key) {
            if (Object.prototype.hasOwnProperty.call(output, key)) {
                if (!Array.isArray(output[key])) {
                    output[key] = [output[key]];
                }

                output[key].push(value);
                return;
            }

            output[key] = value;
        });

        return output;
    }

    function focusFirstInvalid(form) {
        if (!(form instanceof HTMLFormElement)) {
            return false;
        }

        const invalid = form.querySelector(":invalid");

        if (!invalid) {
            return false;
        }

        invalid.focus({ preventScroll: false });
        return true;
    }

    function setFormDisabled(form, disabled) {
        if (!(form instanceof HTMLFormElement)) {
            return;
        }

        form.querySelectorAll("input, select, textarea, button").forEach(function (control) {
            if (disabled) {
                if (!control.hasAttribute("data-pt-was-disabled")) {
                    control.setAttribute("data-pt-was-disabled", control.disabled ? "1" : "0");
                }

                control.disabled = true;
                return;
            }

            const previous = control.getAttribute("data-pt-was-disabled");

            if (previous !== null) {
                control.disabled = previous === "1";
                control.removeAttribute("data-pt-was-disabled");
            }
        });
    }

    function filterTable(table, query) {
        if (!(table instanceof HTMLTableElement)) {
            return 0;
        }

        const needle = String(query || "").trim().toLocaleLowerCase();
        let visible = 0;

        table.querySelectorAll("tbody tr").forEach(function (row) {
            const matches = !needle || row.textContent.toLocaleLowerCase().includes(needle);
            row.hidden = !matches;

            if (matches) {
                visible += 1;
            }
        });

        return visible;
    }

    function sortTable(table, columnIndex, direction) {
        if (!(table instanceof HTMLTableElement)) {
            return;
        }

        const body = table.tBodies[0];

        if (!body) {
            return;
        }

        const rows = Array.from(body.rows);
        const multiplier = direction === "desc" ? -1 : 1;

        rows.sort(function (left, right) {
            const leftCell = left.cells[columnIndex];
            const rightCell = right.cells[columnIndex];
            const leftValue = leftCell ? leftCell.textContent.trim() : "";
            const rightValue = rightCell ? rightCell.textContent.trim() : "";
            const leftNumber = Number(leftValue.replace(/[^0-9.+-]/g, ""));
            const rightNumber = Number(rightValue.replace(/[^0-9.+-]/g, ""));

            if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber) && leftValue && rightValue) {
                return (leftNumber - rightNumber) * multiplier;
            }

            return leftValue.localeCompare(rightValue, undefined, {
                numeric: true,
                sensitivity: "base"
            }) * multiplier;
        });

        rows.forEach(function (row) {
            body.appendChild(row);
        });
    }

    function copyText(text) {
        const value = String(text || "");

        if (navigator.clipboard && navigator.clipboard.writeText) {
            return navigator.clipboard.writeText(value);
        }

        const area = document.createElement("textarea");
        area.value = value;
        area.style.position = "fixed";
        area.style.opacity = "0";
        document.body.appendChild(area);
        area.select();

        try {
            document.execCommand("copy");
            return Promise.resolve();
        } catch (error) {
            return Promise.reject(error);
        } finally {
            area.remove();
        }
    }

    function trapFocus(container, event) {
        if (!(container instanceof Element) || event.key !== "Tab") {
            return;
        }

        const focusable = Array.from(container.querySelectorAll(
            'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex]:not([tabindex="-1"])'
        )).filter(function (element) {
            return element.getClientRects().length > 0;
        });

        if (!focusable.length) {
            event.preventDefault();
            return;
        }

        const first = focusable[0];
        const last = focusable[focusable.length - 1];

        if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
            return;
        }

        if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
        }
    }

    function scrollIntoViewIfNeeded(element) {
        if (!(element instanceof Element)) {
            return;
        }

        const rect = element.getBoundingClientRect();
        const inView = rect.top >= 0 && rect.bottom <= window.innerHeight;

        if (!inView) {
            element.scrollIntoView({
                behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
                block: "nearest"
            });
        }
    }

    function setPressed(button, pressed) {
        if (!(button instanceof HTMLButtonElement)) {
            return;
        }

        button.setAttribute("aria-pressed", pressed ? "true" : "false");
        button.classList.toggle("active", Boolean(pressed));
    }

    function setExpanded(button, expanded) {
        if (!(button instanceof Element)) {
            return;
        }

        button.setAttribute("aria-expanded", expanded ? "true" : "false");
    }

    function visibleRows(table) {
        if (!(table instanceof HTMLTableElement)) {
            return [];
        }

        return Array.from(table.querySelectorAll("tbody tr")).filter(function (row) {
            return !row.hidden;
        });
    }

    function tableToText(table) {
        if (!(table instanceof HTMLTableElement)) {
            return "";
        }

        const lines = [];

        table.querySelectorAll("tr").forEach(function (row) {
            if (row.hidden) {
                return;
            }

            const cells = Array.from(row.querySelectorAll("th, td")).map(function (cell) {
                return cell.textContent.replace(/\s+/g, " ").trim();
            });

            lines.push(cells.join("\t"));
        });

        return lines.join("\n");
    }

    function observeVisibility(element, callback) {
        if (!(element instanceof Element) || typeof IntersectionObserver === "undefined") {
            return function () {};
        }

        const observer = new IntersectionObserver(function (entries) {
            entries.forEach(function (entry) {
                callback(entry.isIntersecting, entry);
            });
        }, {
            root: null,
            rootMargin: "80px",
            threshold: 0.01
        });

        observer.observe(element);

        return function () {
            observer.disconnect();
        };
    }

    function downloadText(filename, content, mimeType) {
        const blob = new Blob([String(content || "")], {
            type: mimeType || "text/plain;charset=utf-8"
        });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = filename || "phoenixtrend-export.txt";
        anchor.style.display = "none";
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        window.setTimeout(function () {
            URL.revokeObjectURL(url);
        }, 0);
    }

    window.PhoenixTrendDom = Object.freeze({
        debounce: debounce,
        throttle: throttle,
        announce: announce,
        serializeForm: serializeForm,
        focusFirstInvalid: focusFirstInvalid,
        setFormDisabled: setFormDisabled,
        filterTable: filterTable,
        sortTable: sortTable,
        copyText: copyText,
        trapFocus: trapFocus,
        scrollIntoViewIfNeeded: scrollIntoViewIfNeeded,
        setPressed: setPressed,
        setExpanded: setExpanded,
        visibleRows: visibleRows,
        tableToText: tableToText,
        observeVisibility: observeVisibility,
        downloadText: downloadText
    });
})();
