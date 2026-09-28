/* frontend/wwwroot/js/trade.js
   PhoenixTrend Manual Trade — premium runtime enhancement layer
   - Premium Phosphor icon hydration
   - Real symbol-logo hydration from existing logo elements/data attributes
   - Accessible tabs, controls, tables and tooltips
   - Symbol-strip interaction
   - Responsive/compact behavior
   - Mutation-safe Blazor lifecycle handling
   - No fabricated market/trading data
*/

(() => {
    "use strict";

    const PAGE = "trade";
    const ROOT_SELECTOR = ".pt-trade";

    const state = {
        mounted: false,
        host: null,
        observer: null,
        resizeObserver: null,
        bootObserver: null,
        disposers: [],
        logoFailures: new Set()
    };

    const q = (selector, scope = document) =>
        scope?.querySelector?.(selector) ?? null;

    const qa = (selector, scope = document) =>
        scope?.querySelectorAll
            ? Array.from(scope.querySelectorAll(selector))
            : [];

    const root = () => q(ROOT_SELECTOR);

    const escapeCss = (value) => {
        const text = String(value ?? "");

        if (window.CSS?.escape) {
            return window.CSS.escape(text);
        }

        return text.replace(
            /[^a-zA-Z0-9_-]/g,
            (character) =>
                `\\${character.codePointAt(0).toString(16)} `
        );
    };

    const normalizeText = (value) =>
        String(value ?? "")
            .trim()
            .replace(/\s+/g, " ");

    const normalizeSymbol = (value) =>
        normalizeText(value)
            .toUpperCase()
            .replace(/^\$/, "");

    const normalizeAssetClass = (value) => {
        const normalized = normalizeText(value)
            .toLowerCase()
            .replace(/[\s_-]+/g, "");

        const aliases = {
            stock: "stocks",
            stocks: "stocks",
            equity: "stocks",
            equities: "stocks",

            etf: "etfs",
            etfs: "etfs",

            option: "options",
            options: "options",

            crypto: "crypto",
            cryptocurrency: "crypto",
            cryptocurrencies: "crypto",

            forex: "forex",
            fx: "forex",

            bond: "bonds",
            bonds: "bonds",
            fixedincome: "bonds"
        };

        return aliases[normalized] || normalized || "stocks";
    };

    const clamp = (value, min, max) =>
        Math.min(max, Math.max(min, value));

    const raf = (callback) =>
        window.requestAnimationFrame(callback);

    const cancelRaf = (handle) => {
        if (handle) {
            window.cancelAnimationFrame(handle);
        }
    };

    const on = (
        target,
        eventName,
        handler,
        options
    ) => {
        if (!target?.addEventListener) {
            return () => {};
        }

        target.addEventListener(
            eventName,
            handler,
            options
        );

        const dispose = () => {
            target.removeEventListener(
                eventName,
                handler,
                options
            );
        };

        state.disposers.push(dispose);

        return dispose;
    };

    const setAttributeIfMissing = (
        element,
        name,
        value
    ) => {
        if (!element || element.hasAttribute(name)) {
            return;
        }

        element.setAttribute(
            name,
            String(value)
        );
    };

    const safeClosest = (
        element,
        selector
    ) => {
        if (!(element instanceof Element)) {
            return null;
        }

        try {
            return element.closest(selector);
        }
        catch {
            return null;
        }
    };

    const ICONS = Object.freeze({
        refresh: "ph-arrows-clockwise",
        reload: "ph-arrows-clockwise",
        sync: "ph-arrows-clockwise",

        search: "ph-magnifying-glass",
        filter: "ph-funnel",
        settings: "ph-gear-six",
        configure: "ph-sliders-horizontal",

        chart: "ph-chart-candlestick",
        charts: "ph-chart-candlestick",
        candlestick: "ph-chart-candlestick",
        analytics: "ph-chart-line-up",
        performance: "ph-trend-up",
        trend: "ph-trend-up",

        portfolio: "ph-briefcase",
        positions: "ph-briefcase",
        position: "ph-briefcase",

        orders: "ph-list-checks",
        order: "ph-receipt",
        activity: "ph-clock-counter-clockwise",
        history: "ph-clock-counter-clockwise",

        risk: "ph-shield-check",
        safety: "ph-shield-check",
        protected: "ph-shield-check",

        buy: "ph-arrow-circle-up-right",
        sell: "ph-arrow-circle-down-right",
        trade: "ph-swap",
        submit: "ph-paper-plane-tilt",
        send: "ph-paper-plane-tilt",
        confirm: "ph-check-circle",
        cancel: "ph-x-circle",
        close: "ph-x",

        connected: "ph-plugs-connected",
        connect: "ph-plugs",
        disconnected: "ph-plugs",
        disconnect: "ph-plugs",

        account: "ph-wallet",
        balance: "ph-wallet",
        buyingpower: "ph-coins",
        equity: "ph-chart-line-up",
        pnl: "ph-currency-dollar",
        profit: "ph-trend-up",
        loss: "ph-trend-down",

        stock: "ph-chart-line-up",
        stocks: "ph-chart-line-up",
        equityasset: "ph-chart-line-up",
        etf: "ph-chart-pie-slice",
        etfs: "ph-chart-pie-slice",
        option: "ph-git-branch",
        options: "ph-git-branch",
        crypto: "ph-currency-btc",
        forex: "ph-currency-circle-dollar",
        bonds: "ph-bank",

        ai: "ph-sparkle",
        tradyai: "ph-sparkle",
        intelligence: "ph-brain",
        insight: "ph-lightbulb",
        insights: "ph-lightbulb",

        strategy: "ph-tree-structure",
        strategies: "ph-tree-structure",
        decision: "ph-git-diff",
        signal: "ph-broadcast",
        scanner: "ph-radar",
        market: "ph-globe-hemisphere-west",

        price: "ph-currency-dollar",
        volume: "ph-chart-bar",
        volatility: "ph-wave-sine",
        momentum: "ph-lightning",
        liquidity: "ph-drop",
        spread: "ph-arrows-left-right",

        target: "ph-crosshair",
        stop: "ph-stop-circle",
        stoploss: "ph-shield-warning",
        takeprofit: "ph-target",

        info: "ph-info",
        warning: "ph-warning",
        error: "ph-warning-octagon",
        success: "ph-check-circle",
        live: "ph-broadcast",
        lock: "ph-lock",
        unlock: "ph-lock-open",

        fullscreen: "ph-corners-out",
        exitfullscreen: "ph-corners-in",
        expand: "ph-corners-out",
        collapse: "ph-corners-in",

        plus: "ph-plus",
        add: "ph-plus",
        minus: "ph-minus",
        remove: "ph-minus",
        delete: "ph-trash",
        trash: "ph-trash",
        edit: "ph-pencil-simple",
        copy: "ph-copy",
        external: "ph-arrow-square-out",

        arrowup: "ph-arrow-up",
        arrowdown: "ph-arrow-down",
        arrowleft: "ph-arrow-left",
        arrowright: "ph-arrow-right",
        chevronup: "ph-caret-up",
        chevrondown: "ph-caret-down",
        chevronleft: "ph-caret-left",
        chevronright: "ph-caret-right"
    });

    const ASSET_ICONS = Object.freeze({
        stocks: "ph-chart-line-up",
        etfs: "ph-chart-pie-slice",
        options: "ph-git-branch",
        crypto: "ph-currency-btc",
        forex: "ph-currency-circle-dollar",
        bonds: "ph-bank"
    });

    function resolveIconName(value) {
        const key = normalizeText(value)
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, "");

        return ICONS[key] || null;
    }

    function iconElement(
        iconClass,
        options = {}
    ) {
        if (!iconClass) {
            return null;
        }

        const icon = document.createElement("i");

        icon.className = [
            "ph",
            iconClass,
            "pt-premium-icon",
            options.className || ""
        ]
            .filter(Boolean)
            .join(" ");

        icon.setAttribute(
            "aria-hidden",
            "true"
        );

        if (options.weight) {
            icon.dataset.phosphorWeight =
                options.weight;
        }

        return icon;
    }

    function ensureIcon(
        element,
        iconName,
        options = {}
    ) {
        if (!element || !iconName) {
            return null;
        }

        const existing = q(
            ":scope > .pt-premium-icon, :scope > i.ph, :scope > svg[data-phosphor-icon]",
            element
        );

        if (existing) {
            existing.classList.add(
                "pt-premium-icon"
            );

            return existing;
        }

        const iconClass =
            resolveIconName(iconName) ||
            iconName;

        if (!iconClass) {
            return null;
        }

        const icon = iconElement(
            iconClass,
            options
        );

        if (!icon) {
            return null;
        }

        if (options.position === "end") {
            element.appendChild(icon);
        }
        else {
            element.insertBefore(
                icon,
                element.firstChild
            );
        }

        element.classList.add(
            "pt-has-premium-icon"
        );

        return icon;
    }

    function hydrateExplicitIcons(host) {
        qa("[data-pt-icon]", host)
            .forEach((element) => {
                const name =
                    element.dataset.ptIcon;

                ensureIcon(
                    element,
                    name,
                    {
                        position:
                            element.dataset.ptIconPosition === "end"
                                ? "end"
                                : "start",
                        weight:
                            element.dataset.ptIconWeight ||
                            "regular"
                    }
                );
            });
    }

    function hydrateButtonIcons(host) {
        qa(
            "button, .pt-btn, .text-action, [role='button']",
            host
        ).forEach((button) => {
            if (
                button.dataset.noAutoIcon === "true" ||
                q(
                    ":scope > i.ph, :scope > .pt-premium-icon, :scope > svg",
                    button
                )
            ) {
                return;
            }

            const explicit =
                button.dataset.icon ||
                button.dataset.action ||
                button.getAttribute("aria-label") ||
                "";

            let iconName =
                resolveIconName(explicit);

            if (!iconName) {
                const text =
                    normalizeText(
                        button.textContent
                    ).toLowerCase();

                const candidates = [
                    ["refresh", "refresh"],
                    ["reload", "refresh"],
                    ["search", "search"],
                    ["filter", "filter"],
                    ["settings", "settings"],
                    ["configure", "settings"],
                    ["buy", "buy"],
                    ["sell", "sell"],
                    ["submit", "submit"],
                    ["send", "send"],
                    ["confirm", "confirm"],
                    ["cancel", "cancel"],
                    ["close", "close"],
                    ["connect", "connect"],
                    ["disconnect", "disconnect"],
                    ["fullscreen", "fullscreen"],
                    ["full screen", "fullscreen"],
                    ["expand", "expand"],
                    ["delete", "delete"],
                    ["remove", "remove"],
                    ["edit", "edit"],
                    ["add", "add"]
                ];

                for (const [
                    token,
                    candidate
                ] of candidates) {
                    if (
                        text === token ||
                        text.startsWith(`${token} `)
                    ) {
                        iconName =
                            resolveIconName(candidate);
                        break;
                    }
                }
            }

            if (iconName) {
                ensureIcon(
                    button,
                    iconName
                );
            }
        });
    }

    function hydrateMetricIcons(host) {
        qa(".metric-card", host)
            .forEach((card) => {
                let holder =
                    q(".metric-icon", card);

                if (!holder) {
                    return;
                }

                if (
                    q(
                        "i.ph, .pt-premium-icon, svg",
                        holder
                    )
                ) {
                    return;
                }

                const label =
                    q(
                        ".metric-label",
                        card
                    )?.textContent || "";

                const normalized =
                    normalizeText(label)
                        .toLowerCase();

                let iconName = null;

                if (
                    normalized.includes(
                        "buying power"
                    )
                ) {
                    iconName = "buyingpower";
                }
                else if (
                    normalized.includes(
                        "equity"
                    )
                ) {
                    iconName = "equity";
                }
                else if (
                    normalized.includes(
                        "p&l"
                    ) ||
                    normalized.includes(
                        "pnl"
                    ) ||
                    normalized.includes(
                        "profit"
                    )
                ) {
                    iconName = "pnl";
                }
                else if (
                    normalized.includes(
                        "position"
                    )
                ) {
                    iconName = "positions";
                }
                else if (
                    normalized.includes(
                        "order"
                    )
                ) {
                    iconName = "orders";
                }
                else if (
                    normalized.includes(
                        "risk"
                    )
                ) {
                    iconName = "risk";
                }
                else if (
                    normalized.includes(
                        "confidence"
                    )
                ) {
                    iconName = "decision";
                }
                else if (
                    normalized.includes(
                        "strategy"
                    )
                ) {
                    iconName = "strategy";
                }
                else if (
                    normalized.includes(
                        "signal"
                    )
                ) {
                    iconName = "signal";
                }
                else if (
                    normalized.includes(
                        "volume"
                    )
                ) {
                    iconName = "volume";
                }
                else if (
                    normalized.includes(
                        "price"
                    )
                ) {
                    iconName = "price";
                }

                if (iconName) {
                    ensureIcon(
                        holder,
                        iconName
                    );
                }
            });
    }

    function hydrateAssetIcons(host) {
        qa(
            "[data-asset-class], [data-asset-type]",
            host
        ).forEach((element) => {
            if (
                element.dataset.noAssetIcon ===
                "true"
            ) {
                return;
            }

            const raw =
                element.dataset.assetClass ||
                element.dataset.assetType;

            const asset =
                normalizeAssetClass(raw);

            const icon =
                ASSET_ICONS[asset];

            if (!icon) {
                return;
            }

            const target =
                q(
                    ".asset-icon, .pt-asset-icon",
                    element
                ) ||
                (
                    element.matches(
                        "button, [role='button']"
                    )
                        ? element
                        : null
                );

            if (target) {
                ensureIcon(
                    target,
                    icon
                );
            }
        });
    }

    function inferSymbolFromElement(element) {
        if (!element) {
            return "";
        }

        const direct =
            element.dataset.symbol ||
            element.getAttribute(
                "data-ticker"
            );

        if (direct) {
            return normalizeSymbol(direct);
        }

        const symbolNode =
            q(
                "[data-symbol], .symbol, .ticker, .symbol-name, .symbol-code, strong",
                element
            );

        if (!symbolNode) {
            return "";
        }

        const nested =
            symbolNode.dataset.symbol ||
            symbolNode.getAttribute(
                "data-ticker"
            ) ||
            symbolNode.textContent;

        return normalizeSymbol(nested)
            .split(/\s+/)[0];
    }

    function inferAssetFromElement(element) {
        if (!element) {
            return "stocks";
        }

        const source =
            element.dataset.assetClass ||
            element.dataset.assetType ||
            safeClosest(
                element,
                "[data-asset-class], [data-asset-type]"
            )?.dataset.assetClass ||
            safeClosest(
                element,
                "[data-asset-class], [data-asset-type]"
            )?.dataset.assetType ||
            "stocks";

        return normalizeAssetClass(source);
    }

    function createLogoShell(
        symbol,
        assetClass
    ) {
        const shell =
            document.createElement("span");

        shell.className =
            "pt-symbol-logo";

        shell.dataset.symbol =
            symbol;

        shell.dataset.assetClass =
            assetClass;

        shell.setAttribute(
            "aria-hidden",
            "true"
        );

        return shell;
    }

    function logoFallback(
        shell,
        symbol,
        assetClass
    ) {
        if (!shell) {
            return;
        }

        shell.replaceChildren();

        shell.classList.add(
            "is-fallback"
        );

        shell.classList.remove(
            "has-image"
        );

        const iconClass =
            ASSET_ICONS[
                normalizeAssetClass(
                    assetClass
                )
            ];

        if (iconClass) {
            const icon =
                iconElement(
                    iconClass,
                    {
                        className:
                            "pt-symbol-fallback-icon"
                    }
                );

            if (icon) {
                shell.appendChild(icon);
            }
        }

        const accessible =
            shell.closest(
                "[data-symbol], button, tr, .symbol-row, .symbol-card"
            );

        if (accessible) {
            setAttributeIfMissing(
                accessible,
                "aria-label",
                symbol
            );
        }
    }

    function bindLogoImage(
        shell,
        image,
        symbol,
        assetClass
    ) {
        if (!shell || !image) {
            return;
        }

        image.classList.add(
            "pt-symbol-logo-image"
        );

        image.alt = "";
        image.setAttribute(
            "aria-hidden",
            "true"
        );

        const failureKey =
            `${assetClass}:${symbol}:${image.src}`;

        const handleLoad = () => {
            shell.classList.add(
                "has-image"
            );

            shell.classList.remove(
                "is-fallback"
            );
        };

        const handleError = () => {
            state.logoFailures.add(
                failureKey
            );

            logoFallback(
                shell,
                symbol,
                assetClass
            );
        };

        image.addEventListener(
            "load",
            handleLoad,
            { once: true }
        );

        image.addEventListener(
            "error",
            handleError,
            { once: true }
        );

        if (
            image.complete &&
            image.naturalWidth > 0
        ) {
            handleLoad();
        }
        else if (
            image.complete &&
            image.naturalWidth === 0
        ) {
            handleError();
        }
    }

    function hydrateExistingLogo(
        shell,
        symbol,
        assetClass
    ) {
        const existing =
            q("img", shell);

        if (!existing) {
            return false;
        }

        bindLogoImage(
            shell,
            existing,
            symbol,
            assetClass
        );

        return true;
    }

    function hydrateLogoSource(
        shell,
        symbol,
        assetClass,
        source
    ) {
        if (!source) {
            return false;
        }

        const normalizedSource =
            normalizeText(source);

        if (!normalizedSource) {
            return false;
        }

        const image =
            document.createElement("img");

        image.loading = "lazy";
        image.decoding = "async";
        image.referrerPolicy =
            "no-referrer";

        bindLogoImage(
            shell,
            image,
            symbol,
            assetClass
        );

        shell.replaceChildren(image);

        image.src =
            normalizedSource;

        return true;
    }

    function findConfiguredLogoSource(
        element
    ) {
        const direct =
            element.dataset.logo ||
            element.dataset.logoUrl ||
            element.dataset.symbolLogo ||
            element.dataset.iconUrl;

        if (direct) {
            return direct;
        }

        const ancestor =
            safeClosest(
                element,
                "[data-logo], [data-logo-url], [data-symbol-logo], [data-icon-url]"
            );

        return (
            ancestor?.dataset.logo ||
            ancestor?.dataset.logoUrl ||
            ancestor?.dataset.symbolLogo ||
            ancestor?.dataset.iconUrl ||
            ""
        );
    }

    function ensureSymbolLogo(
        container
    ) {
        if (!container) {
            return null;
        }

        const symbol =
            inferSymbolFromElement(
                container
            );

        if (!symbol) {
            return null;
        }

        const assetClass =
            inferAssetFromElement(
                container
            );

        let shell =
            q(
                ":scope > .pt-symbol-logo, :scope .symbol-logo, :scope .ticker-logo, :scope [data-symbol-logo-host]",
                container
            );

        if (shell) {
            shell.classList.add(
                "pt-symbol-logo"
            );

            shell.dataset.symbol =
                symbol;

            shell.dataset.assetClass =
                assetClass;

            if (
                hydrateExistingLogo(
                    shell,
                    symbol,
                    assetClass
                )
            ) {
                return shell;
            }

            const configuredSource =
                findConfiguredLogoSource(
                    shell
                ) ||
                findConfiguredLogoSource(
                    container
                );

            if (
                hydrateLogoSource(
                    shell,
                    symbol,
                    assetClass,
                    configuredSource
                )
            ) {
                return shell;
            }

            logoFallback(
                shell,
                symbol,
                assetClass
            );

            return shell;
        }

        shell =
            createLogoShell(
                symbol,
                assetClass
            );

        const configuredSource =
            findConfiguredLogoSource(
                container
            );

        if (
            configuredSource
        ) {
            hydrateLogoSource(
                shell,
                symbol,
                assetClass,
                configuredSource
            );
        }
        else {
            logoFallback(
                shell,
                symbol,
                assetClass
            );
        }

        const insertionTarget =
            q(
                ".symbol-main, .symbol-cell, .symbol-info, .symbol-copy",
                container
            ) ||
            container;

        insertionTarget.insertBefore(
            shell,
            insertionTarget.firstChild
        );

        container.classList.add(
            "pt-has-symbol-logo"
        );

        return shell;
    }

    function hydrateSymbolLogos(host) {
        const selectors = [
            ".symbol-strip button",
            "[data-symbol-card]",
            "[data-symbol-row]",
            ".symbol-row[data-symbol]",
            ".watchlist-row[data-symbol]",
            ".position-row[data-symbol]",
            ".order-row[data-symbol]",
            ".market-row[data-symbol]",
            ".trade-symbol[data-symbol]",
            "tr[data-symbol]"
        ];

        qa(
            selectors.join(","),
            host
        ).forEach(
            ensureSymbolLogo
        );

        qa(
            ".pt-symbol-logo, .symbol-logo, .ticker-logo",
            host
        ).forEach((shell) => {
            const owner =
                safeClosest(
                    shell,
                    "[data-symbol], [data-ticker], button, tr, .symbol-row, .symbol-card"
                );

            const symbol =
                normalizeSymbol(
                    shell.dataset.symbol ||
                    owner?.dataset.symbol ||
                    owner?.dataset.ticker ||
                    inferSymbolFromElement(
                        owner
                    )
                );

            if (!symbol) {
                return;
            }

            const assetClass =
                normalizeAssetClass(
                    shell.dataset.assetClass ||
                    owner?.dataset.assetClass ||
                    owner?.dataset.assetType ||
                    inferAssetFromElement(
                        owner
                    )
                );

            shell.classList.add(
                "pt-symbol-logo"
            );

            shell.dataset.symbol =
                symbol;

            shell.dataset.assetClass =
                assetClass;

            if (
                hydrateExistingLogo(
                    shell,
                    symbol,
                    assetClass
                )
            ) {
                return;
            }

            const configuredSource =
                findConfiguredLogoSource(
                    shell
                ) ||
                findConfiguredLogoSource(
                    owner
                );

            if (
                !hydrateLogoSource(
                    shell,
                    symbol,
                    assetClass,
                    configuredSource
                )
            ) {
                logoFallback(
                    shell,
                    symbol,
                    assetClass
                );
            }
        });
    }

    function enhanceTables(host) {
        qa(
            ".data-table",
            host
        ).forEach((table) => {
            table.setAttribute(
                "role",
                "table"
            );

            qa(
                "thead th",
                table
            ).forEach((header) => {
                setAttributeIfMissing(
                    header,
                    "scope",
                    "col"
                );
            });

            qa(
                "tbody tr",
                table
            ).forEach((row) => {
                if (
                    row.dataset.keyboardDisabled ===
                    "true"
                ) {
                    return;
                }

                if (
                    row.tabIndex < 0
                ) {
                    row.tabIndex = 0;
                }

                row.classList.add(
                    "pt-interactive-row"
                );
            });
        });
    }

    function updateTabState(
        bar,
        activeButton
    ) {
        qa(
            "button",
            bar
        ).forEach((button) => {
            const active =
                button === activeButton;

            button.classList.toggle(
                "active",
                active
            );

            button.setAttribute(
                "aria-selected",
                active
                    ? "true"
                    : "false"
            );

            button.tabIndex =
                active
                    ? 0
                    : -1;
        });
    }

    function enhanceTabs(host) {
        qa(
            ".tabbar, .ai-modebar",
            host
        ).forEach((bar) => {
            bar.setAttribute(
                "role",
                "tablist"
            );

            const buttons =
                qa(
                    "button",
                    bar
                );

            let active =
                buttons.find(
                    (button) =>
                        button.classList.contains(
                            "active"
                        )
                ) ||
                buttons[0];

            buttons.forEach(
                (
                    button,
                    index
                ) => {
                    button.setAttribute(
                        "role",
                        "tab"
                    );

                    button.setAttribute(
                        "aria-selected",
                        button === active
                            ? "true"
                            : "false"
                    );

                    button.tabIndex =
                        button === active
                            ? 0
                            : -1;

                    if (
                        button.dataset.ptTabBound ===
                        "true"
                    ) {
                        return;
                    }

                    button.dataset.ptTabBound =
                        "true";

                    on(
                        button,
                        "click",
                        () => {
                            updateTabState(
                                bar,
                                button
                            );
                        }
                    );

                    on(
                        button,
                        "keydown",
                        (event) => {
                            const current =
                                buttons.indexOf(
                                    button
                                );

                            let next =
                                current;

                            if (
                                event.key ===
                                "ArrowRight"
                            ) {
                                next =
                                    (
                                        current +
                                        1
                                    ) %
                                    buttons.length;
                            }
                            else if (
                                event.key ===
                                "ArrowLeft"
                            ) {
                                next =
                                    (
                                        current -
                                        1 +
                                        buttons.length
                                    ) %
                                    buttons.length;
                            }
                            else if (
                                event.key ===
                                "Home"
                            ) {
                                next = 0;
                            }
                            else if (
                                event.key ===
                                "End"
                            ) {
                                next =
                                    buttons.length -
                                    1;
                            }
                            else {
                                return;
                            }

                            event.preventDefault();

                            buttons[
                                next
                            ]?.focus();
                        }
                    );
                }
            );
        });
    }

    function enhanceInputs(host) {
        qa(
            "input, select, textarea",
            host
        ).forEach((input) => {
            if (
                input.dataset.ptInputBound ===
                "true"
            ) {
                return;
            }

            input.dataset.ptInputBound =
                "true";

            const field =
                () =>
                    safeClosest(
                        input,
                        ".field, label, .form-field, .input-wrap"
                    );

            on(
                input,
                "focus",
                () => {
                    field()?.classList.add(
                        "is-focused"
                    );
                }
            );

            on(
                input,
                "blur",
                () => {
                    field()?.classList.remove(
                        "is-focused"
                    );
                }
            );

            on(
                input,
                "input",
                () => {
                    field()?.classList.toggle(
                        "has-value",
                        normalizeText(
                            input.value
                        ).length > 0
                    );
                }
            );

            field()?.classList.toggle(
                "has-value",
                normalizeText(
                    input.value
                ).length > 0
            );
        });
    }

    function enhanceScroll(host) {
        qa(
            ".tabbar, .ai-modebar, .symbol-strip",
            host
        ).forEach((strip) => {
            if (
                strip.dataset.ptWheelBound ===
                "true"
            ) {
                return;
            }

            strip.dataset.ptWheelBound =
                "true";

            on(
                strip,
                "wheel",
                (event) => {
                    if (
                        Math.abs(
                            event.deltaY
                        ) <=
                        Math.abs(
                            event.deltaX
                        )
                    ) {
                        return;
                    }

                    if (
                        strip.scrollWidth <=
                        strip.clientWidth
                    ) {
                        return;
                    }

                    strip.scrollLeft +=
                        event.deltaY;

                    event.preventDefault();
                },
                {
                    passive: false
                }
            );
        });
    }

    function enhanceSymbolStrip(host) {
        qa(
            ".symbol-strip",
            host
        ).forEach((strip) => {
            const buttons =
                qa(
                    "button",
                    strip
                );

            buttons.forEach(
                (button) => {
                    const symbol =
                        inferSymbolFromElement(
                            button
                        );

                    if (symbol) {
                        button.dataset.symbol =
                            symbol;

                        setAttributeIfMissing(
                            button,
                            "aria-label",
                            `Select ${symbol}`
                        );
                    }

                    button.setAttribute(
                        "aria-pressed",
                        button.classList.contains(
                            "active"
                        )
                            ? "true"
                            : "false"
                    );

                    if (
                        button.dataset.ptSymbolBound ===
                        "true"
                    ) {
                        return;
                    }

                    button.dataset.ptSymbolBound =
                        "true";

                    on(
                        button,
                        "click",
                        () => {
                            buttons.forEach(
                                (candidate) => {
                                    const active =
                                        candidate ===
                                        button;

                                    candidate.classList.toggle(
                                        "active",
                                        active
                                    );

                                    candidate.setAttribute(
                                        "aria-pressed",
                                        active
                                            ? "true"
                                            : "false"
                                    );
                                }
                            );
                        }
                    );
                }
            );
        });
    }

    function enhanceBuySell(host) {
        qa(
            ".buy-sell",
            host
        ).forEach((group) => {
            const buttons =
                qa(
                    "button",
                    group
                );

            buttons.forEach(
                (button) => {
                    const text =
                        normalizeText(
                            button.textContent
                        ).toLowerCase();

                    if (
                        text.includes("buy")
                    ) {
                        button.classList.add(
                            "pt-buy-action"
                        );

                        ensureIcon(
                            button,
                            "buy"
                        );
                    }
                    else if (
                        text.includes("sell")
                    ) {
                        button.classList.add(
                            "pt-sell-action"
                        );

                        ensureIcon(
                            button,
                            "sell"
                        );
                    }

                    button.setAttribute(
                        "aria-pressed",
                        button.classList.contains(
                            "active"
                        )
                            ? "true"
                            : "false"
                    );
                }
            );
        });
    }

    function enhanceOrderTypes(host) {
        qa(
            ".order-types",
            host
        ).forEach((group) => {
            qa(
                "button",
                group
            ).forEach((button) => {
                button.setAttribute(
                    "aria-pressed",
                    button.classList.contains(
                        "active"
                    )
                        ? "true"
                        : "false"
                );
            });
        });
    }

    function enhanceStatusBadges(host) {
        qa(
            "[data-status], .status-success, .status-danger, .status-warning, .status-info, .status-violet",
            host
        ).forEach((element) => {
            const status =
                normalizeText(
                    element.dataset.status ||
                    element.textContent
                ).toLowerCase();

            let iconName = null;

            if (
                status.includes(
                    "connected"
                ) &&
                !status.includes(
                    "disconnected"
                )
            ) {
                iconName =
                    "connected";
            }
            else if (
                status.includes(
                    "disconnected"
                )
            ) {
                iconName =
                    "disconnected";
            }
            else if (
                status.includes(
                    "approved"
                ) ||
                status.includes(
                    "success"
                ) ||
                status.includes(
                    "filled"
                ) ||
                status.includes(
                    "complete"
                )
            ) {
                iconName =
                    "success";
            }
            else if (
                status.includes(
                    "reject"
                ) ||
                status.includes(
                    "failed"
                ) ||
                status.includes(
                    "error"
                ) ||
                status.includes(
                    "blocked"
                )
            ) {
                iconName =
                    "error";
            }
            else if (
                status.includes(
                    "warning"
                ) ||
                status.includes(
                    "pending"
                )
            ) {
                iconName =
                    "warning";
            }
            else if (
                status.includes(
                    "live"
                ) ||
                status.includes(
                    "stream"
                )
            ) {
                iconName =
                    "live";
            }

            if (iconName) {
                ensureIcon(
                    element,
                    iconName
                );
            }
        });
    }

    function enhancePanelHeaders(host) {
        qa(
            ".panel-head",
            host
        ).forEach((header) => {
            const title =
                q(
                    "h1, h2, h3, h4, strong",
                    header
                );

            if (!title) {
                return;
            }

            const text =
                normalizeText(
                    title.textContent
                ).toLowerCase();

            const rules = [
                ["portfolio", "portfolio"],
                ["position", "positions"],
                ["order", "orders"],
                ["activity", "activity"],
                ["risk", "risk"],
                ["strategy", "strategy"],
                ["decision", "decision"],
                ["signal", "signal"],
                ["chart", "chart"],
                ["performance", "performance"],
                ["analytics", "analytics"],
                ["account", "account"],
                ["market", "market"],
                ["scanner", "scanner"],
                ["insight", "insight"],
                ["trady", "tradyai"],
                ["ai", "ai"]
            ];

            for (const [
                token,
                iconName
            ] of rules) {
                if (
                    text.includes(
                        token
                    )
                ) {
                    ensureIcon(
                        title,
                        iconName
                    );
                    break;
                }
            }
        });
    }

    function enhanceTooltips(host) {
        qa(
            "[data-tooltip], [title]",
            host
        ).forEach((element) => {
            const text =
                element.dataset.tooltip ||
                element.getAttribute(
                    "title"
                );

            if (!text) {
                return;
            }

            element.dataset.ptTooltip =
                text;

            element.classList.add(
                "pt-tooltip-host"
            );

            if (
                element.hasAttribute(
                    "title"
                )
            ) {
                element.removeAttribute(
                    "title"
                );
            }

            setAttributeIfMissing(
                element,
                "aria-label",
                text
            );
        });
    }

    function setCompactMode(host) {
        if (!host) {
            return;
        }

        const width =
            host.getBoundingClientRect()
                .width;

        host.classList.toggle(
            "pt-compact",
            width < 980
        );

        host.classList.toggle(
            "pt-narrow",
            width < 720
        );

        host.classList.toggle(
            "pt-wide",
            width >= 1320
        );
    }

    function syncActiveStates(host) {
        if (!host) {
            return;
        }

        qa(
            ".tabbar button, .ai-modebar button",
            host
        ).forEach((button) => {
            button.setAttribute(
                "aria-selected",
                button.classList.contains(
                    "active"
                )
                    ? "true"
                    : "false"
            );
        });

        qa(
            ".buy-sell button, .order-types button, .symbol-strip button",
            host
        ).forEach((button) => {
            button.setAttribute(
                "aria-pressed",
                button.classList.contains(
                    "active"
                )
                    ? "true"
                    : "false"
            );
        });
    }

    function hydratePremiumUi(host) {
        if (!host) {
            return;
        }

        hydrateExplicitIcons(host);
        hydrateButtonIcons(host);
        hydrateMetricIcons(host);
        hydrateAssetIcons(host);
        hydrateSymbolLogos(host);

        enhanceTables(host);
        enhanceTabs(host);
        enhanceInputs(host);
        enhanceScroll(host);
        enhanceSymbolStrip(host);
        enhanceBuySell(host);
        enhanceOrderTypes(host);
        enhanceStatusBadges(host);
        enhancePanelHeaders(host);
        enhanceTooltips(host);

        syncActiveStates(host);
    }

    let hydrationFrame = 0;

    function scheduleHydration(host) {
        cancelRaf(
            hydrationFrame
        );

        hydrationFrame =
            raf(() => {
                hydrationFrame = 0;

                if (
                    !host ||
                    !document.documentElement.contains(
                        host
                    )
                ) {
                    return;
                }

                hydratePremiumUi(
                    host
                );
            });
    }

    function observe(host) {
        state.observer?.disconnect();
        state.resizeObserver?.disconnect();

        state.observer =
            new MutationObserver(
                (mutations) => {
                    let relevant = false;

                    for (
                        const mutation
                        of mutations
                    ) {
                        if (
                            mutation.type ===
                            "childList"
                        ) {
                            relevant = true;
                            break;
                        }

                        if (
                            mutation.type ===
                            "attributes"
                        ) {
                            const name =
                                mutation.attributeName;

                            if (
                                name ===
                                    "class" ||
                                name ===
                                    "data-symbol" ||
                                name ===
                                    "data-status" ||
                                name ===
                                    "data-logo" ||
                                name ===
                                    "data-logo-url"
                            ) {
                                relevant =
                                    true;
                                break;
                            }
                        }
                    }

                    if (relevant) {
                        scheduleHydration(
                            host
                        );
                    }
                }
            );

        state.observer.observe(
            host,
            {
                childList: true,
                subtree: true,
                attributes: true,
                attributeFilter: [
                    "class",
                    "data-symbol",
                    "data-status",
                    "data-logo",
                    "data-logo-url",
                    "data-symbol-logo",
                    "data-asset-class",
                    "data-asset-type"
                ]
            }
        );

        if (
            "ResizeObserver" in window
        ) {
            state.resizeObserver =
                new ResizeObserver(
                    () => {
                        setCompactMode(
                            host
                        );
                    }
                );

            state.resizeObserver.observe(
                host
            );
        }
        else {
            on(
                window,
                "resize",
                () => {
                    setCompactMode(
                        host
                    );
                },
                {
                    passive: true
                }
            );
        }
    }

    function setSymbolLogo(
        symbol,
        logoUrl,
        assetClass = "stocks"
    ) {
        const host =
            root();

        if (!host) {
            return false;
        }

        const normalizedSymbol =
            normalizeSymbol(
                symbol
            );

        if (!normalizedSymbol) {
            return false;
        }

        const selector =
            `[data-symbol="${escapeCss(
                normalizedSymbol
            )}"]`;

        const matches =
            qa(
                selector,
                host
            );

        let updated = false;

        matches.forEach(
            (element) => {
                element.dataset.logoUrl =
                    logoUrl || "";

                element.dataset.assetClass =
                    normalizeAssetClass(
                        assetClass
                    );

                const shell =
                    ensureSymbolLogo(
                        element
                    );

                if (!shell) {
                    return;
                }

                if (logoUrl) {
                    hydrateLogoSource(
                        shell,
                        normalizedSymbol,
                        assetClass,
                        logoUrl
                    );
                }
                else {
                    logoFallback(
                        shell,
                        normalizedSymbol,
                        assetClass
                    );
                }

                updated = true;
            }
        );

        return updated;
    }

    function setSymbolLogos(
        symbols
    ) {
        if (!symbols) {
            return;
        }

        if (
            Array.isArray(
                symbols
            )
        ) {
            symbols.forEach(
                (entry) => {
                    if (
                        !entry ||
                        typeof entry !==
                            "object"
                    ) {
                        return;
                    }

                    setSymbolLogo(
                        entry.symbol,
                        entry.logoUrl ||
                            entry.logo ||
                            entry.iconUrl ||
                            "",
                        entry.assetClass ||
                            entry.assetType ||
                            "stocks"
                    );
                }
            );

            return;
        }

        if (
            typeof symbols ===
            "object"
        ) {
            Object.entries(
                symbols
            ).forEach(
                ([
                    symbol,
                    value
                ]) => {
                    if (
                        typeof value ===
                        "string"
                    ) {
                        setSymbolLogo(
                            symbol,
                            value,
                            "stocks"
                        );
                    }
                    else if (
                        value &&
                        typeof value ===
                            "object"
                    ) {
                        setSymbolLogo(
                            symbol,
                            value.logoUrl ||
                                value.logo ||
                                value.iconUrl ||
                                "",
                            value.assetClass ||
                                value.assetType ||
                                "stocks"
                        );
                    }
                }
            );
        }
    }

    function updateRuntimeStatus(
        status
    ) {
        const host =
            root();

        if (!host) {
            return;
        }

        const normalized =
            normalizeText(
                status
            );

        host.dataset.runtimeStatus =
            normalized;

        qa(
            "[data-runtime-status]",
            host
        ).forEach((element) => {
            element.dataset.status =
                normalized;

            if (
                element.dataset.runtimeStatusText ===
                "true"
            ) {
                element.textContent =
                    normalized;
            }
        });

        enhanceStatusBadges(
            host
        );
    }

    function setSelectedSymbol(
        symbol
    ) {
        const host =
            root();

        if (!host) {
            return false;
        }

        const normalized =
            normalizeSymbol(
                symbol
            );

        if (!normalized) {
            return false;
        }

        let found = false;

        qa(
            ".symbol-strip button",
            host
        ).forEach((button) => {
            const active =
                inferSymbolFromElement(
                    button
                ) ===
                normalized;

            button.classList.toggle(
                "active",
                active
            );

            button.setAttribute(
                "aria-pressed",
                active
                    ? "true"
                    : "false"
            );

            if (active) {
                found = true;
            }
        });

        host.dataset.selectedSymbol =
            normalized;

        return found;
    }

    function refresh() {
        const host =
            root();

        if (!host) {
            return false;
        }

        setCompactMode(
            host
        );

        hydratePremiumUi(
            host
        );

        return true;
    }

    function mount() {
        const host =
            root();

        if (!host) {
            return false;
        }

        if (
            state.mounted &&
            state.host === host &&
            host.dataset.runtimeMounted ===
                "true"
        ) {
            refresh();
            return true;
        }

        if (
            state.mounted &&
            state.host !== host
        ) {
            unmount();
        }

        host.dataset.runtimeMounted =
            "true";

        host.dataset.pageRuntime =
            PAGE;

        state.host =
            host;

        state.mounted =
            true;

        setCompactMode(
            host
        );

        hydratePremiumUi(
            host
        );

        observe(
            host
        );

        return true;
    }

    function unmount() {
        cancelRaf(
            hydrationFrame
        );

        hydrationFrame = 0;

        state.observer?.disconnect();
        state.resizeObserver?.disconnect();

        state.observer = null;
        state.resizeObserver = null;

        state.disposers
            .splice(0)
            .forEach((dispose) => {
                try {
                    dispose();
                }
                catch {
                    // Disposal must never interrupt Blazor navigation.
                }
            });

        if (
            state.host
        ) {
            delete state.host.dataset
                .runtimeMounted;

            delete state.host.dataset
                .pageRuntime;
        }

        state.host = null;
        state.mounted = false;
    }

    function boot() {
        if (mount()) {
            return;
        }

        state.bootObserver?.disconnect();

        const app =
            document.getElementById(
                "app"
            ) ||
            document.body;

        if (!app) {
            return;
        }

        state.bootObserver =
            new MutationObserver(
                () => {
                    if (
                        mount()
                    ) {
                        state.bootObserver?.disconnect();
                        state.bootObserver =
                            null;
                    }
                }
            );

        state.bootObserver.observe(
            app,
            {
                childList: true,
                subtree: true
            }
        );
    }

    window.PhoenixTrendPages =
        window.PhoenixTrendPages ||
        {};

    window.PhoenixTrendPages.trade = {
        mount,
        unmount,
        refresh,
        setSymbolLogo,
        setSymbolLogos,
        setSelectedSymbol,
        updateRuntimeStatus
    };

    window.PhoenixTrade =
        window.PhoenixTrade ||
        {};

    Object.assign(
        window.PhoenixTrade,
        {
            mount,
            unmount,
            refresh,
            setSymbolLogo,
            setSymbolLogos,
            setSelectedSymbol,
            updateRuntimeStatus
        }
    );

    if (
        document.readyState ===
        "loading"
    ) {
        document.addEventListener(
            "DOMContentLoaded",
            boot,
            {
                once: true
            }
        );
    }
    else {
        boot();
    }
})();
/* Manual Trade fullscreen extension — keeps the existing chart in place. */
(() => {
    window.PhoenixTrade = window.PhoenixTrade || {};
    window.PhoenixTrade.toggleChartFullscreen = async (elementId) => {
        const el = document.getElementById(elementId);
        if (!el) return false;
        try {
            if (document.fullscreenElement === el) {
                await document.exitFullscreen();
            } else {
                if (document.fullscreenElement) await document.exitFullscreen();
                await el.requestFullscreen();
            }
            window.setTimeout(() => window.dispatchEvent(new Event('resize')), 80);
            return true;
        } catch (error) {
            console.error('PhoenixTrend chart fullscreen failed:', error);
            return false;
        }
    };
    document.addEventListener('fullscreenchange', () => {
        window.setTimeout(() => window.dispatchEvent(new Event('resize')), 80);
    });
})();
