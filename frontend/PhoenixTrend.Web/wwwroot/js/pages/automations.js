/* ============================================================
   PHOENIXTREND AUTOMATIONS
   frontend/PhoenixTrend.Web/wwwroot/js/pages/automations.js

   UI STATE / VISUAL SYNCHRONIZATION ONLY
   Blazor + PhoenixApi remain authoritative for trading actions.
   ============================================================ */

window.PhoenixPage_automations = () => {
    if (
        window.PhoenixPremium &&
        typeof window.PhoenixPremium.init === "function"
    ) {
        window.PhoenixPremium.init("automations");
    }

    if (
        window.PhoenixAutomations &&
        typeof window.PhoenixAutomations.initialize === "function"
    ) {
        window.PhoenixAutomations.initialize();
    }
};


window.PhoenixAutomations = (() => {

    /* ============================================================
       STATE
       ============================================================ */

    let initialized = false;
    let observer = null;
    let observedRoot = null;

    let activeSection = "engine";
    let engineState = "STOPPED";

    const sectionStates = new Map();
    const runtimeStates = new Map();


    /* ============================================================
       SELECTORS
       ============================================================ */

    const SELECTORS = {
        root: ".pt-automations",

        section:
            ".auto-section[data-auto-section]",

        navItem:
            ".auto-section-nav [data-auto-section]",

        engineState:
            "[data-engine-state]",

        runtime:
            "[data-runtime-state]",

        assetSection:
            "[data-asset-section]",

        automation:
            "[data-automation-id]",

        engineAsset:
            ".auto-engine-asset",

        switch:
            ".auto-switch",

        panel:
            ".auto-panel",

        metric:
            ".auto-engine-metrics article",

        sideCard:
            ".auto-side-card"
    };


    /* ============================================================
       HELPERS
       ============================================================ */

    function getRoot() {
        return document.querySelector(
            SELECTORS.root
        );
    }


    function normalize(value) {
        return String(value ?? "")
            .trim()
            .toUpperCase();
    }


    function normalizeKey(value) {
        return String(value ?? "")
            .trim()
            .toLowerCase();
    }


    function escapeSelector(value) {
        const text =
            String(value ?? "");

        if (
            window.CSS &&
            typeof window.CSS.escape === "function"
        ) {
            return window.CSS.escape(text);
        }

        return text.replace(
            /["\\]/g,
            "\\$&"
        );
    }


    function setText(element, value) {
        if (!element) {
            return;
        }

        element.textContent =
            value == null
                ? ""
                : String(value);
    }


    function setAttribute(
        element,
        name,
        value
    ) {
        if (!element) {
            return;
        }

        if (
            value == null ||
            value === ""
        ) {
            element.removeAttribute(name);
            return;
        }

        element.setAttribute(
            name,
            String(value)
        );
    }


    function toggleClass(
        element,
        className,
        enabled
    ) {
        if (!element) {
            return;
        }

        element.classList.toggle(
            className,
            Boolean(enabled)
        );
    }


    function requestFrame(callback) {
        if (
            typeof window.requestAnimationFrame ===
            "function"
        ) {
            window.requestAnimationFrame(
                callback
            );

            return;
        }

        window.setTimeout(
            callback,
            0
        );
    }


    function getDatasetKey(
        element,
        ...keys
    ) {
        if (!element) {
            return "";
        }

        for (const key of keys) {
            const value =
                element.dataset?.[key];

            if (
                value != null &&
                String(value).trim() !== ""
            ) {
                return String(value).trim();
            }
        }

        return "";
    }


    function boolFromValue(
        value,
        fallback = false
    ) {
        if (
            value === true ||
            value === "true" ||
            value === "1" ||
            value === 1
        ) {
            return true;
        }

        if (
            value === false ||
            value === "false" ||
            value === "0" ||
            value === 0
        ) {
            return false;
        }

        return fallback;
    }


    /* ============================================================
       INITIALIZE
       ============================================================ */

    function initialize() {
        const root =
            getRoot();

        if (!root) {
            initialized = false;
            disconnectObserver();

            return false;
        }

        if (
            observedRoot &&
            observedRoot !== root
        ) {
            unbindRoot(
                observedRoot
            );

            disconnectObserver();

            initialized = false;
        }

        if (!initialized) {
            initialized = true;

            bindRoot(root);

            startObserver(root);
        } else {
            bindRoot(root);
        }

        enhance(root);

        return true;
    }


    /* ============================================================
       ROOT BINDING
       ============================================================ */

    function bindRoot(root) {
        if (
            !root ||
            root.dataset
                .phoenixAutomationsBound ===
                "true"
        ) {
            return;
        }

        root.dataset
            .phoenixAutomationsBound =
            "true";

        root.addEventListener(
            "click",
            handleRootClick
        );

        root.addEventListener(
            "pointermove",
            handlePointerMove,
            {
                passive: true
            }
        );

        root.addEventListener(
            "pointerleave",
            handlePointerLeave,
            {
                passive: true
            }
        );
    }


    function unbindRoot(root) {
        if (!root) {
            return;
        }

        root.removeEventListener(
            "click",
            handleRootClick
        );

        root.removeEventListener(
            "pointermove",
            handlePointerMove
        );

        root.removeEventListener(
            "pointerleave",
            handlePointerLeave
        );

        if (root.dataset) {
            delete root.dataset
                .phoenixAutomationsBound;
        }
    }


    /* ============================================================
       ENHANCE DOM
       ============================================================ */

    function enhance(root) {
        if (!root) {
            return;
        }

        prepareNavigation(root);

        preparePanels(root);

        prepareMetrics(root);

        prepareAssetRows(root);

        prepareSwitches(root);

        prepareRuntimeRows(root);

        prepareSideCards(root);

        syncActiveSection(root);

        syncEngineVisuals(root);

        syncStoredSectionStates(root);

        syncStoredRuntimeStates(root);
    }


    /* ============================================================
       NAVIGATION
       ============================================================ */

    function prepareNavigation(root) {
        const items =
            root.querySelectorAll(
                SELECTORS.navItem
            );

        items.forEach((item) => {
            if (
                item.dataset
                    .phoenixNavReady ===
                "true"
            ) {
                return;
            }

            item.dataset
                .phoenixNavReady =
                "true";

            if (
                item.tagName ===
                "BUTTON"
            ) {
                if (
                    !item.getAttribute(
                        "type"
                    )
                ) {
                    item.setAttribute(
                        "type",
                        "button"
                    );
                }
            }

            item.setAttribute(
                "role",
                "tab"
            );
        });
    }


    function setActiveSection(
        sectionName
    ) {
        const key =
            normalizeKey(
                sectionName
            );

        if (!key) {
            return;
        }

        activeSection =
            key;

        const root =
            getRoot();

        if (!root) {
            return;
        }

        syncActiveSection(
            root
        );
    }


    function syncActiveSection(root) {
        if (!root) {
            return;
        }

        const navItems =
            root.querySelectorAll(
                SELECTORS.navItem
            );

        navItems.forEach(
            (item) => {
                const section =
                    normalizeKey(
                        item.dataset
                            .autoSection
                    );

                const selected =
                    section ===
                    activeSection;

                item.classList.toggle(
                    "active",
                    selected
                );

                item.setAttribute(
                    "aria-selected",
                    selected
                        ? "true"
                        : "false"
                );

                item.setAttribute(
                    "tabindex",
                    selected
                        ? "0"
                        : "-1"
                );

                if (selected) {
                    item.setAttribute(
                        "aria-current",
                        "page"
                    );
                } else {
                    item.removeAttribute(
                        "aria-current"
                    );
                }
            }
        );

        const sections =
            root.querySelectorAll(
                SELECTORS.section
            );

        sections.forEach(
            (section) => {
                const sectionName =
                    normalizeKey(
                        section.dataset
                            .autoSection
                    );

                const selected =
                    sectionName ===
                    activeSection;

                section.classList.toggle(
                    "active",
                    selected
                );

                section.dataset.active =
                    selected
                        ? "true"
                        : "false";

                if (
                    section.hasAttribute(
                        "data-auto-section-panel"
                    )
                ) {
                    section.hidden =
                        !selected;
                }
            }
        );
    }


    /* ============================================================
       ENGINE STATE
       ============================================================ */

    function setEngineState(state) {
        engineState =
            normalize(state) ||
            "STOPPED";

        const root =
            getRoot();

        if (!root) {
            return;
        }

        syncEngineVisuals(
            root
        );
    }


    function syncEngineVisuals(root) {
        if (!root) {
            return;
        }

        const state =
            normalize(
                engineState
            ) || "STOPPED";

        const stateElements =
            root.querySelectorAll(
                SELECTORS.engineState
            );

        stateElements.forEach(
            (element) => {
                element.dataset
                    .engineState =
                    state;

                if (
                    element.matches(
                        ".auto-engine-state"
                    ) ||
                    element.dataset
                        .engineStateText ===
                        "true"
                ) {
                    setText(
                        element,
                        formatEngineState(
                            state
                        )
                    );
                }
            }
        );

        root.dataset.engineState =
            state;

        root.classList.toggle(
            "engine-running",
            state === "RUNNING"
        );

        root.classList.toggle(
            "engine-stopped",
            state === "STOPPED"
        );

        root.classList.toggle(
            "engine-starting",
            state === "STARTING"
        );

        root.classList.toggle(
            "engine-stopping",
            state === "STOPPING"
        );

        root.classList.toggle(
            "engine-error",
            state === "ERROR"
        );

        root.classList.toggle(
            "engine-emergency",
            state ===
                "EMERGENCY_STOP"
        );
    }


    function formatEngineState(state) {
        switch (
            normalize(state)
        ) {
            case "RUNNING":
                return "RUNNING";

            case "EMERGENCY_STOP":
                return "EMERGENCY STOP";

            case "STARTING":
                return "STARTING";

            case "STOPPING":
                return "STOPPING";

            case "ERROR":
                return "ERROR";

            default:
                return "STOPPED";
        }
    }


    /* ============================================================
       ASSET SECTION STATE
       ============================================================ */

    function setSectionState(
        sectionName,
        enabled
    ) {
        const key =
            normalizeKey(
                sectionName
            );

        if (!key) {
            return;
        }

        const value =
            Boolean(enabled);

        sectionStates.set(
            key,
            value
        );

        const root =
            getRoot();

        if (!root) {
            return;
        }

        applySectionState(
            root,
            key,
            value
        );
    }


    function applySectionState(
        root,
        key,
        enabled
    ) {
        if (
            !root ||
            !key
        ) {
            return;
        }

        const escaped =
            escapeSelector(key);

        const targets =
            root.querySelectorAll(
                `[data-asset-section="${escaped}"],` +
                `[data-auto-asset="${escaped}"]`
            );

        targets.forEach(
            (element) => {
                element.classList.toggle(
                    "is-on",
                    enabled
                );

                element.classList.toggle(
                    "is-off",
                    !enabled
                );

                element.dataset.enabled =
                    enabled
                        ? "true"
                        : "false";

                const switchElement =
                    element.matches(
                        ".auto-switch"
                    )
                        ? element
                        : element.querySelector(
                            ".auto-switch"
                        );

                syncSwitch(
                    switchElement,
                    enabled
                );

                const label =
                    element.querySelector(
                        ".auto-section-toggle-label"
                    );

                if (label) {
                    setText(
                        label,
                        enabled
                            ? "ENABLED"
                            : "DISABLED"
                    );
                }
            }
        );

        const navTargets =
            root.querySelectorAll(
                `.auto-section-nav [data-auto-section="${escaped}"]`
            );

        navTargets.forEach(
            (navItem) => {
                navItem.classList.toggle(
                    "is-on",
                    enabled
                );

                navItem.classList.toggle(
                    "is-off",
                    !enabled
                );

                navItem.dataset.enabled =
                    enabled
                        ? "true"
                        : "false";
            }
        );
    }


    function syncStoredSectionStates(
        root
    ) {
        sectionStates.forEach(
            (enabled, key) => {
                applySectionState(
                    root,
                    key,
                    enabled
                );
            }
        );
    }


    /* ============================================================
       SECTION RUNNING STATE
       ============================================================ */

    function setSectionRunning(
        sectionName,
        running
    ) {
        const key =
            normalizeKey(
                sectionName
            );

        if (!key) {
            return;
        }

        const root =
            getRoot();

        if (!root) {
            return;
        }

        const escaped =
            escapeSelector(key);

        const targets =
            root.querySelectorAll(
                `[data-asset-section="${escaped}"],` +
                `[data-auto-asset="${escaped}"]`
            );

        targets.forEach(
            (element) => {
                element.classList.toggle(
                    "is-running",
                    Boolean(running)
                );

                element.dataset.running =
                    running
                        ? "true"
                        : "false";
            }
        );
    }


    /* ============================================================
       RUNTIME STATE
       ============================================================ */

    function setRuntimeState(
        automationId,
        state
    ) {
        const key =
            String(
                automationId ?? ""
            ).trim();

        if (!key) {
            return;
        }

        const normalizedState =
            normalize(state) ||
            "STOPPED";

        runtimeStates.set(
            key,
            normalizedState
        );

        const root =
            getRoot();

        if (!root) {
            return;
        }

        applyRuntimeState(
            root,
            key,
            normalizedState
        );
    }


    function applyRuntimeState(
        root,
        automationId,
        state
    ) {
        if (
            !root ||
            !automationId
        ) {
            return;
        }

        const escaped =
            escapeSelector(
                automationId
            );

        const targets =
            root.querySelectorAll(
                `[data-automation-id="${escaped}"]`
            );

        targets.forEach(
            (element) => {
                element.dataset
                    .runtimeState =
                    state;

                element.classList.toggle(
                    "is-running",
                    state === "RUNNING"
                );

                element.classList.toggle(
                    "is-error",
                    state === "ERROR" ||
                    state === "FAILED"
                );

                element.classList.toggle(
                    "is-stopped",
                    state === "STOPPED"
                );

                element.classList.toggle(
                    "is-paused",
                    state === "PAUSED"
                );

                element.classList.toggle(
                    "is-starting",
                    state === "STARTING"
                );

                element.classList.toggle(
                    "is-stopping",
                    state === "STOPPING"
                );

                element.classList.toggle(
                    "is-disabled",
                    state === "DISABLED"
                );

                const badge =
                    element.querySelector(
                        ".auto-runtime-badge"
                    );

                if (badge) {
                    badge.dataset
                        .runtimeState =
                        state;

                    setText(
                        badge,
                        formatRuntimeState(
                            state
                        )
                    );
                }
            }
        );
    }


    function syncStoredRuntimeStates(
        root
    ) {
        runtimeStates.forEach(
            (
                state,
                automationId
            ) => {
                applyRuntimeState(
                    root,
                    automationId,
                    state
                );
            }
        );
    }


    function formatRuntimeState(state) {
        const normalized =
            normalize(state);

        switch (normalized) {
            case "RUNNING":
                return "RUNNING";

            case "PAUSED":
                return "PAUSED";

            case "STARTING":
                return "STARTING";

            case "STOPPING":
                return "STOPPING";

            case "FAILED":
                return "FAILED";

            case "ERROR":
                return "ERROR";

            case "DISABLED":
                return "DISABLED";

            default:
                return "STOPPED";
        }
    }


    /* ============================================================
       SWITCHES
       ============================================================ */

    function prepareSwitches(root) {
        const switches =
            root.querySelectorAll(
                SELECTORS.switch
            );

        switches.forEach(
            (switchElement) => {
                if (
                    switchElement.dataset
                        .phoenixSwitchReady ===
                    "true"
                ) {
                    return;
                }

                switchElement.dataset
                    .phoenixSwitchReady =
                    "true";

                if (
                    switchElement.tagName ===
                        "BUTTON" &&
                    !switchElement
                        .getAttribute(
                            "type"
                        )
                ) {
                    switchElement
                        .setAttribute(
                            "type",
                            "button"
                        );
                }

                const datasetEnabled =
                    switchElement.dataset
                        .enabled;

                const enabled =
                    datasetEnabled != null
                        ? boolFromValue(
                            datasetEnabled,
                            switchElement
                                .classList
                                .contains(
                                    "on"
                                )
                        )
                        : switchElement
                            .classList
                            .contains(
                                "on"
                            );

                syncSwitch(
                    switchElement,
                    enabled
                );
            }
        );
    }


    function syncSwitch(
        switchElement,
        enabled
    ) {
        if (!switchElement) {
            return;
        }

        const value =
            Boolean(enabled);

        switchElement.classList.toggle(
            "on",
            value
        );

        switchElement.setAttribute(
            "aria-pressed",
            value
                ? "true"
                : "false"
        );

        switchElement.dataset.enabled =
            value
                ? "true"
                : "false";
    }


    /* ============================================================
       ASSET ROW PREPARATION
       ============================================================ */

    function prepareAssetRows(root) {
        const rows =
            root.querySelectorAll(
                SELECTORS.engineAsset
            );

        rows.forEach(
            (row, index) => {
                if (
                    row.dataset
                        .phoenixAssetReady ===
                    "true"
                ) {
                    return;
                }

                row.dataset
                    .phoenixAssetReady =
                    "true";

                row.style.setProperty(
                    "--auto-row-index",
                    String(index)
                );

                const sectionName =
                    normalizeKey(
                        row.dataset
                            .assetSection ||
                        row.dataset
                            .autoAsset
                    );

                if (
                    sectionName &&
                    sectionStates.has(
                        sectionName
                    )
                ) {
                    const enabled =
                        sectionStates.get(
                            sectionName
                        );

                    row.classList.toggle(
                        "is-on",
                        Boolean(enabled)
                    );

                    row.classList.toggle(
                        "is-off",
                        !Boolean(enabled)
                    );
                }
            }
        );
    }


    /* ============================================================
       PANEL PREPARATION
       ============================================================ */

    function preparePanels(root) {
        const panels =
            root.querySelectorAll(
                SELECTORS.panel
            );

        panels.forEach(
            (panel, index) => {
                if (
                    panel.dataset
                        .phoenixPanelReady ===
                    "true"
                ) {
                    return;
                }

                panel.dataset
                    .phoenixPanelReady =
                    "true";

                panel.style.setProperty(
                    "--auto-panel-index",
                    String(index)
                );
            }
        );
    }


    /* ============================================================
       METRIC PREPARATION
       ============================================================ */

    function prepareMetrics(root) {
        const metrics =
            root.querySelectorAll(
                SELECTORS.metric
            );

        metrics.forEach(
            (metric, index) => {
                if (
                    metric.dataset
                        .phoenixMetricReady ===
                    "true"
                ) {
                    return;
                }

                metric.dataset
                    .phoenixMetricReady =
                    "true";

                metric.style.setProperty(
                    "--auto-metric-index",
                    String(index)
                );
            }
        );
    }


    /* ============================================================
       RUNTIME ROW PREPARATION
       ============================================================ */

    function prepareRuntimeRows(root) {
        const rows =
            root.querySelectorAll(
                "[data-automation-id]"
            );

        rows.forEach(
            (row) => {
                if (
                    row.dataset
                        .phoenixRuntimeReady ===
                    "true"
                ) {
                    return;
                }

                row.dataset
                    .phoenixRuntimeReady =
                    "true";

                const automationId =
                    String(
                        row.dataset
                            .automationId ??
                        ""
                    ).trim();

                if (
                    automationId &&
                    runtimeStates.has(
                        automationId
                    )
                ) {
                    applyRuntimeState(
                        root,
                        automationId,
                        runtimeStates.get(
                            automationId
                        )
                    );
                }
            }
        );
    }


    /* ============================================================
       SIDE CARDS
       ============================================================ */

    function prepareSideCards(root) {
        const cards =
            root.querySelectorAll(
                SELECTORS.sideCard
            );

        cards.forEach(
            (card, index) => {
                if (
                    card.dataset
                        .phoenixSideReady ===
                    "true"
                ) {
                    return;
                }

                card.dataset
                    .phoenixSideReady =
                    "true";

                card.style.setProperty(
                    "--auto-side-index",
                    String(index)
                );
            }
        );
    }


    /* ============================================================
       CLICK HANDLING
       ============================================================ */

    function handleRootClick(event) {
        const root =
            getRoot();

        if (!root) {
            return;
        }

        const target =
            event.target;

        if (
            !target ||
            typeof target.closest !==
                "function"
        ) {
            return;
        }

        const navItem =
            target.closest(
                ".auto-section-nav [data-auto-section]"
            );

        if (
            navItem &&
            root.contains(navItem)
        ) {
            const sectionName =
                normalizeKey(
                    navItem.dataset
                        .autoSection
                );

            if (sectionName) {
                activeSection =
                    sectionName;

                syncActiveSection(
                    root
                );
            }
        }
    }


    /* ============================================================
       PREMIUM POINTER LIGHT
       ============================================================ */

    function handlePointerMove(event) {
        const root =
            getRoot();

        if (!root) {
            return;
        }

        const eventTarget =
            event.target;

        if (
            !eventTarget ||
            typeof eventTarget.closest !==
                "function"
        ) {
            return;
        }

        const target =
            eventTarget.closest(
                ".auto-panel, " +
                ".auto-engine-command, " +
                ".auto-engine-metrics article, " +
                ".auto-side-card"
            );

        if (
            !target ||
            !root.contains(target)
        ) {
            return;
        }

        const rect =
            target
                .getBoundingClientRect();

        if (
            !rect.width ||
            !rect.height
        ) {
            return;
        }

        const x =
            event.clientX -
            rect.left;

        const y =
            event.clientY -
            rect.top;

        const xPercent =
            Math.max(
                0,
                Math.min(
                    100,
                    (
                        x /
                        rect.width
                    ) * 100
                )
            );

        const yPercent =
            Math.max(
                0,
                Math.min(
                    100,
                    (
                        y /
                        rect.height
                    ) * 100
                )
            );

        target.style.setProperty(
            "--auto-pointer-x",
            `${xPercent}%`
        );

        target.style.setProperty(
            "--auto-pointer-y",
            `${yPercent}%`
        );

        target.classList.add(
            "auto-pointer-active"
        );
    }


    function handlePointerLeave(event) {
        const root =
            getRoot();

        if (!root) {
            return;
        }

        const eventTarget =
            event.target;

        if (
            !eventTarget ||
            typeof eventTarget.closest !==
                "function"
        ) {
            return;
        }

        const target =
            eventTarget.closest(
                ".auto-panel, " +
                ".auto-engine-command, " +
                ".auto-engine-metrics article, " +
                ".auto-side-card"
            );

        if (!target) {
            return;
        }

        target.classList.remove(
            "auto-pointer-active"
        );
    }


    /* ============================================================
       MUTATION OBSERVER
       ============================================================ */

    function startObserver(root) {
        disconnectObserver();

        if (
            !root ||
            typeof MutationObserver ===
                "undefined"
        ) {
            return;
        }

        observedRoot =
            root;

        let scheduled =
            false;

        observer =
            new MutationObserver(
                () => {
                    if (scheduled) {
                        return;
                    }

                    scheduled =
                        true;

                    requestFrame(
                        () => {
                            scheduled =
                                false;

                            const currentRoot =
                                getRoot();

                            if (
                                !currentRoot
                            ) {
                                dispose();
                                return;
                            }

                            if (
                                currentRoot !==
                                observedRoot
                            ) {
                                initialize();
                                return;
                            }

                            enhance(
                                currentRoot
                            );
                        }
                    );
                }
            );

        observer.observe(
            root,
            {
                childList: true,
                subtree: true
            }
        );
    }


    function disconnectObserver() {
        if (observer) {
            observer.disconnect();

            observer =
                null;
        }

        observedRoot =
            null;
    }


    /* ============================================================
       REFRESH / RESYNC
       ============================================================ */

    function refresh() {
        const root =
            getRoot();

        if (!root) {
            initialize();
            return;
        }

        if (
            observedRoot !== root
        ) {
            initialize();
            return;
        }

        enhance(root);
    }


    /* ============================================================
       RESET
       ============================================================ */

    function reset() {
        activeSection =
            "engine";

        engineState =
            "STOPPED";

        sectionStates.clear();

        runtimeStates.clear();

        const root =
            getRoot();

        if (root) {
            syncActiveSection(
                root
            );

            syncEngineVisuals(
                root
            );

            const sectionTargets =
                root.querySelectorAll(
                    "[data-asset-section]," +
                    "[data-auto-asset]"
                );

            sectionTargets.forEach(
                (element) => {
                    element.classList.remove(
                        "is-on",
                        "is-running"
                    );

                    element.classList.add(
                        "is-off"
                    );

                    element.dataset.enabled =
                        "false";

                    element.dataset.running =
                        "false";

                    const switchElement =
                        element.matches(
                            ".auto-switch"
                        )
                            ? element
                            : element
                                .querySelector(
                                    ".auto-switch"
                                );

                    syncSwitch(
                        switchElement,
                        false
                    );

                    const label =
                        element.querySelector(
                            ".auto-section-toggle-label"
                        );

                    if (label) {
                        setText(
                            label,
                            "DISABLED"
                        );
                    }
                }
            );

            const runtimeTargets =
                root.querySelectorAll(
                    "[data-automation-id]"
                );

            runtimeTargets.forEach(
                (element) => {
                    element.dataset
                        .runtimeState =
                        "STOPPED";

                    element.classList.remove(
                        "is-running",
                        "is-error",
                        "is-paused",
                        "is-starting",
                        "is-stopping",
                        "is-disabled"
                    );

                    element.classList.add(
                        "is-stopped"
                    );

                    const badge =
                        element.querySelector(
                            ".auto-runtime-badge"
                        );

                    if (badge) {
                        badge.dataset
                            .runtimeState =
                            "STOPPED";

                        setText(
                            badge,
                            "STOPPED"
                        );
                    }
                }
            );
        }
    }


    /* ============================================================
       DISPOSE
       ============================================================ */

    function dispose() {
        const root =
            observedRoot ||
            getRoot();

        disconnectObserver();

        if (root) {
            unbindRoot(root);
        }

        initialized =
            false;
    }


    /* ============================================================
       AUTO BOOT
       ============================================================ */

    function bootWhenReady() {
        if (
            document.readyState ===
            "loading"
        ) {
            document.addEventListener(
                "DOMContentLoaded",
                () => {
                    initialize();
                },
                {
                    once: true
                }
            );

            return;
        }

        initialize();
    }


    bootWhenReady();


    /* ============================================================
       PUBLIC API
       ============================================================ */

    return {
        initialize,

        init:
            initialize,

        refresh,

        dispose,

        reset,

        setActiveSection,

        setEngineState,

        setSectionState,

        setSectionRunning,

        setRuntimeState
    };

})();