window.PhoenixPage_markets = () => {
    if (window.PhoenixPremium &&
        typeof window.PhoenixPremium.init === "function") {
        window.PhoenixPremium.init("markets");
    }

    window.PhoenixMarkets = window.PhoenixMarkets || {};

    window.PhoenixMarkets.focusSearch = () => {
        const input = document.getElementById("ptm-symbol-search");
        if (!input) return;

        input.focus();
        input.select();
        input.scrollIntoView({
            behavior: "smooth",
            block: "center"
        });
    };

    /*
     * News cards use normal <a> elements with target="_blank".
     * Keeping navigation native means the original publisher URL
     * returned by the backend is opened directly and PhoenixTrend
     * does not rewrite or proxy the article.
     */

    if (window.PhoenixMarkets._marketsKeyHandlerAttached) return;

    window.PhoenixMarkets._marketsKeyHandlerAttached = true;

    document.addEventListener("keydown", event => {
        if (event.key !== "/" ||
            event.ctrlKey ||
            event.metaKey ||
            event.altKey) {
            return;
        }

        if (!document.querySelector(".ptm-page")) return;

        const target = event.target;
        const tag = target?.tagName?.toLowerCase();

        if (tag === "input" ||
            tag === "textarea" ||
            target?.isContentEditable) {
            return;
        }

        event.preventDefault();
        window.PhoenixMarkets.focusSearch();
    });
};
