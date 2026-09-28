/* ============================================================
   PHOENIXTREND
   HOME / COMMAND CENTER PREMIUM EFFECTS
   ============================================================ */

window.PhoenixPage_home = () => {

    /* ========================================================
       KEEP EXISTING PHOENIX INITIALIZATION
       ======================================================== */

    if (
        window.PhoenixPremium &&
        typeof window.PhoenixPremium.init === "function"
    ) {
        PhoenixPremium.init("home");
    }


    /* ========================================================
       HERO
       ======================================================== */

    const hero =
        document.querySelector(
            ".page-hero:has(+ .metric-grid.five)"
        );


    if (hero) {

        setupHeroParallax(hero);

        setupHeroHighlight(hero);

    }


    /* ========================================================
       FLOATING METRIC CARDS
       ======================================================== */

    const metricCards =
        document.querySelectorAll(
            ".metric-grid.five > *"
        );


    metricCards.forEach(
        (card) => {

            setupCardDepth(card);

        }
    );


    /* ========================================================
       PREMIUM REVEAL
       ======================================================== */

    const revealElements = [
        ...document.querySelectorAll(
            ".metric-grid.five > *"
        ),
        ...document.querySelectorAll(
            ".home-grid > *"
        )
    ];


    revealElements.forEach(
        (element, index) => {

            setupReveal(
                element,
                index
            );

        }
    );


    /* ========================================================
       TABLE ROW INTERACTION
       ======================================================== */

    setupTableRows();


    /* ========================================================
       MARKET ROW INTERACTION
       ======================================================== */

    setupTickerRows();

};



/* ============================================================
   HERO PARALLAX
   ============================================================ */

function setupHeroParallax(hero) {

    if (
        hero.dataset.ptParallaxReady === "true"
    ) {
        return;
    }


    hero.dataset.ptParallaxReady =
        "true";


    if (prefersReducedMotion()) {
        return;
    }


    let frame = null;


    hero.addEventListener(
        "pointermove",
        (event) => {

            if (frame !== null) {
                cancelAnimationFrame(frame);
            }


            frame =
                requestAnimationFrame(
                    () => {

                        const rect =
                            hero.getBoundingClientRect();


                        const x =
                            (
                                event.clientX -
                                rect.left
                            ) /
                            rect.width;


                        const y =
                            (
                                event.clientY -
                                rect.top
                            ) /
                            rect.height;


                        /*
                         * Keep motion intentionally tiny.
                         * Large movement would look like a game.
                         */

                        const moveX =
                            (x - .5) * 7;


                        const moveY =
                            (y - .5) * 4;


                        hero.style.setProperty(
                            "--hero-x",
                            `${moveX.toFixed(2)}px`
                        );


                        hero.style.setProperty(
                            "--hero-y",
                            `${moveY.toFixed(2)}px`
                        );

                    }
                );

        }
    );


    hero.addEventListener(
        "pointerleave",
        () => {

            if (frame !== null) {
                cancelAnimationFrame(frame);
            }


            hero.style.setProperty(
                "--hero-x",
                "0px"
            );


            hero.style.setProperty(
                "--hero-y",
                "0px"
            );

        }
    );

}



/* ============================================================
   HERO POINTER LIGHT
   ============================================================ */

function setupHeroHighlight(hero) {

    if (
        hero.dataset.ptHighlightReady === "true"
    ) {
        return;
    }


    hero.dataset.ptHighlightReady =
        "true";


    hero.addEventListener(
        "pointermove",
        (event) => {

            const rect =
                hero.getBoundingClientRect();


            const x =
                event.clientX -
                rect.left;


            const y =
                event.clientY -
                rect.top;


            hero.style.setProperty(
                "--pointer-x",
                `${x}px`
            );


            hero.style.setProperty(
                "--pointer-y",
                `${y}px`
            );

        }
    );

}



/* ============================================================
   CARD DEPTH
   ============================================================ */

function setupCardDepth(card) {

    if (
        card.dataset.ptDepthReady === "true"
    ) {
        return;
    }


    card.dataset.ptDepthReady =
        "true";


    if (prefersReducedMotion()) {
        return;
    }


    card.addEventListener(
        "pointermove",
        (event) => {

            const rect =
                card.getBoundingClientRect();


            const px =
                (
                    event.clientX -
                    rect.left
                ) /
                rect.width;


            const py =
                (
                    event.clientY -
                    rect.top
                ) /
                rect.height;


            const rotateY =
                (px - .5) * 1.2;


            const rotateX =
                (.5 - py) * 1.0;


            card.style.transform =
                `translateY(-3px)
                 perspective(700px)
                 rotateX(${rotateX.toFixed(2)}deg)
                 rotateY(${rotateY.toFixed(2)}deg)`;

        }
    );


    card.addEventListener(
        "pointerleave",
        () => {

            card.style.transform =
                "";

        }
    );

}



/* ============================================================
   REVEAL ANIMATION
   ============================================================ */

function setupReveal(
    element,
    index
) {

    if (
        element.dataset.ptRevealReady === "true"
    ) {
        return;
    }


    element.dataset.ptRevealReady =
        "true";


    element.classList.add(
        "pt-home-reveal"
    );


    if (prefersReducedMotion()) {

        element.classList.add(
            "pt-visible"
        );

        return;

    }


    const delay =
        Math.min(
            index * 45,
            260
        );


    window.setTimeout(
        () => {

            element.classList.add(
                "pt-visible"
            );

        },
        delay
    );

}



/* ============================================================
   WATCHLIST ROWS
   ============================================================ */

function setupTableRows() {

    const rows =
        document.querySelectorAll(
            ".data-table tbody tr"
        );


    rows.forEach(
        (row) => {

            if (
                row.dataset.ptTableReady === "true"
            ) {
                return;
            }


            row.dataset.ptTableReady =
                "true";


            row.addEventListener(
                "pointerenter",
                () => {

                    row.style.background =
                        "rgba(255,255,255,.027)";

                }
            );


            row.addEventListener(
                "pointerleave",
                () => {

                    row.style.background =
                        "";

                }
            );

        }
    );

}



/* ============================================================
   MARKET OVERVIEW ROWS
   ============================================================ */

function setupTickerRows() {

    const rows =
        document.querySelectorAll(
            ".ticker-list > div"
        );


    rows.forEach(
        (row) => {

            if (
                row.dataset.ptTickerReady === "true"
            ) {
                return;
            }


            row.dataset.ptTickerReady =
                "true";


            row.addEventListener(
                "pointerenter",
                () => {

                    row.style.background =
                        "rgba(255,255,255,.022)";

                }
            );


            row.addEventListener(
                "pointerleave",
                () => {

                    row.style.background =
                        "";

                }
            );

        }
    );

}



/* ============================================================
   ACCESSIBILITY
   ============================================================ */

function prefersReducedMotion() {

    return (
        window.matchMedia &&
        window.matchMedia(
            "(prefers-reduced-motion: reduce)"
        ).matches
    );

}