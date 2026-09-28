/* ============================================================
   PHOENIXTREND LOGIN — VISIBLE CINEMATIC MOTION
   No extra logo is created. The branding stays inside loginscreen.png.
   ============================================================ */

window.PhoenixLogin = (() => {
    let initialized = false;
    let cleanup = [];

    function listen(target, event, handler, options) {
        target.addEventListener(event, handler, options);
        cleanup.push(() => target.removeEventListener(event, handler, options));
    }

    function reducedMotion() {
        return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    }

    function boot() {
        const page = document.querySelector(".pt-login-page");

        if (!page) {
            initialized = false;
            return;
        }

        if (initialized) return;
        initialized = true;

        createAtmosphere(page);
        createEmbers(page);
        animateEntrance(page);
        enableInputEffects(page);
        enableCardLight(page);
        enableBackgroundMotion(page);
        enableKeyboardNavigation();
    }

    function createAtmosphere(page) {
        if (page.querySelector(".pt-login-fx")) return;

        const fx = document.createElement("div");
        fx.className = "pt-login-fx";
        fx.setAttribute("aria-hidden", "true");

        const rays = document.createElement("div");
        rays.className = "pt-login-rays";
        rays.setAttribute("aria-hidden", "true");

        page.appendChild(fx);
        page.appendChild(rays);

        cleanup.push(() => fx.remove());
        cleanup.push(() => rays.remove());
    }

    function createEmbers(page) {
        if (reducedMotion() || window.matchMedia("(max-width: 900px)").matches) {
            return;
        }

        const old = page.querySelector(".pt-login-embers");
        if (old) old.remove();

        const layer = document.createElement("div");
        layer.className = "pt-login-embers";
        layer.setAttribute("aria-hidden", "true");

        // More particles, but restricted to the artwork side.
        const embers = [
            [5,  3.2,  8.5, -1.0,  26],
            [8,  4.4, 10.5, -7.0, -22],
            [11, 2.5,  7.5, -4.0,  34],
            [14, 3.8, 11.5, -9.0, -28],
            [17, 2.8,  9.0, -2.0,  18],
            [20, 4.8, 12.0, -10.0, 31],
            [23, 2.4,  8.0, -5.0, -18],
            [26, 3.5, 10.0, -3.0,  25],
            [29, 2.6,  9.5, -8.0, -30],
            [32, 4.1, 12.5, -11.0, 28],
            [35, 2.3,  7.8, -6.0,  19],
            [38, 3.7, 11.0, -1.5, -24],
            [41, 2.7,  9.2, -7.5,  32],
            [44, 4.5, 12.8, -12.0, -20],
            [47, 2.5,  8.8, -4.5,  23],
            [50, 3.4, 10.8, -9.5, -29],
            [53, 2.2,  7.2, -3.5,  17],
            [56, 4.0, 11.8, -8.5,  27]
        ];

        embers.forEach(([x, size, duration, delay, drift]) => {
            const ember = document.createElement("span");
            ember.className = "pt-login-ember";
            ember.style.setProperty("--ember-x", `${x}vw`);
            ember.style.setProperty("--ember-size", `${size}px`);
            ember.style.setProperty("--ember-duration", `${duration}s`);
            ember.style.setProperty("--ember-delay", `${delay}s`);
            ember.style.setProperty("--ember-drift", `${drift}px`);
            layer.appendChild(ember);
        });

        page.appendChild(layer);
        cleanup.push(() => layer.remove());
    }

    function animateEntrance(page) {
        if (reducedMotion()) return;

        const card = page.querySelector(".pt-login-card");

        if (card) {
            card.animate(
                [
                    {
                        opacity: 0,
                        transform: "translate3d(28px,20px,0) scale(.975)",
                        filter: "blur(5px)"
                    },
                    {
                        opacity: 1,
                        transform: "translate3d(0,0,0) scale(1)",
                        filter: "blur(0)"
                    }
                ],
                {
                    duration: 820,
                    easing: "cubic-bezier(.18,.8,.24,1)",
                    fill: "both"
                }
            );
        }

        const items = page.querySelectorAll(
            ".pt-login-card-header, .pt-login-field, .pt-login-options, " +
            ".pt-login-submit, .pt-login-divider, .pt-login-social, .pt-login-create"
        );

        items.forEach((item, index) => {
            item.animate(
                [
                    { opacity: 0, transform: "translateY(15px)" },
                    { opacity: 1, transform: "translateY(0)" }
                ],
                {
                    duration: 500,
                    delay: 180 + index * 55,
                    easing: "cubic-bezier(.18,.8,.24,1)",
                    fill: "both"
                }
            );
        });
    }

    function enableInputEffects(page) {
        page.querySelectorAll(".pt-login-input-wrap").forEach(wrapper => {
            const input = wrapper.querySelector(".pt-login-input");
            if (!input) return;

            listen(input, "focus", () => wrapper.classList.add("is-focused"));
            listen(input, "blur", () => wrapper.classList.remove("is-focused"));
        });
    }

    function enableCardLight(page) {
        const card = page.querySelector(".pt-login-card");
        if (!card) return;

        let glow = card.querySelector(".pt-login-card-glow");
        if (!glow) {
            glow = document.createElement("span");
            glow.className = "pt-login-card-glow";
            glow.setAttribute("aria-hidden", "true");
            card.prepend(glow);
        }

        listen(card, "mousemove", event => {
            const rect = card.getBoundingClientRect();
            card.style.setProperty("--mouse-x", `${event.clientX - rect.left}px`);
            card.style.setProperty("--mouse-y", `${event.clientY - rect.top}px`);
        });

        listen(card, "mouseleave", () => {
            card.style.setProperty("--mouse-x", "50%");
            card.style.setProperty("--mouse-y", "20%");
        });
    }

    function enableBackgroundMotion(page) {
        const background = page.querySelector(".pt-login-bg");

        if (!background || reducedMotion() ||
            window.matchMedia("(max-width: 900px)").matches) {
            return;
        }

        let pointerX = 0;
        let pointerY = 0;
        let smoothX = 0;
        let smoothY = 0;
        let raf = 0;
        let active = true;
        const started = performance.now();

        listen(document, "mousemove", event => {
            pointerX = (event.clientX / window.innerWidth - .5) * 7;
            pointerY = (event.clientY / window.innerHeight - .5) * 5;
        });

        function render(now) {
            if (!active) return;

            const t = (now - started) / 1000;

            // Slow autonomous cinematic drift.
            const driftX = Math.sin(t * .18) * 4.2;
            const driftY = Math.cos(t * .14) * 2.4;

            smoothX += (pointerX - smoothX) * .018;
            smoothY += (pointerY - smoothY) * .018;

            const x = driftX - smoothX * .30;
            const y = driftY - smoothY * .22;

            // Important: translation only. No scale, so the background stays zoomed out.
            background.style.transform =
                `translate3d(${x}px, ${y}px, 0)`;

            raf = requestAnimationFrame(render);
        }

        raf = requestAnimationFrame(render);

        cleanup.push(() => {
            active = false;
            if (raf) cancelAnimationFrame(raf);
        });
    }

    function enableKeyboardNavigation() {
        listen(document, "keydown", event => {
            if (event.key === "Tab") {
                document.body.classList.add("pt-keyboard-navigation");
            }
        });
    }

    function reset() {
        cleanup.forEach(fn => {
            try { fn(); } catch (_) { }
        });

        cleanup = [];
        initialized = false;
        requestAnimationFrame(boot);
    }

    return { boot, reset };
})();

document.addEventListener("DOMContentLoaded", () => {
    window.PhoenixLogin.boot();
});

window.addEventListener("pageshow", () => {
    window.PhoenixLogin.boot();
});
