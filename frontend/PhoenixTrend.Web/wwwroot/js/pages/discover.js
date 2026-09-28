window.PhoenixPage_discover = () => {
    if (window.PhoenixPremium &&
        typeof window.PhoenixPremium.init === "function") {
        window.PhoenixPremium.init("discover");
    }

    window.PhoenixDiscover = window.PhoenixDiscover || {};

    if (window.PhoenixDiscover._pulseTimer) {
        clearInterval(window.PhoenixDiscover._pulseTimer);
    }

    window.PhoenixDiscover._pulseTimer = setInterval(() => {
        if (!document.querySelector(".pt-discover")) {
            clearInterval(window.PhoenixDiscover._pulseTimer);
            window.PhoenixDiscover._pulseTimer = null;
            return;
        }

        if (window.PhoenixPremium &&
            typeof window.PhoenixPremium.pulse === "function") {
            window.PhoenixPremium.pulse(".pt-discover .discover-panel");
        }
    }, 5000);
};