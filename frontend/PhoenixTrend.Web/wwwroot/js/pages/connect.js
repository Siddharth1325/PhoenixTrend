window.PhoenixConnect = (() => {

    let cleanup = [];
    let booted = false;


    function reducedMotion() {
        return window.matchMedia &&
            window.matchMedia(
                "(prefers-reduced-motion: reduce)"
            ).matches;
    }


    function addCleanup(fn) {
        cleanup.push(fn);
    }


    function destroy() {

        cleanup.forEach(fn => {

            try {
                fn();
            }
            catch {
            }

        });

        cleanup = [];

        booted = false;


        document
            .querySelectorAll(".pt-connect-embers")
            .forEach(node => node.remove());
    }


    function createEmbers(page) {

        if (!page || reducedMotion()) {
            return;
        }


        const layer =
            document.createElement("div");

        layer.className =
            "pt-connect-embers";

        layer.setAttribute(
            "aria-hidden",
            "true"
        );


        const amount = 14;


        for (let i = 0; i < amount; i++) {

            const ember =
                document.createElement("span");

            ember.className =
                "pt-connect-ember";


            const x =
                54 + Math.random() * 45;

            const size =
                1 + Math.random() * 2.2;

            const duration =
                8 + Math.random() * 9;

            const delay =
                Math.random() * -15;

            const drift =
                -30 + Math.random() * 60;


            ember.style.setProperty(
                "--x",
                `${x}%`
            );

            ember.style.setProperty(
                "--size",
                `${size}px`
            );

            ember.style.setProperty(
                "--duration",
                `${duration}s`
            );

            ember.style.setProperty(
                "--delay",
                `${delay}s`
            );

            ember.style.setProperty(
                "--drift",
                `${drift}px`
            );


            layer.appendChild(ember);
        }


        page.appendChild(layer);


        addCleanup(() => {

            if (layer.isConnected) {
                layer.remove();
            }

        });
    }


    function setupCardReflection(card) {

        if (!card || reducedMotion()) {
            return;
        }


        const move = event => {

            const rect =
                card.getBoundingClientRect();


            const x =
                event.clientX -
                rect.left;

            const y =
                event.clientY -
                rect.top;


            card.style.setProperty(
                "--mouse-x",
                `${x}px`
            );

            card.style.setProperty(
                "--mouse-y",
                `${y}px`
            );
        };


        const leave = () => {

            card.style.setProperty(
                "--mouse-x",
                "50%"
            );

            card.style.setProperty(
                "--mouse-y",
                "20%"
            );
        };


        card.addEventListener(
            "pointermove",
            move
        );

        card.addEventListener(
            "pointerleave",
            leave
        );


        addCleanup(() => {

            card.removeEventListener(
                "pointermove",
                move
            );

            card.removeEventListener(
                "pointerleave",
                leave
            );

        });
    }


    function setupBackgroundMotion(background) {

        if (!background || reducedMotion()) {
            return;
        }


        const move = event => {

            const width =
                window.innerWidth || 1;

            const height =
                window.innerHeight || 1;


            const normalizedX =
                event.clientX / width - .5;

            const normalizedY =
                event.clientY / height - .5;


            const x =
                normalizedX * -5;

            const y =
                normalizedY * -3;


            background.style.transform =
                `translate3d(${x}px, ${y}px, 0) scale(1.006)`;
        };


        const leave = () => {

            background.style.transform =
                "translate3d(0, 0, 0) scale(1.001)";
        };


        window.addEventListener(
            "pointermove",
            move,
            {
                passive: true
            }
        );

        document.addEventListener(
            "mouseleave",
            leave
        );


        addCleanup(() => {

            window.removeEventListener(
                "pointermove",
                move
            );

            document.removeEventListener(
                "mouseleave",
                leave
            );

        });
    }


    function setupButton(button) {

        if (!button || reducedMotion()) {
            return;
        }


        const down = () => {

            if (button.disabled) {
                return;
            }

            button.style.transform =
                "translateY(0) scale(.995)";
        };


        const up = () => {

            button.style.transform =
                "";
        };


        button.addEventListener(
            "pointerdown",
            down
        );

        button.addEventListener(
            "pointerup",
            up
        );

        button.addEventListener(
            "pointercancel",
            up
        );

        button.addEventListener(
            "pointerleave",
            up
        );


        addCleanup(() => {

            button.removeEventListener(
                "pointerdown",
                down
            );

            button.removeEventListener(
                "pointerup",
                up
            );

            button.removeEventListener(
                "pointercancel",
                up
            );

            button.removeEventListener(
                "pointerleave",
                up
            );

        });
    }


    function boot() {

        destroy();


        const page =
            document.querySelector(
                ".pt-connect-page"
            );


        if (!page) {
            return;
        }


        booted = true;


        const card =
            page.querySelector(
                ".pt-connect-card"
            );


        const background =
            page.querySelector(
                ".pt-connect-bg"
            );


        const submit =
            page.querySelector(
                ".pt-connect-submit"
            );


        createEmbers(page);

        setupCardReflection(card);

        setupBackgroundMotion(
            background
        );

        setupButton(
            submit
        );
    }


    return {
        boot,
        destroy
    };

})();