/* ==========================================================================
   PHOENIXTREND ARENA — PHOENIX FLIGHT
   arena.js
   ========================================================================== */

const Arena = {
    mounted: false,
    abort: null,
    pollTimer: 0,
    animationFrame: 0,

    state: null,

    previousPhase: null,
    previousRoundId: null,

    betAmount: 500,

    autoCashEnabled: false,
    autoCashTarget: 5,
    autoCashSent: false,

    placingBet: false,
    cancellingBet: false,
    cashingOut: false,

    playerId: null,
    playerName: "Trader",
    announcementAudio: null,
    flightAudio: null,
    announcementTimer: 0,

    lastPollAt: 0,
    pollInterval: 220,

    serverOffsetMs: 0,

    messageTimer: 0,

    elements: {},

    historyFingerprint: "",
    betFingerprint: "",

    phoenixImageReady: false,

    lastFlightProgress: 0,
    lastMultiplier: 1,

    resizeHandler: null
};


/* ==========================================================================
   BASIC HELPERS
   ========================================================================== */

function q(selector) {
    return document.querySelector(selector);
}


function qa(selector) {
    return Array.from(document.querySelectorAll(selector));
}


function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
}


function number(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
}


function formatCoins(value) {
    return Math.max(0, number(value, 0)).toLocaleString("en-US");
}


function formatMultiplier(value) {
    return `${Math.max(1, number(value, 1)).toFixed(2)}x`;
}


function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}


/* ==========================================================================
   AUTHENTICATED PLAYER + FLIGHT AUDIO
   ========================================================================== */

async function loadAuthenticatedPlayer() {
    try {
        const token = window.localStorage.getItem("phoenixtrend.auth.token");
        if (!token) return;
        const response = await fetch("/api/auth/me", {
            headers: { Authorization: `Bearer ${token}` },
            cache: "no-store"
        });
        if (!response.ok) return;
        const user = await response.json();
        const name = String(user?.display_name || user?.username || "").trim();
        if (name) Arena.playerName = name;
    } catch { }
}

function initializeFlightAudio() {
    Arena.announcementAudio = new Audio("/assets/arena/audio/announcement.mp3");
    Arena.flightAudio = new Audio("/assets/arena/audio/flight.mp3");
    Arena.announcementAudio.preload = "auto";
    Arena.flightAudio.preload = "auto";
    Arena.flightAudio.loop = true;
    Arena.announcementAudio.volume = 0.72;
    Arena.flightAudio.volume = 0.62;
}

function stopFlightAudio() {
    if (Arena.announcementTimer) {
        window.clearTimeout(Arena.announcementTimer);
        Arena.announcementTimer = 0;
    }
    for (const audio of [Arena.announcementAudio, Arena.flightAudio]) {
        if (!audio) continue;
        audio.pause();
        try { audio.currentTime = 0; } catch { }
    }
}

function playAnnouncementThenEngine() {
    stopFlightAudio();
    const announcement = Arena.announcementAudio;
    if (!announcement) return;
    announcement.currentTime = 0;
    announcement.play().catch(() => {});
    Arena.announcementTimer = window.setTimeout(() => {
        announcement.pause();
        try { announcement.currentTime = 0; } catch { }
        Arena.announcementTimer = 0;
        if (Arena.state?.round?.phase === "flying" && Arena.flightAudio) {
            Arena.flightAudio.currentTime = 0;
            Arena.flightAudio.play().catch(() => {});
        }
    }, 4000);
}

function startEngineNow() {
    if (Arena.announcementTimer) return;
    const audio = Arena.flightAudio;
    if (!audio || !audio.paused) return;
    audio.currentTime = 0;
    audio.play().catch(() => {});
}

/* ==========================================================================
   PLAYER
   ========================================================================== */

function getOrCreatePlayerId() {
    const key = "phoenixtrend.arena.player-id";

    let id = localStorage.getItem(key);

    if (!id) {
        const uuid =
            typeof crypto !== "undefined" &&
            typeof crypto.randomUUID === "function"
                ? crypto.randomUUID()
                : `${Date.now()}-${Math.random().toString(16).slice(2)}`;

        id = `pt-${uuid}`;

        localStorage.setItem(key, id);
    }

    return id;
}


/* ==========================================================================
   DOM CACHE
   ========================================================================== */

function cacheElements() {
    Arena.elements = {
        root: q("#phoenixArenaRoot"),

        balance: q("#arenaBalance"),

        history: q("#arenaHistory"),

        players: q("#arenaPlayers"),

        roundId: q("#arenaRoundId"),

        serverState: q("#arenaServerState"),

        stage: q("#arenaStage"),

        flightSvg: q("#arenaFlightSvg"),

        trail: q("#arenaTrail"),

        trailGlow: q("#arenaTrailGlow"),

        area: q("#arenaAreaPath"),

        multiplier: q("#arenaMultiplier"),

        phaseLabel: q("#arenaPhaseLabel"),

        subLabel: q("#arenaSubLabel"),

        countdown: q("#arenaCountdown"),

        countdownValue: q("#arenaCountdown strong"),

        phoenix: q("#arenaPhoenix"),

        phoenixImage: q("#arenaPhoenixImage"),

        burst: q("#arenaCrashBurst"),

        betFeed: q("#arenaBetFeed"),

        betValue: q("#arenaBetValue"),

        autoCash: q("#arenaAutoCash"),

        autoEnabled: q("#arenaAutoEnabled"),

        primary: q("#arenaPrimaryAction"),

        cancel: q("#arenaCancelAction"),

        message: q("#arenaMessage"),

        totalRounds: q("#arenaTotalRounds"),

        highest: q("#arenaHighest"),

        longest: q("#arenaLongest"),

        lastFlight: q("#arenaLastFlight"),

        commitment: q("#arenaCommitment")
    };
}


/* ==========================================================================
   REQUIRED ELEMENT CHECK
   ========================================================================== */

function validateElements() {
    const required = [
        "root",
        "balance",
        "stage",
        "trail",
        "trailGlow",
        "area",
        "multiplier",
        "phaseLabel",
        "subLabel",
        "countdown",
        "phoenix",
        "primary",
        "cancel",
        "betValue",
        "autoCash",
        "autoEnabled"
    ];

    const missing = required.filter(name => !Arena.elements[name]);

    if (missing.length) {
        console.error(
            "[PhoenixTrend Arena] Missing DOM elements:",
            missing
        );

        return false;
    }

    return true;
}


/* ==========================================================================
   API
   ========================================================================== */

async function api(path, options = {}) {
    const controller = Arena.abort;

    const token = window.localStorage.getItem("phoenixtrend.auth.token");

    const request = {
        method: options.method || "GET",

        credentials: "same-origin",

        cache: "no-store",

        signal: controller?.signal,

        headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...(options.headers || {})
        },

        ...options
    };

    const response = await fetch(path, request);

    let body = null;

    const contentType =
        response.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
        try {
            body = await response.json();
        }
        catch {
            body = null;
        }
    }
    else {
        try {
            const text = await response.text();

            body = text
                ? { detail: text }
                : null;
        }
        catch {
            body = null;
        }
    }

    if (!response.ok) {
        let detail =
            body?.detail ||
            body?.message ||
            `Arena request failed (${response.status}).`;

        if (Array.isArray(detail)) {
            detail = detail
                .map(item =>
                    item?.msg ||
                    item?.message ||
                    JSON.stringify(item)
                )
                .join(", ");
        }

        throw new Error(String(detail));
    }

    if (body === null) {
        throw new Error(
            "Arena server returned an empty response."
        );
    }

    return body;
}


/* ==========================================================================
   RESPONSE NORMALIZATION
   ========================================================================== */

function normalizeArenaResponse(response) {
    if (!response) {
        return null;
    }

    /*
     * Normal expected response:
     *
     * {
     *   ready,
     *   server_time,
     *   round,
     *   player,
     *   my_bet,
     *   bets,
     *   history,
     *   stats
     * }
     */

    if (response.round) {
        return response;
    }

    /*
     * Support:
     *
     * {
     *   state: { ... }
     * }
     */

    if (response.state?.round) {
        return response.state;
    }

    /*
     * Support:
     *
     * {
     *   arena: { ... }
     * }
     */

    if (response.arena?.round) {
        return response.arena;
    }

    /*
     * Support:
     *
     * {
     *   data: { ... }
     * }
     */

    if (response.data?.round) {
        return response.data;
    }

    return null;
}


/* ==========================================================================
   PLAYER QUERY
   ========================================================================== */

function playerQuery() {
    const params = new URLSearchParams({
        player_id: Arena.playerId,
        player_name: Arena.playerName
    });

    return params.toString();
}


/* ==========================================================================
   STATE LOAD
   ========================================================================== */

async function fetchState() {
    const state = await api(
        `/api/arena/state?${playerQuery()}`
    );

    const normalized = normalizeArenaResponse(state);

    if (!normalized) {
        throw new Error(
            "Arena state response is invalid."
        );
    }

    return normalized;
}


async function loadState() {
    const started = performance.now();

    const state = await fetchState();

    const finished = performance.now();

    updateServerClock(state);

    Arena.lastPollAt = finished;

    Arena.state = state;

    renderServerState(
        finished - started
    );

    renderState(state);
}


/* ==========================================================================
   SERVER CLOCK
   ========================================================================== */

function updateServerClock(state) {
    const serverSeconds =
        number(
            state?.server_time,
            Date.now() / 1000
        );

    Arena.serverOffsetMs =
        serverSeconds * 1000 -
        Date.now();
}


function serverNowMs() {
    return Date.now() +
        Arena.serverOffsetMs;
}


/* ==========================================================================
   SERVER STATUS
   ========================================================================== */

function renderServerState(latency) {
    const el = Arena.elements.serverState;

    if (!el) {
        return;
    }

    el.textContent =
        `SERVER SYNCED · ${Math.round(latency)}ms`;

    const parent =
        el.closest(".server-state");

    parent?.classList.add("online");

    parent?.classList.remove("offline");
}


function renderOffline() {
    const el = Arena.elements.serverState;

    if (!el) {
        return;
    }

    el.textContent =
        "ARENA SERVER OFFLINE";

    const parent =
        el.closest(".server-state");

    parent?.classList.remove("online");

    parent?.classList.add("offline");
}


/* ==========================================================================
   MAIN STATE RENDER
   ========================================================================== */

function renderState(state) {
    if (!state?.round) {
        return;
    }

    const round = state.round;

    const phaseChanged =
        Arena.previousPhase !== round.phase;

    const roundChanged =
        Arena.previousRoundId !== round.id;

    if (Arena.elements.balance) {
        Arena.elements.balance.textContent =
            formatCoins(
                state.player?.balance
            );
    }

    if (Arena.elements.roundId) {
        Arena.elements.roundId.textContent =
            String(round.id || "—")
                .slice(-12)
                .toUpperCase();
    }

    if (Arena.elements.commitment) {
        Arena.elements.commitment.textContent =
            round.commitment
                ? `${String(round.commitment).slice(0, 18)}…${String(round.commitment).slice(-10)}`
                : "Waiting for commitment…";
    }

    renderHistory(
        state.history || []
    );

    renderBets(
        state.bets || [],
        state.my_bet
    );

    renderStats(
        state.stats || {},
        state.history || []
    );

    if (roundChanged) {
        Arena.autoCashSent = false;

        Arena.lastFlightProgress = 0;

        Arena.lastMultiplier = 1;

        resetFlightVisuals();
    }

    if (phaseChanged || roundChanged) {
        onPhaseChange(
            round.phase,
            state
        );
    }

    renderControls(state);

    Arena.previousPhase =
        round.phase;

    Arena.previousRoundId =
        round.id;
}


/* ==========================================================================
   HISTORY
   ========================================================================== */

function renderHistory(history) {
    const el = Arena.elements.history;

    if (!el) {
        return;
    }

    const fingerprint =
        history
            .map(
                x =>
                    `${x.round_id}:${x.multiplier}`
            )
            .join("|");

    if (
        fingerprint ===
        Arena.historyFingerprint
    ) {
        return;
    }

    Arena.historyFingerprint =
        fingerprint;

    if (!history.length) {
        el.innerHTML = `
            <span class="history-placeholder">
                Completed flights will appear here
            </span>
        `;

        return;
    }

    el.innerHTML =
        history
            .slice(0, 14)
            .map(item => {
                const m =
                    number(
                        item.multiplier,
                        1
                    );

                let tier =
                    "micro";

                if (m >= 10) {
                    tier = "legendary";
                }
                else if (m >= 5) {
                    tier = "high";
                }
                else if (m >= 2) {
                    tier = "mid";
                }
                else if (m >= 1.30) {
                    tier = "low";
                }

                return `
                    <button
                        type="button"
                        class="history-pill ${tier}"
                        title="${escapeHtml(item.round_id)}"
                    >
                        ${m.toFixed(2)}x
                    </button>
                `;
            })
            .join("");
}


/* ==========================================================================
   BET FEED
   ========================================================================== */

function renderBets(bets, myBet) {
    const feed =
        Arena.elements.betFeed;

    if (!feed) {
        return;
    }

    const fingerprint =
        JSON.stringify({
            bets,
            myBetId: myBet?.id || null,
            myBetCash:
                myBet?.cashout_multiplier ||
                null
        });

    if (
        fingerprint ===
        Arena.betFingerprint
    ) {
        return;
    }

    Arena.betFingerprint =
        fingerprint;

    if (Arena.elements.players) {
        Arena.elements.players.textContent =
            Math.max(
                1,
                bets.length
            );
    }

    if (!bets.length) {
        feed.innerHTML = `
            <div class="feed-empty">
                <i class="ph-duotone ph-users-three"></i>
                <span>Waiting for bets…</span>
            </div>
        `;

        return;
    }

    feed.innerHTML =
        bets
            .slice()
            .reverse()
            .map((bet, index) => {
                const isMine =
                    !!myBet &&
                    String(bet.id) ===
                    String(myBet.id);

                const playerName =
                    bet.player_name ||
                    "Player";

                const initial =
                    escapeHtml(
                        playerName
                            .slice(0, 1)
                            .toUpperCase()
                    );

                const cash =
                    bet.cashed_out
                        ? `
                            <b class="feed-win">
                                ${number(
                                    bet.cashout_multiplier,
                                    1
                                ).toFixed(2)}x
                            </b>
                          `
                        : `
                            <span class="feed-pending">
                                —
                            </span>
                          `;

                return `
                    <div
                        class="feed-row ${isMine ? "mine" : ""}"
                        style="--row-delay:${Math.min(index * 20, 160)}ms"
                    >

                        <div class="feed-player">

                            <span class="feed-avatar">
                                ${initial}
                            </span>

                            <b>
                                ${escapeHtml(playerName)}
                            </b>

                        </div>

                        <strong>
                            ${formatCoins(bet.amount)}
                        </strong>

                        <div>
                            ${cash}
                        </div>

                    </div>
                `;
            })
            .join("");
}


/* ==========================================================================
   STATS
   ========================================================================== */

function renderStats(stats, history) {
    if (Arena.elements.totalRounds) {
        Arena.elements.totalRounds.textContent =
            formatCoins(
                stats.total_rounds || 0
            );
    }

    if (Arena.elements.highest) {
        Arena.elements.highest.textContent =
            stats.highest
                ? formatMultiplier(
                    stats.highest
                )
                : "—";
    }

    if (Arena.elements.longest) {
        Arena.elements.longest.textContent =
            stats.longest_seconds
                ? `${number(
                    stats.longest_seconds,
                    0
                ).toFixed(1)}s`
                : "—";
    }

    if (Arena.elements.lastFlight) {
        Arena.elements.lastFlight.textContent =
            history.length
                ? formatMultiplier(
                    history[0].multiplier
                )
                : "—";
    }
}


/* ==========================================================================
   CONTROL STATE
   ========================================================================== */

function renderControls(state) {
    if (!state?.round) {
        return;
    }

    const phase =
        state.round.phase;

    const myBet =
        state.my_bet;

    const primary =
        Arena.elements.primary;

    const cancel =
        Arena.elements.cancel;

    if (!primary || !cancel) {
        return;
    }

    primary.classList.remove(
        "cashout",
        "locked",
        "success",
        "loading"
    );

    cancel.disabled = true;

    if (Arena.placingBet) {
        primary.disabled = true;

        primary.classList.add(
            "loading"
        );

        primary.innerHTML = `
            <i class="ph-duotone ph-circle-notch"></i>

            <span>
                <b>PLACING BET…</b>
                <small>
                    ${formatCoins(Arena.betAmount)}
                    PHOENIX COINS
                </small>
            </span>
        `;

        return;
    }

    if (Arena.cashingOut) {
        primary.disabled = true;

        primary.classList.add(
            "loading"
        );

        primary.innerHTML = `
            <i class="ph-duotone ph-circle-notch"></i>

            <span>
                <b>CASHING OUT…</b>
                <small>
                    CONFIRMING WITH SERVER
                </small>
            </span>
        `;

        return;
    }

    if (phase === "countdown") {
        if (myBet) {
            primary.disabled = true;

            primary.classList.add(
                "locked"
            );

            primary.innerHTML = `
                <i class="ph-duotone ph-check-circle"></i>

                <span>

                    <b>
                        BET LOCKED IN
                    </b>

                    <small>
                        ${formatCoins(myBet.amount)}
                        PHOENIX COINS
                    </small>

                </span>
            `;

            cancel.disabled =
                Arena.cancellingBet;
        }
        else {
            primary.disabled = false;

            primary.innerHTML = `
                <i class="ph-duotone ph-rocket-launch"></i>

                <span>

                    <b>
                        PLACE BET
                    </b>

                    <small>
                        ${formatCoins(Arena.betAmount)}
                        PHOENIX COINS
                    </small>

                </span>
            `;
        }

        return;
    }

    if (phase === "flying") {
        cancel.disabled = true;

        if (
            myBet &&
            !myBet.cashed_out
        ) {
            primary.disabled = false;

            primary.classList.add(
                "cashout"
            );

            const current =
                visualMultiplier();

            const payout =
                Math.floor(
                    number(
                        myBet.amount,
                        0
                    ) *
                    current
                );

            primary.innerHTML = `
                <i class="ph-duotone ph-coins"></i>

                <span>

                    <b>
                        CASH OUT
                        ${current.toFixed(2)}x
                    </b>

                    <small>
                        RETURN
                        ${formatCoins(payout)}
                        COINS
                    </small>

                </span>
            `;
        }
        else if (
            myBet?.cashed_out
        ) {
            primary.disabled = true;

            primary.classList.add(
                "success"
            );

            primary.innerHTML = `
                <i class="ph-duotone ph-check-circle"></i>

                <span>

                    <b>
                        CASHED OUT
                        ${number(
                            myBet.cashout_multiplier,
                            1
                        ).toFixed(2)}x
                    </b>

                    <small>
                        +${formatCoins(myBet.payout)}
                        COINS RETURNED
                    </small>

                </span>
            `;
        }
        else {
            primary.disabled = true;

            primary.classList.add(
                "locked"
            );

            primary.innerHTML = `
                <i class="ph-duotone ph-airplane-tilt"></i>

                <span>

                    <b>
                        FLIGHT IN PROGRESS
                    </b>

                    <small>
                        BET NEXT ROUND
                    </small>

                </span>
            `;
        }

        return;
    }

    primary.disabled = true;

    primary.classList.add(
        "locked"
    );

    primary.innerHTML = `
        <i class="ph-duotone ph-fire"></i>

        <span>

            <b>
                ROUND COMPLETE
            </b>

            <small>
                NEXT FLIGHT OPENING SOON
            </small>

        </span>
    `;
}


/* ==========================================================================
   PHASE CHANGE
   ========================================================================== */

function onPhaseChange(phase, state) {
    const stage =
        Arena.elements.stage;

    const phoenix =
        Arena.elements.phoenix;

    const burst =
        Arena.elements.burst;

    if (!stage) {
        return;
    }

    stage.classList.remove(
        "phase-countdown",
        "phase-flying",
        "phase-crashed"
    );

    stage.classList.add(
        `phase-${phase}`
    );

    if (phase === "countdown") {
        if (Arena.elements.phaseLabel) {
            Arena.elements.phaseLabel.textContent =
                "PHOENIX FLIGHT";
        }

        if (Arena.elements.subLabel) {
            Arena.elements.subLabel.textContent =
                "Place your virtual coin bet before launch";
        }

        if (Arena.elements.multiplier) {
            Arena.elements.multiplier.textContent =
                "1.00x";
        }

        Arena.elements.countdown?.classList.add(
            "visible"
        );

        phoenix?.classList.remove(
            "flying",
            "fly-away",
            "crashed"
        );

        burst?.classList.remove(
            "active"
        );

        resetFlightVisuals();
        playAnnouncementThenEngine();

        return;
    }

    if (phase === "flying") {
        if (Arena.elements.phaseLabel) {
            Arena.elements.phaseLabel.textContent =
                "LIVE MULTIPLIER";
        }

        if (Arena.elements.subLabel) {
            Arena.elements.subLabel.textContent =
                "Cash out before the Phoenix flies away";
        }

        Arena.elements.countdown?.classList.remove(
            "visible"
        );

        phoenix?.classList.remove(
            "fly-away",
            "crashed"
        );

        phoenix?.classList.add(
            "flying"
        );

        burst?.classList.remove(
            "active"
        );

        startEngineNow();
        return;
    }

    if (phase === "crashed") {
        const crash =
            number(
                state.round.crash_multiplier,
                1
            );

        if (Arena.elements.phaseLabel) {
            Arena.elements.phaseLabel.textContent =
                "PHOENIX FLEW AWAY";
        }

        if (Arena.elements.subLabel) {
            Arena.elements.subLabel.textContent =
                `Round ended at ${crash.toFixed(2)}x`;
        }

        if (Arena.elements.multiplier) {
            Arena.elements.multiplier.textContent =
                `${crash.toFixed(2)}x`;
        }

        Arena.elements.countdown?.classList.remove(
            "visible"
        );

        phoenix?.classList.remove(
            "flying"
        );

        phoenix?.classList.add(
            "fly-away"
        );

        stopFlightAudio();

        burst?.classList.add(
            "active"
        );

        window.setTimeout(
            () => {
                burst?.classList.remove(
                    "active"
                );
            },
            850
        );
    }
}


/* ==========================================================================
   PHOENIX IMAGE
   ========================================================================== */

function initializePhoenixImage() {
    const image =
        Arena.elements.phoenixImage;

    const phoenix =
        Arena.elements.phoenix;

    if (!image || !phoenix) {
        return;
    }

    const markReady = () => {
        Arena.phoenixImageReady = true;

        phoenix.classList.add(
            "image-ready"
        );

        phoenix.classList.remove(
            "image-error"
        );
    };

    const markError = () => {
        Arena.phoenixImageReady = false;

        phoenix.classList.remove(
            "image-ready"
        );

        phoenix.classList.add(
            "image-error"
        );

        console.error(
            "[PhoenixTrend Arena] Phoenix image failed to load:",
            image.src
        );
    };

    image.addEventListener(
        "load",
        markReady,
        {
            signal: Arena.abort.signal
        }
    );

    image.addEventListener(
        "error",
        markError,
        {
            signal: Arena.abort.signal
        }
    );

    if (
        image.complete &&
        image.naturalWidth > 0
    ) {
        markReady();
    }
}


/* ==========================================================================
   RESET FLIGHT
   ========================================================================== */

function resetFlightVisuals() {
    const start =
        pointForProgress(0);

    const startPath =
        `M ${start.x.toFixed(2)} ${start.y.toFixed(2)}`;

    Arena.elements.trail?.setAttribute(
        "d",
        startPath
    );

    Arena.elements.trailGlow?.setAttribute(
        "d",
        startPath
    );

    Arena.elements.area?.setAttribute(
        "d",
        `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} L ${start.x.toFixed(2)} 520 Z`
    );

    Arena.lastFlightProgress = 0;

    Arena.lastMultiplier = 1;

    positionPhoenixAtProgress(
        0,
        1
    );

    if (Arena.elements.phoenix) {
        Arena.elements.phoenix.style.opacity =
            "1";
    }

    Arena.elements.stage?.style.setProperty(
        "--flight-intensity",
        "0"
    );
}


/* ==========================================================================
   MULTIPLIER
   ========================================================================== */

function visualMultiplier() {
    const state =
        Arena.state;

    if (!state?.round) {
        return 1;
    }

    const round =
        state.round;

    if (round.phase === "countdown") {
        return 1;
    }

    if (round.phase === "crashed") {
        return Math.max(
            1,
            number(
                round.crash_multiplier,
                1
            )
        );
    }

    /*
     * Prefer server supplied start timestamp.
     */

    if (round.started_at) {
        const startedAt =
            number(
                round.started_at,
                0
            );

        if (startedAt > 0) {
            const elapsed =
                Math.max(
                    0,
                    (
                        serverNowMs() -
                        startedAt * 1000
                    ) /
                    1000
                );

            return Math.max(
                1,
                Math.exp(
                    elapsed * 0.115
                )
            );
        }
    }

    /*
     * Fallback to server multiplier.
     */

    return Math.max(
        1,
        number(
            round.current_multiplier,
            1
        )
    );
}


/* ==========================================================================
   FLIGHT PROGRESS
   ========================================================================== */

function flightProgress(multiplier) {
    const safe =
        Math.max(
            1,
            number(
                multiplier,
                1
            )
        );

    /*
     * Faster initial movement than the old implementation.
     *
     * 1.00x -> 0
     * 1.25x -> visible movement
     * 2.00x -> meaningful travel
     * 5.00x -> high into the chart
     * 25x   -> near chart end
     */

    const log =
        Math.log(safe);

    return clamp(
        log / Math.log(25),
        0,
        1
    );
}


/* ==========================================================================
   FLIGHT CURVE
   ========================================================================== */

function pointForProgress(progress) {
    const p =
        clamp(
            progress,
            0,
            1
        );

    const x =
        34 +
        p * 895;

    /*
     * Curved acceleration.
     */

    const rise =
        0.14 * p +
        0.86 * p * p;

    const y =
        505 -
        rise * 430;

    return {
        x,
        y
    };
}


/* ==========================================================================
   BUILD PATH
   ========================================================================== */

function buildPath(progress, samples = 100) {
    const p =
        clamp(
            progress,
            0,
            1
        );

    const points = [];

    /*
     * Always generate enough points for a smooth curve.
     */

    const count =
        Math.max(
            8,
            Math.ceil(
                samples *
                Math.max(
                    p,
                    0.08
                )
            )
        );

    for (
        let i = 0;
        i <= count;
        i += 1
    ) {
        const local =
            (i / count) *
            p;

        points.push(
            pointForProgress(
                local
            )
        );
    }

    return points;
}


/* ==========================================================================
   PATH STRING
   ========================================================================== */

function pathString(points) {
    if (!points.length) {
        return "M 34 505";
    }

    return points
        .map(
            (point, index) =>
                `${index === 0 ? "M" : "L"} ${point.x.toFixed(2)} ${point.y.toFixed(2)}`
        )
        .join(" ");
}


/* ==========================================================================
   AREA STRING
   ========================================================================== */

function areaString(points) {
    if (!points.length) {
        return "M 34 505 L 34 520 Z";
    }

    const first =
        points[0];

    const last =
        points[
            points.length - 1
        ];

    return (
        `${pathString(points)} ` +
        `L ${last.x.toFixed(2)} 520 ` +
        `L ${first.x.toFixed(2)} 520 Z`
    );
}


/* ==========================================================================
   PHOENIX POSITION
   ========================================================================== */

function positionPhoenixAtProgress(
    progress,
    multiplier
) {
    const stage =
        Arena.elements.stage;

    const phoenix =
        Arena.elements.phoenix;

    if (!stage || !phoenix) {
        return;
    }

    const p =
        clamp(
            progress,
            0,
            1
        );

    const point =
        pointForProgress(p);

    /*
     * Get a nearby point to calculate trajectory angle.
     */

    const previousPoint =
        pointForProgress(
            Math.max(
                0,
                p - 0.01
            )
        );

    const rect =
        stage.getBoundingClientRect();

    if (
        rect.width <= 0 ||
        rect.height <= 0
    ) {
        return;
    }

    /*
     * SVG viewBox:
     *
     * 0 0 1000 540
     *
     * Convert exact SVG coordinate to exact CSS pixel position.
     */

    const px =
        (point.x / 1000) *
        rect.width;

    const py =
        (point.y / 540) *
        rect.height;

    const dx =
        point.x -
        previousPoint.x;

    const dy =
        point.y -
        previousPoint.y;

    let angle =
        Math.atan2(
            dy,
            dx
        ) *
        180 /
        Math.PI;

    angle =
        clamp(
            angle,
            -32,
            -2
        );

    /*
     * CRITICAL:
     *
     * left/top are the exact same endpoint used by the SVG path.
     *
     * translate(-50%, -50%) makes the CENTER of the Phoenix
     * sit on the path endpoint.
     */

    phoenix.style.left =
        `${px}px`;

    phoenix.style.top =
        `${py}px`;

    phoenix.style.transform =
        `translate(-50%, -50%) rotate(${angle.toFixed(2)}deg)`;

    phoenix.style.opacity =
        "1";

    phoenix.style.setProperty(
        "--phoenix-angle",
        `${angle.toFixed(2)}deg`
    );

    phoenix.style.setProperty(
        "--phoenix-progress",
        p.toFixed(4)
    );

    phoenix.style.setProperty(
        "--phoenix-multiplier",
        number(
            multiplier,
            1
        ).toFixed(3)
    );
}


/* ==========================================================================
   DRAW FLIGHT
   ========================================================================== */

function drawFlight(multiplier) {
    const safeMultiplier =
        Math.max(
            1,
            number(
                multiplier,
                1
            )
        );

    const progress =
        roundVisualProgress(
            safeMultiplier
        );

    const points =
        buildPath(
            progress
        );

    const path =
        pathString(
            points
        );

    Arena.elements.trail?.setAttribute(
        "d",
        path
    );

    Arena.elements.trailGlow?.setAttribute(
        "d",
        path
    );

    Arena.elements.area?.setAttribute(
        "d",
        areaString(
            points
        )
    );

    /*
     * EXACT same progress used for:
     *
     * 1. SVG line
     * 2. Phoenix position
     */

    positionPhoenixAtProgress(
        progress,
        safeMultiplier
    );

    Arena.lastFlightProgress =
        progress;

    Arena.lastMultiplier =
        safeMultiplier;

    const intensity =
        clamp(
            (
                safeMultiplier -
                1
            ) /
            8,
            0,
            1
        );

    Arena.elements.stage?.style.setProperty(
        "--flight-intensity",
        intensity.toFixed(3)
    );
}


/* ==========================================================================
   VISUAL PROGRESS
   ========================================================================== */

function roundVisualProgress(multiplier) {
    return flightProgress(
        multiplier
    );
}


/* ==========================================================================
   FRAME LOOP
   ========================================================================== */

function renderFlightFrame() {
    if (!Arena.mounted) {
        return;
    }

    const round =
        Arena.state?.round;

    if (round) {
        if (
            round.phase ===
            "countdown"
        ) {
            renderCountdownFrame(
                round
            );

            drawFlight(1);
        }

        else if (
            round.phase ===
            "flying"
        ) {
            const multiplier =
                visualMultiplier();

            if (
                Arena.elements.multiplier
            ) {
                Arena.elements.multiplier.textContent =
                    `${multiplier.toFixed(2)}x`;
            }

            drawFlight(
                multiplier
            );

            updateLiveCashoutButton(
                multiplier
            );

            maybeAutoCashout(
                multiplier
            );
        }

        else if (
            round.phase ===
            "crashed"
        ) {
            const crash =
                Math.max(
                    1,
                    number(
                        round.crash_multiplier,
                        1
                    )
                );

            drawFlight(
                crash
            );
        }
    }

    Arena.animationFrame =
        requestAnimationFrame(
            renderFlightFrame
        );
}


/* ==========================================================================
   COUNTDOWN
   ========================================================================== */

function renderCountdownFrame(round) {
    if (
        !Arena.elements.countdownValue
    ) {
        return;
    }

    let remaining =
        number(
            round.countdown,
            0
        );

    /*
     * countdown is the server snapshot.
     * Reduce locally between polls.
     */

    if (Arena.lastPollAt) {
        remaining -=
            (
                performance.now() -
                Arena.lastPollAt
            ) /
            1000;
    }

    remaining =
        Math.max(
            0,
            remaining
        );

    Arena.elements.countdownValue.textContent =
        String(
            Math.max(
                1,
                Math.ceil(
                    remaining
                )
            )
        );
}


/* ==========================================================================
   LIVE CASHOUT BUTTON
   ========================================================================== */

function updateLiveCashoutButton(
    multiplier
) {
    if (
        Arena.cashingOut ||
        Arena.placingBet
    ) {
        return;
    }

    const state =
        Arena.state;

    const myBet =
        state?.my_bet;

    if (
        !myBet ||
        myBet.cashed_out ||
        state?.round?.phase !== "flying"
    ) {
        return;
    }

    const primary =
        Arena.elements.primary;

    if (!primary) {
        return;
    }

    const payout =
        Math.floor(
            number(
                myBet.amount,
                0
            ) *
            multiplier
        );

    primary.disabled = false;

    primary.classList.add(
        "cashout"
    );

    primary.innerHTML = `
        <i class="ph-duotone ph-coins"></i>

        <span>

            <b>
                CASH OUT
                ${multiplier.toFixed(2)}x
            </b>

            <small>
                RETURN
                ${formatCoins(payout)}
                COINS
            </small>

        </span>
    `;
}


/* ==========================================================================
   AUTO CASH OUT
   ========================================================================== */

async function maybeAutoCashout(
    multiplier
) {
    if (
        !Arena.autoCashEnabled ||
        Arena.autoCashSent ||
        Arena.cashingOut
    ) {
        return;
    }

    const myBet =
        Arena.state?.my_bet;

    if (
        !myBet ||
        myBet.cashed_out
    ) {
        return;
    }

    if (
        Arena.state?.round?.phase !==
        "flying"
    ) {
        return;
    }

    const target =
        number(
            Arena.autoCashTarget,
            5
        );

    if (
        target <= 1 ||
        multiplier < target
    ) {
        return;
    }

    Arena.autoCashSent = true;

    try {
        await cashOut(true);
    }
    catch {
        Arena.autoCashSent = false;
    }
}


/* ==========================================================================
   MESSAGE
   ========================================================================== */

function showMessage(
    text,
    type = "info"
) {
    const el =
        Arena.elements.message;

    if (!el) {
        return;
    }

    window.clearTimeout(
        Arena.messageTimer
    );

    el.className =
        `arena-message visible ${type}`;

    el.textContent =
        String(text || "");

    Arena.messageTimer =
        window.setTimeout(
            () => {
                el.classList.remove(
                    "visible"
                );
            },
            4200
        );
}


/* ==========================================================================
   APPLY ACTION RESPONSE
   ========================================================================== */

async function applyActionResponse(
    response
) {
    let state =
        normalizeArenaResponse(
            response
        );

    /*
     * Some backend endpoints return only:
     *
     * { success: true }
     *
     * If so, immediately fetch authoritative state.
     */

    if (!state) {
        state =
            await fetchState();
    }

    updateServerClock(
        state
    );

    Arena.lastPollAt =
        performance.now();

    Arena.state =
        state;

    renderState(
        state
    );

    return state;
}


/* ==========================================================================
   PLACE BET
   ========================================================================== */

async function placeBet() {
    if (Arena.placingBet) {
        return;
    }

    const state =
        Arena.state;

    if (!state?.round) {
        showMessage(
            "Arena is still connecting.",
            "error"
        );

        return;
    }

    if (
        state.round.phase !==
        "countdown"
    ) {
        showMessage(
            "Betting is closed for this flight.",
            "error"
        );

        return;
    }

    if (state.my_bet) {
        showMessage(
            "You already have a bet in this round.",
            "info"
        );

        return;
    }

    const amount =
        Math.floor(
            number(
                Arena.betAmount,
                500
            )
        );

    if (
        amount < 100 ||
        amount > 2500
    ) {
        showMessage(
            "Bet must be between 100 and 2,500 Phoenix Coins.",
            "error"
        );

        return;
    }

    const balance =
        number(
            state.player?.balance,
            0
        );

    if (
        balance > 0 &&
        amount > balance
    ) {
        showMessage(
            "Not enough Phoenix Coins.",
            "error"
        );

        return;
    }

    Arena.placingBet = true;

    renderControls(
        state
    );

    try {
        const response =
            await api(
                "/api/arena/bet",
                {
                    method: "POST",

                    body: JSON.stringify({
                        player_id:
                            Arena.playerId,

                        player_name:
                            Arena.playerName,

                        amount
                    })
                }
            );

        const updatedState =
            await applyActionResponse(
                response
            );

        if (!updatedState.my_bet) {
            /*
             * Force one extra state read in case the action
             * endpoint committed successfully but returned
             * before the snapshot reflected it.
             */

            const confirmed =
                await fetchState();

            updateServerClock(
                confirmed
            );

            Arena.state =
                confirmed;

            Arena.lastPollAt =
                performance.now();

            renderState(
                confirmed
            );
        }

        if (
            Arena.state?.my_bet
        ) {
            showMessage(
                `${formatCoins(amount)} Phoenix Coins locked into this flight.`,
                "success"
            );
        }
        else {
            showMessage(
                "Bet request completed but the server did not return an active bet.",
                "error"
            );
        }
    }
    catch (error) {
        console.error(
            "[PhoenixTrend Arena] Place bet failed:",
            error
        );

        showMessage(
            error?.message ||
            "Unable to place bet.",
            "error"
        );

        /*
         * Re-sync state after any action failure.
         */

        try {
            const refreshed =
                await fetchState();

            Arena.state =
                refreshed;

            updateServerClock(
                refreshed
            );

            Arena.lastPollAt =
                performance.now();

            renderState(
                refreshed
            );
        }
        catch {
            // Poll loop will retry.
        }
    }
    finally {
        Arena.placingBet = false;

        if (Arena.state) {
            renderControls(
                Arena.state
            );
        }
    }
}


/* ==========================================================================
   CANCEL BET
   ========================================================================== */

async function cancelBet() {
    if (
        Arena.cancellingBet
    ) {
        return;
    }

    const state =
        Arena.state;

    if (
        !state?.my_bet
    ) {
        return;
    }

    if (
        state.round?.phase !==
        "countdown"
    ) {
        showMessage(
            "The flight has already launched.",
            "error"
        );

        return;
    }

    Arena.cancellingBet = true;

    if (Arena.elements.cancel) {
        Arena.elements.cancel.disabled =
            true;
    }

    try {
        const response =
            await api(
                "/api/arena/cancel",
                {
                    method: "POST",

                    body: JSON.stringify({
                        player_id:
                            Arena.playerId,

                        player_name:
                            Arena.playerName
                    })
                }
            );

        await applyActionResponse(
            response
        );

        /*
         * Ensure the cancelled bet disappeared.
         */

        if (
            Arena.state?.my_bet
        ) {
            const confirmed =
                await fetchState();

            Arena.state =
                confirmed;

            updateServerClock(
                confirmed
            );

            Arena.lastPollAt =
                performance.now();

            renderState(
                confirmed
            );
        }

        showMessage(
            "Bet cancelled and Phoenix Coins returned.",
            "info"
        );
    }
    catch (error) {
        console.error(
            "[PhoenixTrend Arena] Cancel bet failed:",
            error
        );

        showMessage(
            error?.message ||
            "Unable to cancel bet.",
            "error"
        );
    }
    finally {
        Arena.cancellingBet =
            false;

        if (Arena.state) {
            renderControls(
                Arena.state
            );
        }
    }
}


/* ==========================================================================
   CASH OUT
   ========================================================================== */

async function cashOut(
    automatic = false
) {
    if (Arena.cashingOut) {
        return;
    }

    const state =
        Arena.state;

    const myBet =
        state?.my_bet;

    if (!myBet) {
        return;
    }

    if (myBet.cashed_out) {
        return;
    }

    if (
        state?.round?.phase !==
        "flying"
    ) {
        if (!automatic) {
            showMessage(
                "Cash out is only available while the Phoenix is flying.",
                "error"
            );
        }

        return;
    }

    Arena.cashingOut = true;

    renderControls(
        state
    );

    try {
        const response =
            await api(
                "/api/arena/cashout",
                {
                    method: "POST",

                    body: JSON.stringify({
                        player_id:
                            Arena.playerId,

                        player_name:
                            Arena.playerName
                    })
                }
            );

        const updatedState =
            await applyActionResponse(
                response
            );

        let bet =
            updatedState.my_bet;

        if (
            !bet?.cashed_out
        ) {
            const confirmed =
                await fetchState();

            Arena.state =
                confirmed;

            updateServerClock(
                confirmed
            );

            Arena.lastPollAt =
                performance.now();

            renderState(
                confirmed
            );

            bet =
                confirmed.my_bet;
        }

        if (
            bet?.cashed_out
        ) {
            showMessage(
                `${automatic ? "Auto cash-out" : "Cash-out"} confirmed at ${number(
                    bet.cashout_multiplier,
                    1
                ).toFixed(2)}x.`,
                "success"
            );
        }
        else {
            showMessage(
                "Cash-out response was not confirmed by the server.",
                "error"
            );
        }
    }
    catch (error) {
        console.error(
            "[PhoenixTrend Arena] Cash out failed:",
            error
        );

        if (automatic) {
            Arena.autoCashSent =
                false;
        }

        showMessage(
            error?.message ||
            "Unable to cash out.",
            "error"
        );
    }
    finally {
        Arena.cashingOut = false;

        if (Arena.state) {
            renderControls(
                Arena.state
            );
        }
    }
}


/* ==========================================================================
   BET CHIP
   ========================================================================== */

function selectBetAmount(
    button
) {
    if (
        Arena.state?.my_bet ||
        Arena.placingBet
    ) {
        return;
    }

    const amount =
        Math.floor(
            number(
                button.dataset.arenaBet,
                500
            )
        );

    Arena.betAmount =
        clamp(
            amount,
            100,
            2500
        );

    if (
        Arena.elements.betValue
    ) {
        Arena.elements.betValue.textContent =
            formatCoins(
                Arena.betAmount
            );
    }

    qa("[data-arena-bet]")
        .forEach(item => {
            item.classList.toggle(
                "active",
                item === button
            );
        });

    if (Arena.state) {
        renderControls(
            Arena.state
        );
    }
}


/* ==========================================================================
   AUTO CASH CHIP
   ========================================================================== */

function selectAutoCash(
    button
) {
    const value =
        clamp(
            number(
                button.dataset.arenaAuto,
                5
            ),
            1.01,
            100
        );

    Arena.autoCashTarget =
        value;

    Arena.autoCashEnabled =
        true;

    Arena.autoCashSent =
        false;

    if (
        Arena.elements.autoCash
    ) {
        Arena.elements.autoCash.value =
            value.toFixed(2);
    }

    if (
        Arena.elements.autoEnabled
    ) {
        Arena.elements.autoEnabled.checked =
            true;
    }

    qa("[data-arena-auto]")
        .forEach(item => {
            item.classList.toggle(
                "active",
                item === button
            );
        });
}


/* ==========================================================================
   BIND EVENTS
   ========================================================================== */

function bindEvents() {
    qa("[data-arena-bet]")
        .forEach(button => {
            button.addEventListener(
                "click",
                () => {
                    selectBetAmount(
                        button
                    );
                },
                {
                    signal:
                        Arena.abort.signal
                }
            );
        });


    qa("[data-arena-auto]")
        .forEach(button => {
            button.addEventListener(
                "click",
                () => {
                    selectAutoCash(
                        button
                    );
                },
                {
                    signal:
                        Arena.abort.signal
                }
            );
        });


    Arena.elements.autoCash
        ?.addEventListener(
            "change",
            () => {
                const value =
                    clamp(
                        number(
                            Arena.elements.autoCash.value,
                            5
                        ),
                        1.01,
                        100
                    );

                Arena.autoCashTarget =
                    value;

                Arena.elements.autoCash.value =
                    value.toFixed(2);

                Arena.autoCashSent =
                    false;
            },
            {
                signal:
                    Arena.abort.signal
            }
        );


    Arena.elements.autoEnabled
        ?.addEventListener(
            "change",
            () => {
                Arena.autoCashEnabled =
                    Arena.elements.autoEnabled.checked;

                Arena.autoCashSent =
                    false;
            },
            {
                signal:
                    Arena.abort.signal
            }
        );


    Arena.elements.primary
        ?.addEventListener(
            "click",
            async event => {
                event.preventDefault();

                event.stopPropagation();

                const phase =
                    Arena.state
                        ?.round
                        ?.phase;

                if (
                    phase ===
                    "countdown"
                ) {
                    playAnnouncementThenEngine();
                    await placeBet();
                }

                else if (
                    phase ===
                    "flying"
                ) {
                    await cashOut(
                        false
                    );
                }
            },
            {
                signal:
                    Arena.abort.signal
            }
        );


    Arena.elements.cancel
        ?.addEventListener(
            "click",
            async event => {
                event.preventDefault();

                event.stopPropagation();

                await cancelBet();
            },
            {
                signal:
                    Arena.abort.signal
            }
        );


    Arena.resizeHandler =
        () => {
            if (!Arena.mounted) {
                return;
            }

            drawFlight(
                Arena.lastMultiplier ||
                1
            );
        };


    window.addEventListener(
        "resize",
        Arena.resizeHandler,
        {
            signal:
                Arena.abort.signal
        }
    );
}


/* ==========================================================================
   POLLING
   ========================================================================== */

async function pollLoop() {
    if (!Arena.mounted) {
        return;
    }

    try {
        await loadState();
    }
    catch (error) {
        if (
            error?.name !==
            "AbortError"
        ) {
            console.error(
                "[PhoenixTrend Arena] State poll failed:",
                error
            );

            renderOffline();
        }
    }
    finally {
        if (Arena.mounted) {
            Arena.pollTimer =
                window.setTimeout(
                    pollLoop,
                    Arena.pollInterval
                );
        }
    }
}


/* ==========================================================================
   MOUNT
   ========================================================================== */

export async function mountPhoenixArena() {
    if (Arena.mounted) {
        return;
    }

    Arena.mounted = true;

    Arena.abort =
        new AbortController();

    Arena.playerId =
        getOrCreatePlayerId();

    await loadAuthenticatedPlayer();
    initializeFlightAudio();

    cacheElements();

    if (!validateElements()) {
        Arena.mounted = false;

        Arena.abort.abort();

        Arena.abort = null;

        return;
    }

    initializePhoenixImage();

    bindEvents();

    resetFlightVisuals();

    /*
     * Start visual loop immediately.
     */

    Arena.animationFrame =
        requestAnimationFrame(
            renderFlightFrame
        );

    /*
     * First state load.
     */

    try {
        await loadState();
    }
    catch (error) {
        if (
            error?.name !==
            "AbortError"
        ) {
            console.error(
                "[PhoenixTrend Arena] Initial state load failed:",
                error
            );

            renderOffline();

            showMessage(
                error?.message ||
                "Unable to connect to Arena server.",
                "error"
            );
        }
    }

    /*
     * Continue polling after initial load.
     */

    if (Arena.mounted) {
        Arena.pollTimer =
            window.setTimeout(
                pollLoop,
                Arena.pollInterval
            );
    }
}


/* ==========================================================================
   UNMOUNT
   ========================================================================== */

export function unmountPhoenixArena() {
    Arena.mounted = false;
    stopFlightAudio();

    if (Arena.abort) {
        Arena.abort.abort();
    }

    if (Arena.pollTimer) {
        window.clearTimeout(
            Arena.pollTimer
        );
    }

    if (Arena.animationFrame) {
        cancelAnimationFrame(
            Arena.animationFrame
        );
    }

    if (Arena.messageTimer) {
        window.clearTimeout(
            Arena.messageTimer
        );
    }

    Arena.abort = null;

    Arena.pollTimer = 0;

    Arena.animationFrame = 0;

    Arena.messageTimer = 0;

    Arena.state = null;

    Arena.previousPhase = null;

    Arena.previousRoundId = null;

    Arena.historyFingerprint = "";

    Arena.betFingerprint = "";

    Arena.placingBet = false;

    Arena.cancellingBet = false;

    Arena.cashingOut = false;

    Arena.autoCashSent = false;

    Arena.phoenixImageReady = false;

    Arena.lastFlightProgress = 0;

    Arena.lastMultiplier = 1;

    Arena.resizeHandler = null;

    Arena.elements = {};
}