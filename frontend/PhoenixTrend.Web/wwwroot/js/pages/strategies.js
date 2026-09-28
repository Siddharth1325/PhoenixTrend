/* ============================================================
   PHOENIXTREND STRATEGIES
   wwwroot/js/strategies.js

   Premium interaction layer only.

   IMPORTANT:
   - Blazor owns strategy data.
   - Blazor owns API calls.
   - Blazor owns Create / Configure / View / Enable / Delete.
   - JavaScript enhances presentation and accessibility only.
   ============================================================ */

window.PhoenixPage_strategies = () => {
    try {
        if (
            window.PhoenixPremium &&
            typeof window.PhoenixPremium.init === "function"
        ) {
            window.PhoenixPremium.init("strategies");
        }

        window.PhoenixStrategies.init();
    }
    catch (error) {
        console.error(
            "[PhoenixTrend Strategies] Page initialization failed.",
            error
        );
    }
};


window.PhoenixStrategies = (() => {

    "use strict";


    /* ============================================================
       STATE
       ============================================================ */

    let initialized = false;
    let observer = null;
    let observerFrame = 0;
    let resizeFrame = 0;
    let lastSelectedCard = null;


    /* ============================================================
       SELECTORS
       ============================================================ */

    const SELECTORS = {

        root:
            ".pt-strategies",

        hero:
            ".strategies-hero",

        card:
            ".strategy-card",

        tab:
            ".strategy-tab",

        tabs:
            ".strategy-tabs",

        tabsShell:
            ".strategy-tabs-shell",

        primaryAction:
            ".strategy-primary-action",

        secondaryAction:
            ".strategy-secondary-action",

        configureAction:
            ".strategy-configure-button",

        ghostAction:
            ".strategy-ghost-action",

        dangerAction:
            ".strategy-danger-action",

        inspector:
            ".strategy-inspector",

        summaryCard:
            ".strategy-summary-card",

        modalBackdrop:
            ".strategy-modal-backdrop",

        modal:
            ".strategy-modal",

        modalClose:
            ".strategy-modal-close",

        search:
            ".strategy-search-box input",

        searchBox:
            ".strategy-search-box",

        searchClear:
            ".strategy-search-clear",

        message:
            ".strategy-message",

        messageClose:
            ".strategy-message-close",

        libraryPanel:
            ".strategy-library-panel",

        strategyGrid:
            ".strategy-grid"
    };


    /* ============================================================
       INITIALIZATION
       ============================================================ */

    function init() {

        const root =
            document.querySelector(
                SELECTORS.root
            );

        if (!root) {
            return;
        }

        if (!initialized) {

            initialized = true;

            bindGlobalEvents();
            startObserver();
        }

        enhance(root);
    }


    /* ============================================================
       MAIN ENHANCEMENT PASS
       ============================================================ */

    function enhance(root) {

        if (!root) {
            return;
        }

        prepareRoot(root);

        prepareHero(root);

        prepareCards(root);

        prepareTabs(root);

        prepareActions(root);

        prepareSummaryCards(root);

        prepareInspector(root);

        prepareSearch(root);

        prepareMessages(root);

        prepareModals(root);

        preparePanels(root);

        syncSelectedCard(root);

        syncAccessibility(root);

        syncModalState(root);
    }


    /* ============================================================
       ROOT
       ============================================================ */

    function prepareRoot(root) {

        if (
            root.dataset.phoenixRootReady ===
            "true"
        ) {
            return;
        }

        root.dataset.phoenixRootReady =
            "true";

        root.classList.add(
            "phoenix-strategies-ready"
        );
    }


    /* ============================================================
       HERO
       ============================================================ */

    function prepareHero(root) {

        const hero =
            root.querySelector(
                SELECTORS.hero
            );

        if (!hero) {
            return;
        }

        if (
            hero.dataset.phoenixHeroReady ===
            "true"
        ) {
            return;
        }

        hero.dataset.phoenixHeroReady =
            "true";

        hero.style.setProperty(
            "--hero-x",
            "72%"
        );

        hero.style.setProperty(
            "--hero-y",
            "38%"
        );

        hero.addEventListener(
            "pointermove",
            handleHeroPointerMove,
            {
                passive: true
            }
        );

        hero.addEventListener(
            "pointerleave",
            handleHeroPointerLeave,
            {
                passive: true
            }
        );
    }


    function handleHeroPointerMove(event) {

        if (prefersReducedMotion()) {
            return;
        }

        if (
            event.pointerType &&
            event.pointerType !== "mouse"
        ) {
            return;
        }

        const hero =
            event.currentTarget;

        if (!hero) {
            return;
        }

        const rect =
            hero.getBoundingClientRect();

        if (
            rect.width <= 0 ||
            rect.height <= 0
        ) {
            return;
        }

        const x =
            clamp(
                (
                    (
                        event.clientX -
                        rect.left
                    ) /
                    rect.width
                ) * 100,
                0,
                100
            );

        const y =
            clamp(
                (
                    (
                        event.clientY -
                        rect.top
                    ) /
                    rect.height
                ) * 100,
                0,
                100
            );

        hero.style.setProperty(
            "--hero-x",
            `${x}%`
        );

        hero.style.setProperty(
            "--hero-y",
            `${y}%`
        );
    }


    function handleHeroPointerLeave(event) {

        const hero =
            event.currentTarget;

        if (!hero) {
            return;
        }

        hero.style.setProperty(
            "--hero-x",
            "72%"
        );

        hero.style.setProperty(
            "--hero-y",
            "38%"
        );
    }


    /* ============================================================
       STRATEGY CARDS
       ============================================================ */

    function prepareCards(root) {

        const cards =
            root.querySelectorAll(
                SELECTORS.card
            );

        cards.forEach(
            (card, index) => {

                card.style.setProperty(
                    "--strategy-index",
                    String(index)
                );

                if (
                    card.dataset
                        .phoenixStrategyReady ===
                    "true"
                ) {
                    return;
                }

                card.dataset
                    .phoenixStrategyReady =
                    "true";

                card.style.setProperty(
                    "--mouse-x",
                    "50%"
                );

                card.style.setProperty(
                    "--mouse-y",
                    "50%"
                );

                card.setAttribute(
                    "role",
                    "button"
                );

                if (
                    !card.hasAttribute(
                        "tabindex"
                    )
                ) {
                    card.setAttribute(
                        "tabindex",
                        "0"
                    );
                }

                card.addEventListener(
                    "pointermove",
                    handleCardPointerMove,
                    {
                        passive: true
                    }
                );

                card.addEventListener(
                    "pointerleave",
                    handleCardPointerLeave,
                    {
                        passive: true
                    }
                );

                card.addEventListener(
                    "keydown",
                    handleCardKeyboard
                );

                card.addEventListener(
                    "pointerdown",
                    handlePressStart,
                    {
                        passive: true
                    }
                );

                card.addEventListener(
                    "pointerup",
                    handlePressEnd,
                    {
                        passive: true
                    }
                );

                card.addEventListener(
                    "pointercancel",
                    handlePressEnd,
                    {
                        passive: true
                    }
                );
            }
        );
    }


    function handleCardPointerMove(event) {

        if (
            event.pointerType &&
            event.pointerType !== "mouse"
        ) {
            return;
        }

        const card =
            event.currentTarget;

        if (!card) {
            return;
        }

        const rect =
            card.getBoundingClientRect();

        if (
            !rect.width ||
            !rect.height
        ) {
            return;
        }

        const x =
            clamp(
                (
                    (
                        event.clientX -
                        rect.left
                    ) /
                    rect.width
                ) * 100,
                0,
                100
            );

        const y =
            clamp(
                (
                    (
                        event.clientY -
                        rect.top
                    ) /
                    rect.height
                ) * 100,
                0,
                100
            );

        card.style.setProperty(
            "--mouse-x",
            `${x}%`
        );

        card.style.setProperty(
            "--mouse-y",
            `${y}%`
        );
    }


    function handleCardPointerLeave(event) {

        const card =
            event.currentTarget;

        if (!card) {
            return;
        }

        card.style.setProperty(
            "--mouse-x",
            "50%"
        );

        card.style.setProperty(
            "--mouse-y",
            "50%"
        );

        card.classList.remove(
            "is-pressed"
        );
    }


    function handleCardKeyboard(event) {

        if (
            event.key !== "Enter" &&
            event.key !== " "
        ) {
            return;
        }

        const card =
            event.currentTarget;

        if (!card) {
            return;
        }

        /*
         * Do not synthesize a click if the
         * keyboard event originated from a
         * real child control.
         */
        if (
            event.target !== card
        ) {
            return;
        }

        event.preventDefault();

        card.click();
    }


    function handlePressStart(event) {

        const element =
            event.currentTarget;

        if (!element) {
            return;
        }

        element.classList.add(
            "is-pressed"
        );
    }


    function handlePressEnd(event) {

        const element =
            event.currentTarget;

        if (!element) {
            return;
        }

        window.setTimeout(
            () => {
                element.classList.remove(
                    "is-pressed"
                );
            },
            90
        );
    }


    /* ============================================================
       TABS
       ============================================================ */

    function prepareTabs(root) {

        const tabs =
            root.querySelectorAll(
                SELECTORS.tab
            );

        tabs.forEach(
            (tab, index) => {

                tab.setAttribute(
                    "role",
                    "tab"
                );

                tab.dataset.tabIndex =
                    String(index);

                if (
                    tab.dataset
                        .phoenixTabReady ===
                    "true"
                ) {
                    return;
                }

                tab.dataset
                    .phoenixTabReady =
                    "true";

                tab.addEventListener(
                    "click",
                    () => {

                        requestAnimationFrame(
                            () => {
                                keepActiveTabVisible(
                                    root
                                );
                            }
                        );
                    }
                );

                tab.addEventListener(
                    "pointerdown",
                    handlePressStart,
                    {
                        passive: true
                    }
                );

                tab.addEventListener(
                    "pointerup",
                    handlePressEnd,
                    {
                        passive: true
                    }
                );
            }
        );

        const tabsContainer =
            root.querySelector(
                SELECTORS.tabs
            );

        if (tabsContainer) {

            tabsContainer.setAttribute(
                "role",
                "tablist"
            );

            tabsContainer.setAttribute(
                "aria-label",
                "Strategy categories"
            );
        }

        keepActiveTabVisible(
            root,
            false
        );
    }


    function keepActiveTabVisible(
        root,
        animate = true
    ) {

        if (!root) {
            return;
        }

        const activeTab =
            root.querySelector(
                `${SELECTORS.tab}.active`
            );

        if (!activeTab) {
            return;
        }

        root.querySelectorAll(
            SELECTORS.tab
        ).forEach(
            tab => {

                const isActive =
                    tab === activeTab;

                tab.setAttribute(
                    "aria-selected",
                    isActive
                        ? "true"
                        : "false"
                );

                tab.setAttribute(
                    "tabindex",
                    isActive
                        ? "0"
                        : "-1"
                );
            }
        );

        try {

            activeTab.scrollIntoView({
                behavior:
                    animate &&
                    !prefersReducedMotion()
                        ? "smooth"
                        : "auto",

                block:
                    "nearest",

                inline:
                    "nearest"
            });
        }
        catch {

            activeTab.scrollIntoView();
        }
    }


    /* ============================================================
       ACTION BUTTONS
       ============================================================ */

    function prepareActions(root) {

        const selector = [
            SELECTORS.primaryAction,
            SELECTORS.secondaryAction,
            SELECTORS.configureAction,
            SELECTORS.ghostAction,
            SELECTORS.dangerAction
        ].join(",");

        const actions =
            root.querySelectorAll(
                selector
            );

        actions.forEach(
            button => {

                if (
                    button.dataset
                        .phoenixActionReady ===
                    "true"
                ) {
                    return;
                }

                button.dataset
                    .phoenixActionReady =
                    "true";

                /*
                 * We intentionally do NOT
                 * preventDefault(), stopPropagation()
                 * or replace onclick.
                 *
                 * Blazor must remain the owner of
                 * every functional action.
                 */

                button.addEventListener(
                    "pointerdown",
                    handlePressStart,
                    {
                        passive: true
                    }
                );

                button.addEventListener(
                    "pointerup",
                    handlePressEnd,
                    {
                        passive: true
                    }
                );

                button.addEventListener(
                    "pointercancel",
                    handlePressEnd,
                    {
                        passive: true
                    }
                );

                button.addEventListener(
                    "click",
                    handleActionFeedback
                );
            }
        );
    }


    function handleActionFeedback(event) {

        const button =
            event.currentTarget;

        if (
            !button ||
            button.disabled
        ) {
            return;
        }

        createButtonRipple(
            button,
            event
        );

        requestAnimationFrame(
            () => {

                requestAnimationFrame(
                    () => {

                        const root =
                            document.querySelector(
                                SELECTORS.root
                            );

                        if (!root) {
                            return;
                        }

                        syncSelectedCard(
                            root
                        );

                        syncModalState(
                            root
                        );
                    }
                );
            }
        );
    }


    function createButtonRipple(
        button,
        event
    ) {

        if (
            prefersReducedMotion()
        ) {
            return;
        }

        if (
            !event ||
            typeof event.clientX !== "number" ||
            typeof event.clientY !== "number"
        ) {
            return;
        }

        const rect =
            button.getBoundingClientRect();

        if (
            !rect.width ||
            !rect.height
        ) {
            return;
        }

        const size =
            Math.max(
                rect.width,
                rect.height
            ) * 1.45;

        const ripple =
            document.createElement(
                "span"
            );

        ripple.className =
            "phoenix-action-ripple";

        ripple.style.width =
            `${size}px`;

        ripple.style.height =
            `${size}px`;

        ripple.style.left =
            `${
                event.clientX -
                rect.left -
                size / 2
            }px`;

        ripple.style.top =
            `${
                event.clientY -
                rect.top -
                size / 2
            }px`;

        /*
         * Inline styles make the effect work
         * even without adding another CSS rule.
         */

        ripple.style.position =
            "absolute";

        ripple.style.pointerEvents =
            "none";

        ripple.style.borderRadius =
            "999px";

        ripple.style.background =
            "rgba(255,255,255,0.18)";

        ripple.style.transform =
            "scale(0)";

        ripple.style.opacity =
            "0.8";

        ripple.style.transition =
            "transform 420ms ease, opacity 420ms ease";

        const computed =
            window.getComputedStyle(
                button
            );

        if (
            computed.position ===
            "static"
        ) {
            button.style.position =
                "relative";
        }

        button.style.overflow =
            "hidden";

        button.appendChild(
            ripple
        );

        requestAnimationFrame(
            () => {

                ripple.style.transform =
                    "scale(1)";

                ripple.style.opacity =
                    "0";
            }
        );

        window.setTimeout(
            () => {
                ripple.remove();
            },
            460
        );
    }


    /* ============================================================
       SUMMARY CARDS
       ============================================================ */

    function prepareSummaryCards(root) {

        const cards =
            root.querySelectorAll(
                SELECTORS.summaryCard
            );

        cards.forEach(
            (card, index) => {

                card.style.setProperty(
                    "--summary-index",
                    String(index)
                );

                if (
                    card.dataset
                        .phoenixSummaryReady ===
                    "true"
                ) {
                    return;
                }

                card.dataset
                    .phoenixSummaryReady =
                    "true";

                card.addEventListener(
                    "pointermove",
                    handleSummaryPointerMove,
                    {
                        passive: true
                    }
                );

                card.addEventListener(
                    "pointerleave",
                    handleSummaryPointerLeave,
                    {
                        passive: true
                    }
                );
            }
        );
    }


    function handleSummaryPointerMove(
        event
    ) {

        if (
            event.pointerType &&
            event.pointerType !== "mouse"
        ) {
            return;
        }

        const card =
            event.currentTarget;

        if (!card) {
            return;
        }

        const rect =
            card.getBoundingClientRect();

        if (
            !rect.width ||
            !rect.height
        ) {
            return;
        }

        const x =
            clamp(
                (
                    (
                        event.clientX -
                        rect.left
                    ) /
                    rect.width
                ) * 100,
                0,
                100
            );

        const y =
            clamp(
                (
                    (
                        event.clientY -
                        rect.top
                    ) /
                    rect.height
                ) * 100,
                0,
                100
            );

        card.style.setProperty(
            "--summary-x",
            `${x}%`
        );

        card.style.setProperty(
            "--summary-y",
            `${y}%`
        );
    }


    function handleSummaryPointerLeave(
        event
    ) {

        const card =
            event.currentTarget;

        if (!card) {
            return;
        }

        card.style.removeProperty(
            "--summary-x"
        );

        card.style.removeProperty(
            "--summary-y"
        );
    }


    /* ============================================================
       SELECTED CARD
       ============================================================ */

    function syncSelectedCard(root) {

        if (!root) {
            return;
        }

        const selected =
            root.querySelector(
                `${SELECTORS.card}.selected`
            );

        root.querySelectorAll(
            SELECTORS.card
        ).forEach(
            card => {

                const isSelected =
                    card === selected;

                card.setAttribute(
                    "aria-selected",
                    isSelected
                        ? "true"
                        : "false"
                );
            }
        );

        if (!selected) {

            lastSelectedCard =
                null;

            return;
        }

        if (
            selected ===
            lastSelectedCard
        ) {
            return;
        }

        lastSelectedCard =
            selected;

        selected.classList.remove(
            "selection-pulse"
        );

        void selected.offsetWidth;

        selected.classList.add(
            "selection-pulse"
        );

        window.setTimeout(
            () => {

                if (
                    selected &&
                    selected.isConnected
                ) {
                    selected.classList.remove(
                        "selection-pulse"
                    );
                }
            },
            520
        );
    }


    /* ============================================================
       INSPECTOR
       ============================================================ */

    function prepareInspector(root) {

        const inspector =
            root.querySelector(
                SELECTORS.inspector
            );

        if (!inspector) {
            return;
        }

        if (
            inspector.dataset
                .phoenixInspectorReady ===
            "true"
        ) {
            return;
        }

        inspector.dataset
            .phoenixInspectorReady =
            "true";

        inspector.setAttribute(
            "aria-live",
            "polite"
        );

        inspector.setAttribute(
            "aria-atomic",
            "false"
        );
    }


    /* ============================================================
       SEARCH
       ============================================================ */

    function prepareSearch(root) {

        const input =
            root.querySelector(
                SELECTORS.search
            );

        if (!input) {
            return;
        }

        if (
            input.dataset
                .phoenixSearchReady !==
            "true"
        ) {

            input.dataset
                .phoenixSearchReady =
                "true";

            input.setAttribute(
                "autocomplete",
                "off"
            );

            input.setAttribute(
                "spellcheck",
                "false"
            );

            input.setAttribute(
                "aria-label",
                "Search strategies"
            );

            input.addEventListener(
                "focus",
                () => {

                    const box =
                        input.closest(
                            SELECTORS.searchBox
                        );

                    if (box) {
                        box.classList.add(
                            "is-focused"
                        );
                    }
                }
            );

            input.addEventListener(
                "blur",
                () => {

                    const box =
                        input.closest(
                            SELECTORS.searchBox
                        );

                    if (box) {
                        box.classList.remove(
                            "is-focused"
                        );
                    }
                }
            );

            input.addEventListener(
                "keydown",
                event => {

                    if (
                        event.key ===
                        "Escape"
                    ) {
                        input.blur();
                    }
                }
            );
        }

        const clearButton =
            root.querySelector(
                SELECTORS.searchClear
            );

        if (
            clearButton &&
            clearButton.dataset
                .phoenixSearchClearReady !==
            "true"
        ) {

            clearButton.dataset
                .phoenixSearchClearReady =
                "true";

            clearButton.setAttribute(
                "aria-label",
                "Clear strategy search"
            );
        }
    }


    /* ============================================================
       MESSAGES
       ============================================================ */

    function prepareMessages(root) {

        root.querySelectorAll(
            SELECTORS.message
        ).forEach(
            message => {

                if (
                    message.dataset
                        .phoenixMessageReady ===
                    "true"
                ) {
                    return;
                }

                message.dataset
                    .phoenixMessageReady =
                    "true";

                message.setAttribute(
                    "role",
                    message.classList.contains(
                        "error"
                    )
                        ? "alert"
                        : "status"
                );
            }
        );

        root.querySelectorAll(
            SELECTORS.messageClose
        ).forEach(
            button => {

                if (
                    button.dataset
                        .phoenixMessageCloseReady ===
                    "true"
                ) {
                    return;
                }

                button.dataset
                    .phoenixMessageCloseReady =
                    "true";

                button.setAttribute(
                    "aria-label",
                    "Dismiss message"
                );
            }
        );
    }


    /* ============================================================
       MODALS
       ============================================================ */

    function prepareModals(root) {

        root.querySelectorAll(
            SELECTORS.modalBackdrop
        ).forEach(
            backdrop => {

                if (
                    backdrop.dataset
                        .phoenixModalBackdropReady ===
                    "true"
                ) {
                    return;
                }

                backdrop.dataset
                    .phoenixModalBackdropReady =
                    "true";

                backdrop.setAttribute(
                    "role",
                    "presentation"
                );
            }
        );

        root.querySelectorAll(
            SELECTORS.modal
        ).forEach(
            modal => {

                if (
                    modal.dataset
                        .phoenixModalReady ===
                    "true"
                ) {
                    return;
                }

                modal.dataset
                    .phoenixModalReady =
                    "true";

                modal.setAttribute(
                    "role",
                    "dialog"
                );

                modal.setAttribute(
                    "aria-modal",
                    "true"
                );

                modal.setAttribute(
                    "tabindex",
                    "-1"
                );
            }
        );

        root.querySelectorAll(
            SELECTORS.modalClose
        ).forEach(
            closeButton => {

                if (
                    closeButton.dataset
                        .phoenixModalCloseReady ===
                    "true"
                ) {
                    return;
                }

                closeButton.dataset
                    .phoenixModalCloseReady =
                    "true";

                closeButton.setAttribute(
                    "aria-label",
                    "Close dialog"
                );
            }
        );
    }


    function syncModalState(root) {

        if (!root) {
            return;
        }

        const modal =
            root.querySelector(
                SELECTORS.modal
            );

        const hasModal =
            Boolean(modal);

        document.documentElement
            .classList.toggle(
                "phoenix-strategy-modal-open",
                hasModal
            );

        document.body
            .classList.toggle(
                "phoenix-strategy-modal-open",
                hasModal
            );

        if (!hasModal) {
            return;
        }

        if (
            modal.dataset
                .phoenixAutoFocused ===
            "true"
        ) {
            return;
        }

        modal.dataset
            .phoenixAutoFocused =
            "true";

        requestAnimationFrame(
            () => {

                if (
                    !modal.isConnected
                ) {
                    return;
                }

                const preferred =
                    modal.querySelector(
                        "input:not([disabled]), select:not([disabled]), button:not([disabled])"
                    );

                if (preferred) {
                    preferred.focus({
                        preventScroll: true
                    });
                }
                else {
                    modal.focus({
                        preventScroll: true
                    });
                }
            }
        );
    }


    /* ============================================================
       PANELS
       ============================================================ */

    function preparePanels(root) {

        const library =
            root.querySelector(
                SELECTORS.libraryPanel
            );

        if (
            library &&
            library.dataset
                .phoenixPanelReady !==
            "true"
        ) {

            library.dataset
                .phoenixPanelReady =
                "true";
        }

        const grid =
            root.querySelector(
                SELECTORS.strategyGrid
            );

        if (
            grid &&
            grid.dataset
                .phoenixGridReady !==
            "true"
        ) {

            grid.dataset
                .phoenixGridReady =
                "true";

            grid.setAttribute(
                "role",
                "list"
            );
        }

        root.querySelectorAll(
            SELECTORS.card
        ).forEach(
            card => {

                card.setAttribute(
                    "aria-roledescription",
                    "strategy"
                );
            }
        );
    }


    /* ============================================================
       ACCESSIBILITY
       ============================================================ */

    function syncAccessibility(root) {

        if (!root) {
            return;
        }

        root.querySelectorAll(
            "button"
        ).forEach(
            button => {

                if (
                    !button.hasAttribute(
                        "type"
                    )
                ) {
                    button.setAttribute(
                        "type",
                        "button"
                    );
                }
            }
        );

        const activeTab =
            root.querySelector(
                `${SELECTORS.tab}.active`
            );

        root.querySelectorAll(
            SELECTORS.tab
        ).forEach(
            tab => {

                const active =
                    tab === activeTab;

                tab.setAttribute(
                    "aria-selected",
                    active
                        ? "true"
                        : "false"
                );
            }
        );
    }


    /* ============================================================
       KEYBOARD
       ============================================================ */

    function bindGlobalEvents() {

        document.addEventListener(
            "keydown",
            handleKeyboard
        );

        window.addEventListener(
            "resize",
            handleResize,
            {
                passive: true
            }
        );

        window.addEventListener(
            "pageshow",
            () => {

                const root =
                    document.querySelector(
                        SELECTORS.root
                    );

                if (root) {
                    enhance(root);
                }
            }
        );
    }


    function handleKeyboard(event) {

        const root =
            document.querySelector(
                SELECTORS.root
            );

        if (!root) {
            return;
        }


        /*
         * ESCAPE
         *
         * We do not close the Blazor modal
         * ourselves because that would desync
         * JavaScript DOM state from Razor state.
         *
         * If a real Blazor close button exists,
         * trigger that button.
         */

        if (
            event.key ===
            "Escape"
        ) {

            const modal =
                root.querySelector(
                    SELECTORS.modal
                );

            if (modal) {

                const closeButton =
                    modal.querySelector(
                        SELECTORS.modalClose
                    );

                if (closeButton) {

                    event.preventDefault();

                    closeButton.click();

                    return;
                }
            }
        }


        /*
         * TAB NAVIGATION
         */

        if (
            event.key !== "ArrowLeft" &&
            event.key !== "ArrowRight" &&
            event.key !== "Home" &&
            event.key !== "End"
        ) {
            return;
        }

        const focused =
            document.activeElement;

        if (
            !focused ||
            !focused.classList ||
            !focused.classList.contains(
                "strategy-tab"
            )
        ) {
            return;
        }

        const tabs =
            Array.from(
                root.querySelectorAll(
                    SELECTORS.tab
                )
            );

        if (!tabs.length) {
            return;
        }

        const currentIndex =
            tabs.indexOf(
                focused
            );

        if (
            currentIndex < 0
        ) {
            return;
        }

        event.preventDefault();

        let nextIndex =
            currentIndex;

        if (
            event.key ===
            "Home"
        ) {
            nextIndex = 0;
        }
        else if (
            event.key ===
            "End"
        ) {
            nextIndex =
                tabs.length - 1;
        }
        else {

            const direction =
                event.key ===
                "ArrowRight"
                    ? 1
                    : -1;

            nextIndex =
                currentIndex +
                direction;

            if (
                nextIndex < 0
            ) {
                nextIndex =
                    tabs.length - 1;
            }

            if (
                nextIndex >=
                tabs.length
            ) {
                nextIndex = 0;
            }
        }

        const nextTab =
            tabs[nextIndex];

        if (!nextTab) {
            return;
        }

        nextTab.focus();

        /*
         * Click invokes the existing Blazor
         * @onclick category handler.
         */

        nextTab.click();
    }


    /* ============================================================
       RESIZE
       ============================================================ */

    function handleResize() {

        if (resizeFrame) {
            cancelAnimationFrame(
                resizeFrame
            );
        }

        resizeFrame =
            requestAnimationFrame(
                () => {

                    resizeFrame = 0;

                    const root =
                        document.querySelector(
                            SELECTORS.root
                        );

                    if (!root) {
                        return;
                    }

                    keepActiveTabVisible(
                        root,
                        false
                    );
                }
            );
    }


    /* ============================================================
       BLAZOR DOM OBSERVER
       ============================================================ */

    function startObserver() {

        if (observer) {
            return;
        }

        observer =
            new MutationObserver(
                handleMutations
            );

        observer.observe(
            document.body,
            {
                childList:
                    true,

                subtree:
                    true,

                attributes:
                    true,

                attributeFilter: [
                    "class",
                    "disabled"
                ]
            }
        );
    }


    function handleMutations(
        mutations
    ) {

        let relevant =
            false;

        for (
            const mutation
            of mutations
        ) {

            if (
                mutation.type ===
                "childList" &&
                (
                    mutation.addedNodes
                        .length > 0 ||
                    mutation.removedNodes
                        .length > 0
                )
            ) {

                relevant = true;

                break;
            }

            if (
                mutation.type ===
                "attributes"
            ) {

                const target =
                    mutation.target;

                if (
                    target &&
                    target.closest &&
                    target.closest(
                        SELECTORS.root
                    )
                ) {

                    relevant = true;

                    break;
                }
            }
        }

        if (!relevant) {
            return;
        }

        scheduleEnhancement();
    }


    function scheduleEnhancement() {

        if (observerFrame) {
            return;
        }

        observerFrame =
            requestAnimationFrame(
                () => {

                    observerFrame = 0;

                    const root =
                        document.querySelector(
                            SELECTORS.root
                        );

                    if (!root) {

                        document.documentElement
                            .classList.remove(
                                "phoenix-strategy-modal-open"
                            );

                        document.body
                            .classList.remove(
                                "phoenix-strategy-modal-open"
                            );

                        return;
                    }

                    enhance(root);
                }
            );
    }


    /* ============================================================
       HELPERS
       ============================================================ */

    function clamp(
        value,
        minimum,
        maximum
    ) {

        return Math.min(
            maximum,
            Math.max(
                minimum,
                value
            )
        );
    }


    function prefersReducedMotion() {

        return Boolean(
            window.matchMedia &&
            window.matchMedia(
                "(prefers-reduced-motion: reduce)"
            ).matches
        );
    }


    /* ============================================================
       CLEANUP
       ============================================================ */

    function destroy() {

        if (observer) {

            observer.disconnect();

            observer = null;
        }

        if (observerFrame) {

            cancelAnimationFrame(
                observerFrame
            );

            observerFrame = 0;
        }

        if (resizeFrame) {

            cancelAnimationFrame(
                resizeFrame
            );

            resizeFrame = 0;
        }

        document.removeEventListener(
            "keydown",
            handleKeyboard
        );

        window.removeEventListener(
            "resize",
            handleResize
        );

        document.documentElement
            .classList.remove(
                "phoenix-strategy-modal-open"
            );

        document.body
            .classList.remove(
                "phoenix-strategy-modal-open"
            );

        initialized =
            false;

        lastSelectedCard =
            null;
    }


    /* ============================================================
       PUBLIC API
       ============================================================ */

    return {

        init,

        refresh() {

            const root =
                document.querySelector(
                    SELECTORS.root
                );

            if (root) {
                enhance(root);
            }
        },

        destroy
    };

})();