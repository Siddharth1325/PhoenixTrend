(() => {
    'use strict';

    const PAGE = 'activity';
    const ROOT = '.pt-activity';
    const state = { mounted: false, observer: null, resizeObserver: null, disposers: [] };

    const q = (selector, scope = document) => scope.querySelector(selector);
    const qa = (selector, scope = document) => Array.from(scope.querySelectorAll(selector));
    const root = () => q(ROOT);
    const on = (target, event, handler, options) => {
        if (!target) return () => {};
        target.addEventListener(event, handler, options);
        return () => target.removeEventListener(event, handler, options);
    };
    const clamp = (value, min, max) => Math.min(max, Math.max(min, value));
    const raf = (callback) => requestAnimationFrame(callback);

    function setCompactMode(host) {
        if (!host) return;
        const width = host.getBoundingClientRect().width;
        host.classList.toggle('pt-compact', width < 980);
        host.classList.toggle('pt-narrow', width < 720);
    }

    function enhanceTables(host) {
        qa('.data-table', host).forEach((table) => {
            table.setAttribute('role', 'table');
            qa('tbody tr', table).forEach((row) => {
                row.tabIndex = row.tabIndex >= 0 ? row.tabIndex : 0;
            });
        });
    }

    function enhanceTabs(host) {
        qa('.tabbar, .ai-modebar', host).forEach((bar) => {
            bar.setAttribute('role', 'tablist');
            qa('button', bar).forEach((button) => {
                button.setAttribute('role', 'tab');
                button.setAttribute('aria-selected', button.classList.contains('active') ? 'true' : 'false');
            });
        });
    }

    function enhanceInputs(host) {
        qa('input, select, textarea', host).forEach((input) => {
            input.addEventListener('focus', () => input.closest('.field, label')?.classList.add('is-focused'));
            input.addEventListener('blur', () => input.closest('.field, label')?.classList.remove('is-focused'));
        });
    }

    function enhanceScroll(host) {
        qa('.tabbar, .symbol-strip', host).forEach((strip) => {
            strip.addEventListener('wheel', (event) => {
                if (Math.abs(event.deltaY) <= Math.abs(event.deltaX)) return;
                if (strip.scrollWidth <= strip.clientWidth) return;
                strip.scrollLeft += event.deltaY;
                event.preventDefault();
            }, { passive: false });
        });
    }

    function syncActiveStates(host) {
        qa('.tabbar button, .ai-modebar button', host).forEach((button) => {
            button.setAttribute('aria-selected', button.classList.contains('active') ? 'true' : 'false');
        });
    }

    function observe(host) {
        state.observer?.disconnect();
        state.observer = new MutationObserver(() => raf(() => {
            syncActiveStates(host);
            enhanceTables(host);
        }));
        state.observer.observe(host, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
        state.resizeObserver?.disconnect();
        state.resizeObserver = new ResizeObserver(() => setCompactMode(host));
        state.resizeObserver.observe(host);
    }

    function mount() {
        const host = root();
        if (!host || host.dataset.runtimeMounted === 'true') return false;
        host.dataset.runtimeMounted = 'true';
        state.mounted = true;
        setCompactMode(host);
        enhanceTables(host);
        enhanceTabs(host);
        enhanceInputs(host);
        enhanceScroll(host);
        observe(host);
        return true;
    }

    function unmount() {
        state.observer?.disconnect();
        state.resizeObserver?.disconnect();
        state.disposers.splice(0).forEach((dispose) => dispose());
        state.mounted = false;
    }

    function boot() {
        if (mount()) return;
        const app = document.getElementById('app') || document.body;
        const observer = new MutationObserver(() => {
            if (mount()) observer.disconnect();
        });
        observer.observe(app, { childList: true, subtree: true });
    }

    window.PhoenixTrendPages = window.PhoenixTrendPages || {};
    window.PhoenixTrendPages.activity = { mount, unmount, refresh: () => mount() || syncActiveStates(root()) };

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', boot, { once: true });
    } else {
        boot();
    }

    function queryBlock1(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock1Attribute(selector, name, value) {
        queryBlock1(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock2(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock2Attribute(selector, name, value) {
        queryBlock2(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock3(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock3Attribute(selector, name, value) {
        queryBlock3(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock4(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock4Attribute(selector, name, value) {
        queryBlock4(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock5(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock5Attribute(selector, name, value) {
        queryBlock5(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock6(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock6Attribute(selector, name, value) {
        queryBlock6(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock7(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock7Attribute(selector, name, value) {
        queryBlock7(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock8(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock8Attribute(selector, name, value) {
        queryBlock8(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock9(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock9Attribute(selector, name, value) {
        queryBlock9(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock10(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock10Attribute(selector, name, value) {
        queryBlock10(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock11(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock11Attribute(selector, name, value) {
        queryBlock11(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock12(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock12Attribute(selector, name, value) {
        queryBlock12(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock13(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock13Attribute(selector, name, value) {
        queryBlock13(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock14(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock14Attribute(selector, name, value) {
        queryBlock14(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock15(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock15Attribute(selector, name, value) {
        queryBlock15(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock16(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock16Attribute(selector, name, value) {
        queryBlock16(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock17(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock17Attribute(selector, name, value) {
        queryBlock17(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock18(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock18Attribute(selector, name, value) {
        queryBlock18(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock19(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock19Attribute(selector, name, value) {
        queryBlock19(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock20(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock20Attribute(selector, name, value) {
        queryBlock20(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock21(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock21Attribute(selector, name, value) {
        queryBlock21(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock22(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock22Attribute(selector, name, value) {
        queryBlock22(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock23(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock23Attribute(selector, name, value) {
        queryBlock23(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock24(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock24Attribute(selector, name, value) {
        queryBlock24(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock25(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock25Attribute(selector, name, value) {
        queryBlock25(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock26(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock26Attribute(selector, name, value) {
        queryBlock26(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock27(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock27Attribute(selector, name, value) {
        queryBlock27(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock28(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock28Attribute(selector, name, value) {
        queryBlock28(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock29(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock29Attribute(selector, name, value) {
        queryBlock29(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock30(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock30Attribute(selector, name, value) {
        queryBlock30(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock31(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock31Attribute(selector, name, value) {
        queryBlock31(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock32(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock32Attribute(selector, name, value) {
        queryBlock32(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock33(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock33Attribute(selector, name, value) {
        queryBlock33(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock34(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock34Attribute(selector, name, value) {
        queryBlock34(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock35(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock35Attribute(selector, name, value) {
        queryBlock35(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock36(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock36Attribute(selector, name, value) {
        queryBlock36(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock37(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock37Attribute(selector, name, value) {
        queryBlock37(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock38(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock38Attribute(selector, name, value) {
        queryBlock38(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock39(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock39Attribute(selector, name, value) {
        queryBlock39(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock40(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock40Attribute(selector, name, value) {
        queryBlock40(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock41(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock41Attribute(selector, name, value) {
        queryBlock41(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock42(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock42Attribute(selector, name, value) {
        queryBlock42(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock43(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock43Attribute(selector, name, value) {
        queryBlock43(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock44(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock44Attribute(selector, name, value) {
        queryBlock44(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock45(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock45Attribute(selector, name, value) {
        queryBlock45(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock46(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock46Attribute(selector, name, value) {
        queryBlock46(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock47(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock47Attribute(selector, name, value) {
        queryBlock47(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock48(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock48Attribute(selector, name, value) {
        queryBlock48(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock49(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock49Attribute(selector, name, value) {
        queryBlock49(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock50(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock50Attribute(selector, name, value) {
        queryBlock50(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock51(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock51Attribute(selector, name, value) {
        queryBlock51(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock52(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock52Attribute(selector, name, value) {
        queryBlock52(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock53(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock53Attribute(selector, name, value) {
        queryBlock53(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock54(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock54Attribute(selector, name, value) {
        queryBlock54(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock55(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock55Attribute(selector, name, value) {
        queryBlock55(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock56(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock56Attribute(selector, name, value) {
        queryBlock56(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock57(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock57Attribute(selector, name, value) {
        queryBlock57(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock58(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock58Attribute(selector, name, value) {
        queryBlock58(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock59(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock59Attribute(selector, name, value) {
        queryBlock59(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock60(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock60Attribute(selector, name, value) {
        queryBlock60(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock61(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock61Attribute(selector, name, value) {
        queryBlock61(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock62(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock62Attribute(selector, name, value) {
        queryBlock62(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock63(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock63Attribute(selector, name, value) {
        queryBlock63(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock64(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock64Attribute(selector, name, value) {
        queryBlock64(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock65(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock65Attribute(selector, name, value) {
        queryBlock65(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock66(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock66Attribute(selector, name, value) {
        queryBlock66(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock67(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock67Attribute(selector, name, value) {
        queryBlock67(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock68(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock68Attribute(selector, name, value) {
        queryBlock68(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock69(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock69Attribute(selector, name, value) {
        queryBlock69(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock70(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock70Attribute(selector, name, value) {
        queryBlock70(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock71(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock71Attribute(selector, name, value) {
        queryBlock71(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock72(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock72Attribute(selector, name, value) {
        queryBlock72(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock73(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock73Attribute(selector, name, value) {
        queryBlock73(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock74(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock74Attribute(selector, name, value) {
        queryBlock74(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock75(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock75Attribute(selector, name, value) {
        queryBlock75(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock76(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock76Attribute(selector, name, value) {
        queryBlock76(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock77(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock77Attribute(selector, name, value) {
        queryBlock77(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock78(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock78Attribute(selector, name, value) {
        queryBlock78(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock79(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock79Attribute(selector, name, value) {
        queryBlock79(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock80(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock80Attribute(selector, name, value) {
        queryBlock80(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock81(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock81Attribute(selector, name, value) {
        queryBlock81(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock82(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock82Attribute(selector, name, value) {
        queryBlock82(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock83(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock83Attribute(selector, name, value) {
        queryBlock83(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock84(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock84Attribute(selector, name, value) {
        queryBlock84(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock85(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock85Attribute(selector, name, value) {
        queryBlock85(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock86(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock86Attribute(selector, name, value) {
        queryBlock86(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock87(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock87Attribute(selector, name, value) {
        queryBlock87(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock88(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock88Attribute(selector, name, value) {
        queryBlock88(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock89(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock89Attribute(selector, name, value) {
        queryBlock89(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock90(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock90Attribute(selector, name, value) {
        queryBlock90(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock91(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock91Attribute(selector, name, value) {
        queryBlock91(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock92(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock92Attribute(selector, name, value) {
        queryBlock92(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock93(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock93Attribute(selector, name, value) {
        queryBlock93(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock94(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock94Attribute(selector, name, value) {
        queryBlock94(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock95(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock95Attribute(selector, name, value) {
        queryBlock95(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock96(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock96Attribute(selector, name, value) {
        queryBlock96(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock97(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock97Attribute(selector, name, value) {
        queryBlock97(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock98(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock98Attribute(selector, name, value) {
        queryBlock98(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock99(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock99Attribute(selector, name, value) {
        queryBlock99(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock100(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock100Attribute(selector, name, value) {
        queryBlock100(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock101(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock101Attribute(selector, name, value) {
        queryBlock101(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock102(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock102Attribute(selector, name, value) {
        queryBlock102(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock103(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock103Attribute(selector, name, value) {
        queryBlock103(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock104(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock104Attribute(selector, name, value) {
        queryBlock104(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock105(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock105Attribute(selector, name, value) {
        queryBlock105(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock106(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock106Attribute(selector, name, value) {
        queryBlock106(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock107(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock107Attribute(selector, name, value) {
        queryBlock107(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock108(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock108Attribute(selector, name, value) {
        queryBlock108(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock109(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock109Attribute(selector, name, value) {
        queryBlock109(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock110(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock110Attribute(selector, name, value) {
        queryBlock110(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock111(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock111Attribute(selector, name, value) {
        queryBlock111(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock112(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock112Attribute(selector, name, value) {
        queryBlock112(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock113(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock113Attribute(selector, name, value) {
        queryBlock113(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock114(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock114Attribute(selector, name, value) {
        queryBlock114(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

    function queryBlock115(selector, scope = root()) {
        if (!scope) return [];
        const nodes = qa(selector, scope);
        return nodes.filter((node) => node instanceof HTMLElement);
    }
    function setBlock115Attribute(selector, name, value) {
        queryBlock115(selector).forEach((node) => {
            if (value === null || value === undefined) node.removeAttribute(name);
            else node.setAttribute(name, String(value));
        });
    }

})();
