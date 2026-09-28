/* ============================================================
   PHOENIXTREND PROFESSIONAL CHART WORKSTATION
   wwwroot/js/phoenix-chart.js

   Real provider-backed OHLCV only.
   No generated candles.
   No interpolated "live" movement.
   ============================================================ */

(() => {
    const state = {
        chart: null,
        candleSeries: null,
        volumeSeries: null,

        ema9Series: null,
        ema20Series: null,
        ema50Series: null,
        ema200Series: null,

        rsiChart: null,
        rsiSeries: null,
        rsi70Series: null,
        rsi30Series: null,

        macdChart: null,
        macdSeries: null,
        macdSignalSeries: null,
        macdHistogramSeries: null,

        resizeObserver: null,

        container: null,
        rsiContainer: null,
        macdContainer: null,

        bars: [],
        symbol: "",
        timeframe: "",
        range: "",

        indicatorsVisible: true,

        supportLines: [],
        resistanceLines: [],
        tradeLines: [],

        drawings: [],
        drawingTool: "crosshair",
        drawingStart: null,
        drawingOverlay: null,
        activeDrawing: null,

        eventMarkers: [],

        crosshairHandler: null,
        visibleRangeHandler: null,

        websocket: null,
        websocketReconnectTimer: null,
        pollingTimer: null,

        liveOptions: null,
        destroyed: false
    };


    // ============================================================
    // LIGHTWEIGHT CHARTS
    // ============================================================

    const lc = () => window.LightweightCharts;


    // ============================================================
    // GENERIC HELPERS
    // ============================================================

    function numberOrNull(value) {
        if (value === null || value === undefined || value === "") {
            return null;
        }

        const number = Number(value);

        return Number.isFinite(number)
            ? number
            : null;
    }


    function parseTime(value) {
        if (value === null || value === undefined) {
            return null;
        }

        if (typeof value === "number") {
            if (!Number.isFinite(value)) {
                return null;
            }

            return value > 100000000000
                ? Math.floor(value / 1000)
                : Math.floor(value);
        }

        if (
            typeof value === "object" &&
            value.year &&
            value.month &&
            value.day
        ) {
            return value;
        }

        const raw = String(value).trim();

        if (!raw) {
            return null;
        }

        if (/^\d+$/.test(raw)) {
            const number = Number(raw);

            if (!Number.isFinite(number)) {
                return null;
            }

            return number > 100000000000
                ? Math.floor(number / 1000)
                : Math.floor(number);
        }

        const milliseconds = Date.parse(raw);

        if (Number.isFinite(milliseconds)) {
            return Math.floor(milliseconds / 1000);
        }

        return raw;
    }


    function timeKey(time) {
        if (time === null || time === undefined) {
            return "";
        }

        if (typeof time === "object") {
            return `${time.year}-${time.month}-${time.day}`;
        }

        return String(time);
    }


    function comparableTime(time) {
        if (typeof time === "number") {
            return time;
        }

        if (
            typeof time === "object" &&
            time.year &&
            time.month &&
            time.day
        ) {
            return Date.UTC(
                time.year,
                time.month - 1,
                time.day
            ) / 1000;
        }

        const parsed = Date.parse(String(time));

        return Number.isFinite(parsed)
            ? parsed / 1000
            : 0;
    }


    function formatPrice(value) {
        const number = Number(value);

        if (!Number.isFinite(number)) {
            return "—";
        }

        if (Math.abs(number) >= 1000) {
            return number.toLocaleString(
                undefined,
                {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                }
            );
        }

        if (Math.abs(number) >= 1) {
            return number.toFixed(2);
        }

        return number.toFixed(4);
    }


    function formatVolume(value) {
        const number = Number(value);

        if (!Number.isFinite(number)) {
            return "—";
        }

        if (Math.abs(number) >= 1_000_000_000) {
            return `${(number / 1_000_000_000).toFixed(2)}B`;
        }

        if (Math.abs(number) >= 1_000_000) {
            return `${(number / 1_000_000).toFixed(2)}M`;
        }

        if (Math.abs(number) >= 1_000) {
            return `${(number / 1_000).toFixed(1)}K`;
        }

        return number.toLocaleString();
    }


    function normalizeBar(item) {
        if (!item) {
            return null;
        }

        const time = parseTime(
            item.time ??
            item.timestamp ??
            item.datetime ??
            item.date
        );

        const open = numberOrNull(item.open);
        const high = numberOrNull(item.high);
        const low = numberOrNull(item.low);
        const close = numberOrNull(item.close);

        const volume = numberOrNull(item.volume);

        if (
            time === null ||
            open === null ||
            high === null ||
            low === null ||
            close === null
        ) {
            return null;
        }

        if (
            high < low ||
            high < open ||
            high < close ||
            low > open ||
            low > close
        ) {
            return null;
        }

        return {
            time,
            open,
            high,
            low,
            close,
            volume
        };
    }


    function normalizeBars(input) {
        const result = [];

        for (const item of input || []) {
            const bar = normalizeBar(item);

            if (bar) {
                result.push(bar);
            }
        }

        result.sort(
            (a, b) =>
                comparableTime(a.time) -
                comparableTime(b.time)
        );

        const deduped = [];
        const indexByTime = new Map();

        for (const bar of result) {
            const key = timeKey(bar.time);

            if (indexByTime.has(key)) {
                deduped[indexByTime.get(key)] = bar;
            } else {
                indexByTime.set(
                    key,
                    deduped.length
                );

                deduped.push(bar);
            }
        }

        return deduped;
    }


    // ============================================================
    // LIGHTWEIGHT CHARTS VERSION COMPATIBILITY
    // ============================================================

    function addCandles(chart, options) {
        if (
            typeof chart.addCandlestickSeries === "function"
        ) {
            return chart.addCandlestickSeries(options);
        }

        return chart.addSeries(
            lc().CandlestickSeries,
            options
        );
    }


    function addHistogram(chart, options) {
        if (
            typeof chart.addHistogramSeries === "function"
        ) {
            return chart.addHistogramSeries(options);
        }

        return chart.addSeries(
            lc().HistogramSeries,
            options
        );
    }


    function addLine(chart, options) {
        if (
            typeof chart.addLineSeries === "function"
        ) {
            return chart.addLineSeries(options);
        }

        return chart.addSeries(
            lc().LineSeries,
            options
        );
    }


    function seriesSetData(series, data) {
        if (
            series &&
            typeof series.setData === "function"
        ) {
            series.setData(data);
        }
    }


    function seriesUpdate(series, data) {
        if (
            series &&
            typeof series.update === "function"
        ) {
            series.update(data);
        }
    }


    // ============================================================
    // TECHNICAL INDICATORS
    // ============================================================

    function emaValues(values, period) {
        if (!values.length) {
            return [];
        }

        const multiplier = 2 / (period + 1);

        let previous = values[0];

        return values.map(
            (value, index) => {
                previous =
                    index === 0
                        ? value
                        : (
                            value * multiplier +
                            previous * (1 - multiplier)
                        );

                return previous;
            }
        );
    }


    function emaData(bars, period) {
        if (!bars.length) {
            return [];
        }

        const values = emaValues(
            bars.map(bar => bar.close),
            period
        );

        const output = [];

        for (
            let index = period - 1;
            index < bars.length;
            index++
        ) {
            output.push({
                time: bars[index].time,
                value: values[index]
            });
        }

        return output;
    }


    function calculateRsi(bars, period = 14) {
        if (bars.length <= period) {
            return [];
        }

        const output = [];

        let gains = 0;
        let losses = 0;

        for (
            let index = 1;
            index <= period;
            index++
        ) {
            const change =
                bars[index].close -
                bars[index - 1].close;

            if (change >= 0) {
                gains += change;
            } else {
                losses += Math.abs(change);
            }
        }

        let averageGain = gains / period;
        let averageLoss = losses / period;

        function rsiValue() {
            if (averageLoss === 0) {
                return 100;
            }

            const relativeStrength =
                averageGain / averageLoss;

            return (
                100 -
                100 / (1 + relativeStrength)
            );
        }

        output.push({
            time: bars[period].time,
            value: rsiValue()
        });

        for (
            let index = period + 1;
            index < bars.length;
            index++
        ) {
            const change =
                bars[index].close -
                bars[index - 1].close;

            const gain =
                change > 0
                    ? change
                    : 0;

            const loss =
                change < 0
                    ? Math.abs(change)
                    : 0;

            averageGain =
                (
                    averageGain *
                    (period - 1) +
                    gain
                ) / period;

            averageLoss =
                (
                    averageLoss *
                    (period - 1) +
                    loss
                ) / period;

            output.push({
                time: bars[index].time,
                value: rsiValue()
            });
        }

        return output;
    }


    function calculateMacd(
        bars,
        fastPeriod = 12,
        slowPeriod = 26,
        signalPeriod = 9
    ) {
        if (!bars.length) {
            return {
                macd: [],
                signal: [],
                histogram: []
            };
        }

        const closes = bars.map(
            bar => bar.close
        );

        const fast = emaValues(
            closes,
            fastPeriod
        );

        const slow = emaValues(
            closes,
            slowPeriod
        );

        const rawMacd = closes.map(
            (_, index) =>
                fast[index] - slow[index]
        );

        const signal = emaValues(
            rawMacd,
            signalPeriod
        );

        const macdData = [];
        const signalData = [];
        const histogramData = [];

        for (
            let index = slowPeriod - 1;
            index < bars.length;
            index++
        ) {
            const macdValue =
                rawMacd[index];

            const signalValue =
                signal[index];

            const histogramValue =
                macdValue - signalValue;

            macdData.push({
                time: bars[index].time,
                value: macdValue
            });

            signalData.push({
                time: bars[index].time,
                value: signalValue
            });

            histogramData.push({
                time: bars[index].time,
                value: histogramValue,
                color:
                    histogramValue >= 0
                        ? "rgba(20,217,144,.58)"
                        : "rgba(255,79,94,.58)"
            });
        }

        return {
            macd: macdData,
            signal: signalData,
            histogram: histogramData
        };
    }


    // ============================================================
    // MAIN CHART
    // ============================================================

    function makeChart(container) {
        const L = lc();

        if (!L) {
            throw new Error(
                "Lightweight Charts is not loaded."
            );
        }

        const chart = L.createChart(
            container,
            {
                width:
                    container.clientWidth,

                height:
                    container.clientHeight,

                layout: {
                    background: {
                        type: "solid",
                        color: "#030b13"
                    },

                    textColor:
                        "#8796a7",

                    fontFamily:
                        "Inter, system-ui, sans-serif",

                    fontSize: 10
                },

                grid: {
                    vertLines: {
                        color:
                            "rgba(115,145,175,.075)"
                    },

                    horzLines: {
                        color:
                            "rgba(115,145,175,.075)"
                    }
                },

                crosshair: {
                    mode:
                        L.CrosshairMode
                            ? L.CrosshairMode.Normal
                            : 0,

                    vertLine: {
                        color:
                            "rgba(183,199,216,.40)",

                        width: 1,
                        style: 2,

                        labelBackgroundColor:
                            "#18283a"
                    },

                    horzLine: {
                        color:
                            "rgba(183,199,216,.40)",

                        width: 1,
                        style: 2,

                        labelBackgroundColor:
                            "#18283a"
                    }
                },

                rightPriceScale: {
                    borderColor:
                        "rgba(130,160,190,.16)",

                    autoScale: true,

                    scaleMargins: {
                        top: 0.08,
                        bottom: 0.22
                    }
                },

                timeScale: {
                    borderColor:
                        "rgba(130,160,190,.16)",

                    timeVisible: true,
                    secondsVisible: false,

                    rightOffset: 5,

                    barSpacing: 7,
                    minBarSpacing: 0.5,

                    fixLeftEdge: false,
                    fixRightEdge: false,

                    lockVisibleTimeRangeOnResize:
                        true
                },

                handleScroll: {
                    mouseWheel: true,
                    pressedMouseMove: true,
                    horzTouchDrag: true,
                    vertTouchDrag: true
                },

                handleScale: {
                    axisPressedMouseMove: true,
                    mouseWheel: true,
                    pinch: true
                },

                kineticScroll: {
                    mouse: true,
                    touch: true
                }
            }
        );

        const candles = addCandles(
            chart,
            {
                upColor:
                    "#14d990",

                downColor:
                    "#ff4f5e",

                borderUpColor:
                    "#14d990",

                borderDownColor:
                    "#ff4f5e",

                wickUpColor:
                    "#14d990",

                wickDownColor:
                    "#ff4f5e",

                priceLineColor:
                    "#18d88c",

                priceLineWidth: 1,

                lastValueVisible: true,
                priceLineVisible: true
            }
        );

        const volume = addHistogram(
            chart,
            {
                priceFormat: {
                    type: "volume"
                },

                priceScaleId:
                    "volume",

                lastValueVisible:
                    false,

                priceLineVisible:
                    false
            }
        );

        chart
            .priceScale("volume")
            .applyOptions({
                scaleMargins: {
                    top: 0.82,
                    bottom: 0
                }
            });

        state.chart = chart;
        state.candleSeries = candles;
        state.volumeSeries = volume;

        state.ema9Series =
            addLine(
                chart,
                {
                    color: "#ff9f31",
                    lineWidth: 1,
                    priceLineVisible: false,
                    lastValueVisible: false,
                    title: "EMA 9"
                }
            );

        state.ema20Series =
            addLine(
                chart,
                {
                    color: "#e3a735",
                    lineWidth: 1,
                    priceLineVisible: false,
                    lastValueVisible: false,
                    title: "EMA 20"
                }
            );

        state.ema50Series =
            addLine(
                chart,
                {
                    color: "#2c9eff",
                    lineWidth: 1,
                    priceLineVisible: false,
                    lastValueVisible: false,
                    title: "EMA 50"
                }
            );

        state.ema200Series =
            addLine(
                chart,
                {
                    color: "#b53cff",
                    lineWidth: 1,
                    priceLineVisible: false,
                    lastValueVisible: false,
                    title: "EMA 200"
                }
            );

        installCrosshairHandler();
        installVisibleRangeHandler();

        state.resizeObserver =
            new ResizeObserver(
                entries => {
                    const rect =
                        entries[0]
                            ?.contentRect;

                    if (
                        !rect ||
                        !state.chart
                    ) {
                        return;
                    }

                    state.chart.applyOptions({
                        width:
                            Math.floor(
                                rect.width
                            ),

                        height:
                            Math.floor(
                                rect.height
                            )
                    });

                    renderDrawings();
                }
            );

        state.resizeObserver.observe(
            container
        );

        createDrawingOverlay(
            container
        );

        installDrawingEvents(
            container
        );

        return chart;
    }


    // ============================================================
    // RSI PANE
    // ============================================================

    function destroyRsiChart() {
        if (state.rsiChart) {
            try {
                state.rsiChart.remove();
            } catch {
            }
        }

        state.rsiChart = null;
        state.rsiSeries = null;
        state.rsi70Series = null;
        state.rsi30Series = null;
        state.rsiContainer = null;
    }


    function createRsiChart(container) {
        destroyRsiChart();

        if (!container || !lc()) {
            return;
        }

        const L = lc();

        const chart = L.createChart(
            container,
            {
                width:
                    container.clientWidth,

                height:
                    container.clientHeight,

                layout: {
                    background: {
                        type: "solid",
                        color: "#030b13"
                    },

                    textColor:
                        "#8796a7",

                    fontFamily:
                        "Inter, system-ui, sans-serif",

                    fontSize: 10
                },

                grid: {
                    vertLines: {
                        color:
                            "rgba(115,145,175,.055)"
                    },

                    horzLines: {
                        color:
                            "rgba(115,145,175,.055)"
                    }
                },

                rightPriceScale: {
                    borderColor:
                        "rgba(130,160,190,.16)",

                    scaleMargins: {
                        top: 0.12,
                        bottom: 0.12
                    }
                },

                timeScale: {
                    visible: false,
                    timeVisible: true
                },

                handleScroll: false,
                handleScale: false
            }
        );

        const rsi =
            addLine(
                chart,
                {
                    color: "#b06cff",
                    lineWidth: 1.4,
                    priceLineVisible: false,
                    lastValueVisible: true,
                    title: "RSI 14"
                }
            );

        const upper =
            addLine(
                chart,
                {
                    color:
                        "rgba(255,79,94,.45)",

                    lineWidth: 1,

                    lineStyle: 2,

                    priceLineVisible:
                        false,

                    lastValueVisible:
                        false
                }
            );

        const lower =
            addLine(
                chart,
                {
                    color:
                        "rgba(20,217,144,.45)",

                    lineWidth: 1,

                    lineStyle: 2,

                    priceLineVisible:
                        false,

                    lastValueVisible:
                        false
                }
            );

        state.rsiChart = chart;
        state.rsiSeries = rsi;
        state.rsi70Series = upper;
        state.rsi30Series = lower;
        state.rsiContainer = container;

        renderRsi();
    }


    function renderRsi() {
        if (
            !state.rsiChart ||
            !state.rsiSeries
        ) {
            return;
        }

        const data =
            calculateRsi(
                state.bars,
                14
            );

        seriesSetData(
            state.rsiSeries,
            data
        );

        seriesSetData(
            state.rsi70Series,
            data.map(item => ({
                time: item.time,
                value: 70
            }))
        );

        seriesSetData(
            state.rsi30Series,
            data.map(item => ({
                time: item.time,
                value: 30
            }))
        );

        state.rsiChart
            .timeScale()
            .fitContent();
    }


    // ============================================================
    // MACD PANE
    // ============================================================

    function destroyMacdChart() {
        if (state.macdChart) {
            try {
                state.macdChart.remove();
            } catch {
            }
        }

        state.macdChart = null;
        state.macdSeries = null;
        state.macdSignalSeries = null;
        state.macdHistogramSeries = null;
        state.macdContainer = null;
    }


    function createMacdChart(container) {
        destroyMacdChart();

        if (!container || !lc()) {
            return;
        }

        const L = lc();

        const chart = L.createChart(
            container,
            {
                width:
                    container.clientWidth,

                height:
                    container.clientHeight,

                layout: {
                    background: {
                        type: "solid",
                        color: "#030b13"
                    },

                    textColor:
                        "#8796a7",

                    fontFamily:
                        "Inter, system-ui, sans-serif",

                    fontSize: 10
                },

                grid: {
                    vertLines: {
                        color:
                            "rgba(115,145,175,.055)"
                    },

                    horzLines: {
                        color:
                            "rgba(115,145,175,.055)"
                    }
                },

                rightPriceScale: {
                    borderColor:
                        "rgba(130,160,190,.16)",

                    scaleMargins: {
                        top: 0.12,
                        bottom: 0.12
                    }
                },

                timeScale: {
                    timeVisible: true,
                    secondsVisible: false
                },

                handleScroll: false,
                handleScale: false
            }
        );

        state.macdSeries =
            addLine(
                chart,
                {
                    color: "#32c8ff",
                    lineWidth: 1.2,
                    priceLineVisible: false,
                    lastValueVisible: false,
                    title: "MACD"
                }
            );

        state.macdSignalSeries =
            addLine(
                chart,
                {
                    color: "#ff9f31",
                    lineWidth: 1.2,
                    priceLineVisible: false,
                    lastValueVisible: false,
                    title: "Signal"
                }
            );

        state.macdHistogramSeries =
            addHistogram(
                chart,
                {
                    priceLineVisible:
                        false,

                    lastValueVisible:
                        false
                }
            );

        state.macdChart = chart;
        state.macdContainer = container;

        renderMacd();
    }


    function renderMacd() {
        if (
            !state.macdChart ||
            !state.macdSeries
        ) {
            return;
        }

        const data =
            calculateMacd(
                state.bars
            );

        seriesSetData(
            state.macdSeries,
            data.macd
        );

        seriesSetData(
            state.macdSignalSeries,
            data.signal
        );

        seriesSetData(
            state.macdHistogramSeries,
            data.histogram
        );

        state.macdChart
            .timeScale()
            .fitContent();
    }


    // ============================================================
    // INDICATOR RENDERING
    // ============================================================

    function renderIndicators() {
        seriesSetData(
            state.ema9Series,
            emaData(
                state.bars,
                9
            )
        );

        seriesSetData(
            state.ema20Series,
            emaData(
                state.bars,
                20
            )
        );

        seriesSetData(
            state.ema50Series,
            emaData(
                state.bars,
                50
            )
        );

        seriesSetData(
            state.ema200Series,
            emaData(
                state.bars,
                200
            )
        );

        renderRsi();
        renderMacd();
    }


    function setIndicatorVisibility(show) {
        state.indicatorsVisible =
            !!show;

        [
            state.ema9Series,
            state.ema20Series,
            state.ema50Series,
            state.ema200Series
        ].forEach(
            series =>
                series
                    ?.applyOptions
                    ?.({
                        visible:
                            state.indicatorsVisible
                    })
        );
    }


    // ============================================================
    // MAIN DATA RENDERING
    // ============================================================

    function renderMainSeries() {
        if (!state.candleSeries) {
            return;
        }

        seriesSetData(
            state.candleSeries,
            state.bars.map(
                bar => ({
                    time: bar.time,
                    open: bar.open,
                    high: bar.high,
                    low: bar.low,
                    close: bar.close
                })
            )
        );

        seriesSetData(
            state.volumeSeries,
            state.bars
                .filter(
                    bar =>
                        Number.isFinite(
                            bar.volume
                        )
                )
                .map(
                    bar => ({
                        time:
                            bar.time,

                        value:
                            bar.volume,

                        color:
                            bar.close >=
                            bar.open
                                ? "rgba(20,217,144,.42)"
                                : "rgba(255,79,94,.42)"
                    })
                )
        );

        renderIndicators();
    }


    // ============================================================
    // LIVE CANDLE UPDATE
    // ============================================================

    function updateBar(raw) {
        const bar =
            normalizeBar(raw);

        if (!bar) {
            return false;
        }

        const last =
            state.bars[
                state.bars.length - 1
            ];

        if (!last) {
            state.bars.push(bar);
        } else {
            const incomingTime =
                comparableTime(
                    bar.time
                );

            const lastTime =
                comparableTime(
                    last.time
                );

            if (
                incomingTime <
                lastTime
            ) {
                return false;
            }

            if (
                timeKey(bar.time) ===
                timeKey(last.time)
            ) {
                state.bars[
                    state.bars.length - 1
                ] = bar;
            } else {
                state.bars.push(bar);
            }
        }

        seriesUpdate(
            state.candleSeries,
            {
                time: bar.time,
                open: bar.open,
                high: bar.high,
                low: bar.low,
                close: bar.close
            }
        );

        if (
            Number.isFinite(
                bar.volume
            )
        ) {
            seriesUpdate(
                state.volumeSeries,
                {
                    time:
                        bar.time,

                    value:
                        bar.volume,

                    color:
                        bar.close >=
                        bar.open
                            ? "rgba(20,217,144,.42)"
                            : "rgba(255,79,94,.42)"
                }
            );
        }

        renderIndicators();

        renderDrawings();

        return true;
    }


    // ============================================================
    // CROSSHAIR / OHLC READOUT
    // ============================================================

    function installCrosshairHandler() {
        if (
            !state.chart ||
            !state.candleSeries
        ) {
            return;
        }

        state.crosshairHandler =
            parameter => {
                if (!parameter) {
                    return;
                }

                let candle = null;

                if (
                    parameter.seriesData &&
                    typeof parameter.seriesData.get ===
                    "function"
                ) {
                    candle =
                        parameter.seriesData.get(
                            state.candleSeries
                        );
                }

                if (!candle) {
                    const key =
                        timeKey(
                            parameter.time
                        );

                    candle =
                        state.bars.find(
                            bar =>
                                timeKey(
                                    bar.time
                                ) === key
                        );
                }

                if (!candle) {
                    return;
                }

                const previousIndex =
                    state.bars.findIndex(
                        bar =>
                            timeKey(
                                bar.time
                            ) ===
                            timeKey(
                                candle.time ??
                                parameter.time
                            )
                    ) - 1;

                const previous =
                    previousIndex >= 0
                        ? state.bars[
                            previousIndex
                        ]
                        : null;

                const change =
                    previous
                        ? candle.close -
                          previous.close
                        : 0;

                const changePercent =
                    previous &&
                    previous.close
                        ? (
                            change /
                            previous.close
                        ) * 100
                        : 0;

                const detail = {
                    time:
                        candle.time ??
                        parameter.time,

                    open:
                        candle.open,

                    high:
                        candle.high,

                    low:
                        candle.low,

                    close:
                        candle.close,

                    volume:
                        candle.volume,

                    change,
                    changePercent,

                    formatted: {
                        open:
                            formatPrice(
                                candle.open
                            ),

                        high:
                            formatPrice(
                                candle.high
                            ),

                        low:
                            formatPrice(
                                candle.low
                            ),

                        close:
                            formatPrice(
                                candle.close
                            ),

                        volume:
                            formatVolume(
                                candle.volume
                            ),

                        change:
                            formatPrice(
                                change
                            ),

                        changePercent:
                            `${changePercent.toFixed(2)}%`
                    }
                };

                if (
                    typeof state.liveOptions
                        ?.onCrosshair ===
                    "function"
                ) {
                    state.liveOptions
                        .onCrosshair(
                            detail
                        );
                }

                window.dispatchEvent(
                    new CustomEvent(
                        "phoenixchart:crosshair",
                        {
                            detail
                        }
                    )
                );
            };

        state.chart
            .subscribeCrosshairMove(
                state.crosshairHandler
            );
    }


    // ============================================================
    // TIME RANGE SYNCHRONIZATION
    // ============================================================

    function installVisibleRangeHandler() {
        if (!state.chart) {
            return;
        }

        state.visibleRangeHandler =
            range => {
                if (!range) {
                    return;
                }

                try {
                    state.rsiChart
                        ?.timeScale()
                        ?.setVisibleLogicalRange(
                            range
                        );

                    state.macdChart
                        ?.timeScale()
                        ?.setVisibleLogicalRange(
                            range
                        );
                } catch {
                }

                renderDrawings();
            };

        state.chart
            .timeScale()
            .subscribeVisibleLogicalRangeChange(
                state.visibleRangeHandler
            );
    }


    // ============================================================
    // SUPPORT / RESISTANCE
    // ============================================================

    function removePriceLines(lines) {
        if (!state.candleSeries) {
            return;
        }

        for (const line of lines) {
            try {
                state.candleSeries
                    .removePriceLine(
                        line
                    );
            } catch {
            }
        }

        lines.length = 0;
    }


    function normalizeLevelValues(values) {
        if (!Array.isArray(values)) {
            return [];
        }

        return values
            .map(item => {
                if (
                    typeof item ===
                    "number"
                ) {
                    return item;
                }

                if (
                    item &&
                    typeof item ===
                    "object"
                ) {
                    return numberOrNull(
                        item.price ??
                        item.value ??
                        item.level
                    );
                }

                return numberOrNull(
                    item
                );
            })
            .filter(
                Number.isFinite
            );
    }


    function setLevels(levels) {
        removePriceLines(
            state.supportLines
        );

        removePriceLines(
            state.resistanceLines
        );

        if (
            !levels ||
            !state.candleSeries
        ) {
            return;
        }

        const supports =
            normalizeLevelValues(
                levels.support ??
                levels.supports ??
                []
            );

        const resistances =
            normalizeLevelValues(
                levels.resistance ??
                levels.resistances ??
                []
            );

        supports.forEach(
            (price, index) => {
                const line =
                    state.candleSeries
                        .createPriceLine({
                            price,

                            color:
                                "rgba(20,217,144,.80)",

                            lineWidth: 1,

                            lineStyle: 2,

                            axisLabelVisible:
                                true,

                            title:
                                index === 0
                                    ? "SUPPORT"
                                    : `S${index + 1}`
                        });

                state.supportLines.push(
                    line
                );
            }
        );

        resistances.forEach(
            (price, index) => {
                const line =
                    state.candleSeries
                        .createPriceLine({
                            price,

                            color:
                                "rgba(255,79,94,.80)",

                            lineWidth: 1,

                            lineStyle: 2,

                            axisLabelVisible:
                                true,

                            title:
                                index === 0
                                    ? "RESISTANCE"
                                    : `R${index + 1}`
                        });

                state.resistanceLines.push(
                    line
                );
            }
        );
    }


    // ============================================================
    // ENTRY / EXIT / STOP / TARGET
    // ============================================================

    function clearTradeLevels() {
        removePriceLines(
            state.tradeLines
        );
    }


    function addTradeLevel(
        price,
        title,
        color
    ) {
        const value =
            numberOrNull(price);

        if (
            value === null ||
            !state.candleSeries
        ) {
            return;
        }

        const line =
            state.candleSeries
                .createPriceLine({
                    price: value,
                    color,
                    lineWidth: 1,
                    lineStyle: 1,
                    axisLabelVisible: true,
                    title
                });

        state.tradeLines.push(
            line
        );
    }


    function setTradeLevels(levels) {
        clearTradeLevels();

        if (!levels) {
            return;
        }

        addTradeLevel(
            levels.entry ??
            levels.entry_price,

            "ENTRY",

            "#32c8ff"
        );

        addTradeLevel(
            levels.stop ??
            levels.stop_loss ??
            levels.stop_price,

            "STOP",

            "#ff4f5e"
        );

        addTradeLevel(
            levels.target ??
            levels.take_profit ??
            levels.target_price,

            "TARGET",

            "#14d990"
        );

        addTradeLevel(
            levels.exit ??
            levels.exit_price,

            "EXIT",

            "#ffae45"
        );
    }


    // ============================================================
    // EVENT MARKERS
    // ============================================================

    function normalizeEvents(events) {
        if (!Array.isArray(events)) {
            return [];
        }

        return events
            .map(event => {
                const time =
                    parseTime(
                        event.time ??
                        event.timestamp ??
                        event.date
                    );

                if (time === null) {
                    return null;
                }

                const type =
                    String(
                        event.type ??
                        event.event_type ??
                        "event"
                    ).toLowerCase();

                let text = "*";
                let position =
                    "aboveBar";

                if (
                    type.includes(
                        "dividend"
                    )
                ) {
                    text = "D";
                } else if (
                    type.includes(
                        "split"
                    )
                ) {
                    text = "S";
                } else if (
                    type.includes(
                        "news"
                    )
                ) {
                    text = "*";
                }

                return {
                    time,
                    position,
                    shape: "circle",
                    color: "#ffae45",
                    text:
                        event.title ??
                        event.label ??
                        text
                };
            })
            .filter(Boolean)
            .sort(
                (a, b) =>
                    comparableTime(
                        a.time
                    ) -
                    comparableTime(
                        b.time
                    )
            );
    }


    function applyMarkers(markers) {
        state.eventMarkers =
            markers;

        if (!state.candleSeries) {
            return;
        }

        try {
            if (
                typeof state.candleSeries
                    .setMarkers ===
                "function"
            ) {
                state.candleSeries
                    .setMarkers(
                        markers
                    );

                return;
            }

            if (
                lc()
                    ?.createSeriesMarkers
            ) {
                lc().createSeriesMarkers(
                    state.candleSeries,
                    markers
                );
            }
        } catch {
        }
    }


    // ============================================================
    // DRAWING COORDINATE CONVERSION
    // ============================================================

    function pointToChartPoint(
        x,
        y
    ) {
        if (
            !state.chart ||
            !state.candleSeries
        ) {
            return null;
        }

        const time =
            state.chart
                .timeScale()
                .coordinateToTime(
                    x
                );

        const price =
            state.candleSeries
                .coordinateToPrice(
                    y
                );

        if (
            time === null ||
            time === undefined ||
            price === null ||
            price === undefined ||
            !Number.isFinite(
                Number(price)
            )
        ) {
            return null;
        }

        return {
            time,
            price:
                Number(price)
        };
    }


    function chartPointToPixels(
        point
    ) {
        if (
            !point ||
            !state.chart ||
            !state.candleSeries
        ) {
            return null;
        }

        const x =
            state.chart
                .timeScale()
                .timeToCoordinate(
                    point.time
                );

        const y =
            state.candleSeries
                .priceToCoordinate(
                    point.price
                );

        if (
            x === null ||
            y === null
        ) {
            return null;
        }

        return {
            x,
            y
        };
    }


    // ============================================================
    // DRAWING OVERLAY
    // ============================================================

    function createDrawingOverlay(
        container
    ) {
        const old =
            container.querySelector(
                ".phoenix-drawing-overlay"
            );

        if (old) {
            old.remove();
        }

        const svg =
            document.createElementNS(
                "http://www.w3.org/2000/svg",
                "svg"
            );

        svg.classList.add(
            "phoenix-drawing-overlay"
        );

        Object.assign(
            svg.style,
            {
                position: "absolute",
                inset: "0",
                width: "100%",
                height: "100%",
                zIndex: "4",
                pointerEvents: "none",
                overflow: "visible"
            }
        );

        container.appendChild(
            svg
        );

        state.drawingOverlay = svg;
    }


    function svgLine(
        svg,
        x1,
        y1,
        x2,
        y2,
        options = {}
    ) {
        const line =
            document.createElementNS(
                svg.namespaceURI,
                "line"
            );

        line.setAttribute(
            "x1",
            x1
        );

        line.setAttribute(
            "y1",
            y1
        );

        line.setAttribute(
            "x2",
            x2
        );

        line.setAttribute(
            "y2",
            y2
        );

        line.setAttribute(
            "stroke",
            options.color ??
            "#ffae45"
        );

        line.setAttribute(
            "stroke-width",
            options.width ??
            "1.4"
        );

        if (options.dash) {
            line.setAttribute(
                "stroke-dasharray",
                options.dash
            );
        }

        svg.appendChild(
            line
        );

        return line;
    }


    function renderDrawings() {
        const svg =
            state.drawingOverlay;

        if (!svg) {
            return;
        }

        svg.replaceChildren();

        const width =
            svg.clientWidth;

        const height =
            svg.clientHeight;

        for (
            const drawing
            of state.drawings
        ) {
            const first =
                chartPointToPixels(
                    drawing.p1
                );

            const second =
                chartPointToPixels(
                    drawing.p2 ??
                    drawing.p1
                );

            if (!first) {
                continue;
            }

            if (
                drawing.type ===
                "horizontal"
            ) {
                svgLine(
                    svg,
                    0,
                    first.y,
                    width,
                    first.y
                );

                continue;
            }

            if (
                drawing.type ===
                "vertical"
            ) {
                svgLine(
                    svg,
                    first.x,
                    0,
                    first.x,
                    height
                );

                continue;
            }

            if (
                drawing.type ===
                "text"
            ) {
                const text =
                    document.createElementNS(
                        svg.namespaceURI,
                        "text"
                    );

                text.setAttribute(
                    "x",
                    first.x
                );

                text.setAttribute(
                    "y",
                    first.y
                );

                text.setAttribute(
                    "fill",
                    "#ffae45"
                );

                text.setAttribute(
                    "font-size",
                    "12"
                );

                text.textContent =
                    drawing.text ??
                    "Note";

                svg.appendChild(
                    text
                );

                continue;
            }

            if (!second) {
                continue;
            }

            if (
                drawing.type ===
                    "trend" ||
                drawing.type ===
                    "arrow" ||
                drawing.type ===
                    "measure"
            ) {
                svgLine(
                    svg,
                    first.x,
                    first.y,
                    second.x,
                    second.y,
                    {
                        color:
                            drawing.type ===
                            "measure"
                                ? "#55c7ff"
                                : "#ffae45",

                        dash:
                            drawing.type ===
                            "measure"
                                ? "5 4"
                                : null
                    }
                );

                if (
                    drawing.type ===
                    "measure"
                ) {
                    const priceChange =
                        drawing.p2.price -
                        drawing.p1.price;

                    const percent =
                        drawing.p1.price
                            ? (
                                priceChange /
                                drawing.p1.price
                            ) * 100
                            : 0;

                    const text =
                        document.createElementNS(
                            svg.namespaceURI,
                            "text"
                        );

                    text.setAttribute(
                        "x",
                        second.x + 6
                    );

                    text.setAttribute(
                        "y",
                        second.y - 6
                    );

                    text.setAttribute(
                        "fill",
                        "#55c7ff"
                    );

                    text.setAttribute(
                        "font-size",
                        "11"
                    );

                    text.textContent =
                        `${priceChange >= 0 ? "+" : ""}${formatPrice(priceChange)} (${percent.toFixed(2)}%)`;

                    svg.appendChild(
                        text
                    );
                }

                continue;
            }

            if (
                drawing.type ===
                "rectangle"
            ) {
                const rectangle =
                    document.createElementNS(
                        svg.namespaceURI,
                        "rect"
                    );

                rectangle.setAttribute(
                    "x",
                    Math.min(
                        first.x,
                        second.x
                    )
                );

                rectangle.setAttribute(
                    "y",
                    Math.min(
                        first.y,
                        second.y
                    )
                );

                rectangle.setAttribute(
                    "width",
                    Math.abs(
                        second.x -
                        first.x
                    )
                );

                rectangle.setAttribute(
                    "height",
                    Math.abs(
                        second.y -
                        first.y
                    )
                );

                rectangle.setAttribute(
                    "fill",
                    "rgba(255,159,49,.08)"
                );

                rectangle.setAttribute(
                    "stroke",
                    "#ffae45"
                );

                svg.appendChild(
                    rectangle
                );

                continue;
            }

            if (
                drawing.type ===
                "fib"
            ) {
                [
                    0,
                    0.236,
                    0.382,
                    0.5,
                    0.618,
                    0.786,
                    1
                ].forEach(
                    level => {
                        const y =
                            first.y +
                            (
                                second.y -
                                first.y
                            ) * level;

                        svgLine(
                            svg,
                            Math.min(
                                first.x,
                                second.x
                            ),
                            y,
                            Math.max(
                                first.x,
                                second.x
                            ),
                            y,
                            {
                                color:
                                    level ===
                                    0.5
                                        ? "#ffae45"
                                        : "rgba(85,199,255,.70)",

                                width:
                                    "1"
                            }
                        );

                        const text =
                            document.createElementNS(
                                svg.namespaceURI,
                                "text"
                            );

                        text.setAttribute(
                            "x",
                            Math.max(
                                first.x,
                                second.x
                            ) + 4
                        );

                        text.setAttribute(
                            "y",
                            y - 2
                        );

                        text.setAttribute(
                            "fill",
                            "#8796a7"
                        );

                        text.setAttribute(
                            "font-size",
                            "9"
                        );

                        text.textContent =
                            `${(level * 100).toFixed(1)}%`;

                        svg.appendChild(
                            text
                        );
                    }
                );
            }
        }
    }


    // ============================================================
    // DRAWING EVENTS
    // ============================================================

    function installDrawingEvents(
        container
    ) {
        container.addEventListener(
            "pointerdown",
            event => {
                if (
                    !state.drawingOverlay ||
                    state.drawingTool ===
                        "crosshair"
                ) {
                    return;
                }

                const rect =
                    container
                        .getBoundingClientRect();

                const point =
                    pointToChartPoint(
                        event.clientX -
                        rect.left,

                        event.clientY -
                        rect.top
                    );

                if (!point) {
                    return;
                }

                if (
                    [
                        "horizontal",
                        "vertical",
                        "text"
                    ].includes(
                        state.drawingTool
                    )
                ) {
                    const drawing = {
                        type:
                            state.drawingTool,

                        p1:
                            point,

                        p2:
                            point
                    };

                    if (
                        state.drawingTool ===
                        "text"
                    ) {
                        drawing.text =
                            "Note";
                    }

                    state.drawings.push(
                        drawing
                    );

                    persistDrawings();
                    renderDrawings();

                    return;
                }

                state.drawingStart =
                    point;

                state.activeDrawing = {
                    type:
                        state.drawingTool,

                    p1:
                        point,

                    p2:
                        point
                };

                state.drawings.push(
                    state.activeDrawing
                );

                renderDrawings();
            },
            true
        );


        container.addEventListener(
            "pointermove",
            event => {
                if (
                    !state.activeDrawing ||
                    !state.drawingStart
                ) {
                    return;
                }

                const rect =
                    container
                        .getBoundingClientRect();

                const point =
                    pointToChartPoint(
                        event.clientX -
                        rect.left,

                        event.clientY -
                        rect.top
                    );

                if (!point) {
                    return;
                }

                state.activeDrawing.p2 =
                    point;

                renderDrawings();
            },
            true
        );


        const finish = () => {
            if (
                state.activeDrawing
            ) {
                persistDrawings();
            }

            state.activeDrawing =
                null;

            state.drawingStart =
                null;
        };


        container.addEventListener(
            "pointerup",
            finish,
            true
        );

        container.addEventListener(
            "pointercancel",
            finish,
            true
        );
    }


    // ============================================================
    // DRAWING STORAGE
    // ============================================================

    function storageKey() {
        return (
            "phoenixtrend:charts:drawings:" +
            (
                state.symbol ||
                "workspace"
            )
        );
    }


    function persistDrawings() {
        try {
            localStorage.setItem(
                storageKey(),
                JSON.stringify(
                    state.drawings
                )
            );
        } catch {
        }
    }


    function loadDrawings() {
        try {
            const raw =
                localStorage.getItem(
                    storageKey()
                );

            state.drawings =
                raw
                    ? JSON.parse(raw)
                    : [];
        } catch {
            state.drawings = [];
        }

        renderDrawings();
    }


    // ============================================================
    // HTTP LIVE-CANDLE FALLBACK
    // ============================================================

    async function fetchLatestCandle(
        url
    ) {
        if (!url) {
            return;
        }

        try {
            const response =
                await fetch(
                    url,
                    {
                        cache: "no-store"
                    }
                );

            if (!response.ok) {
                return;
            }

            const payload =
                await response.json();

            const candle =
                payload?.candle ??
                payload?.bar ??
                payload;

            if (
                candle &&
                updateBar(candle)
            ) {
                emitMarketUpdate(
                    {
                        source:
                            "http-poll",

                        provider:
                            payload?.provider ??
                            "yahoo-finance",

                        providerMode:
                            payload?.provider_mode ??
                            "polled",

                        realTimeStream:
                            payload?.real_time_stream ??
                            false,

                        candle
                    }
                );
            }
        } catch {
        }
    }


    function startPolling(
        options
    ) {
        stopPolling();

        const url =
            options?.pollUrl;

        if (!url) {
            return;
        }

        const interval =
            Math.max(
                1500,
                Number(
                    options?.pollInterval ??
                    2000
                )
            );

        fetchLatestCandle(
            url
        );

        state.pollingTimer =
            window.setInterval(
                () =>
                    fetchLatestCandle(
                        url
                    ),
                interval
            );
    }


    function stopPolling() {
        if (
            state.pollingTimer
        ) {
            clearInterval(
                state.pollingTimer
            );

            state.pollingTimer =
                null;
        }
    }


    // ============================================================
    // WEBSOCKET LIVE CANDLE
    // ============================================================

    function websocketUrl(
        path
    ) {
        if (!path) {
            return null;
        }

        if (
            path.startsWith(
                "ws://"
            ) ||
            path.startsWith(
                "wss://"
            )
        ) {
            return path;
        }

        const protocol =
            window.location.protocol ===
            "https:"
                ? "wss:"
                : "ws:";

        const normalized =
            path.startsWith("/")
                ? path
                : `/${path}`;

        return (
            `${protocol}//` +
            `${window.location.host}` +
            normalized
        );
    }


    function closeWebSocket() {
        if (
            state.websocketReconnectTimer
        ) {
            clearTimeout(
                state.websocketReconnectTimer
            );

            state.websocketReconnectTimer =
                null;
        }

        if (state.websocket) {
            try {
                state.websocket.onopen =
                    null;

                state.websocket.onmessage =
                    null;

                state.websocket.onerror =
                    null;

                state.websocket.onclose =
                    null;

                state.websocket.close();
            } catch {
            }
        }

        state.websocket = null;
    }


    function startWebSocket(
        options
    ) {
        closeWebSocket();

        const url =
            websocketUrl(
                options?.wsUrl
            );

        if (!url) {
            startPolling(
                options
            );

            return;
        }

        try {
            const socket =
                new WebSocket(
                    url
                );

            state.websocket =
                socket;

            socket.onopen = () => {
                stopPolling();

                emitConnectionState(
                    "connected",
                    "websocket"
                );
            };


            socket.onmessage =
                event => {
                    try {
                        const payload =
                            JSON.parse(
                                event.data
                            );

                        if (
                            payload?.type ===
                            "market_data_error"
                        ) {
                            emitConnectionState(
                                "provider-error",
                                "websocket"
                            );

                            return;
                        }

                        const candle =
                            payload?.candle ??
                            payload?.bar ??
                            payload;

                        if (
                            candle &&
                            updateBar(
                                candle
                            )
                        ) {
                            emitMarketUpdate(
                                {
                                    source:
                                        "websocket",

                                    provider:
                                        payload?.provider ??
                                        "yahoo-finance",

                                    providerMode:
                                        payload?.provider_mode ??
                                        "polled",

                                    realTimeStream:
                                        payload?.real_time_stream ??
                                        false,

                                    candle
                                }
                            );
                        }
                    } catch {
                    }
                };


            socket.onerror = () => {
                emitConnectionState(
                    "fallback",
                    "http-poll"
                );
            };


            socket.onclose = () => {
                state.websocket =
                    null;

                if (
                    state.destroyed
                ) {
                    return;
                }

                startPolling(
                    options
                );

                state.websocketReconnectTimer =
                    window.setTimeout(
                        () => {
                            if (
                                !state.destroyed
                            ) {
                                startWebSocket(
                                    options
                                );
                            }
                        },
                        10000
                    );
            };
        } catch {
            startPolling(
                options
            );
        }
    }


    function emitMarketUpdate(
        detail
    ) {
        if (
            typeof state.liveOptions
                ?.onLiveUpdate ===
            "function"
        ) {
            state.liveOptions
                .onLiveUpdate(
                    detail
                );
        }

        window.dispatchEvent(
            new CustomEvent(
                "phoenixchart:live",
                {
                    detail
                }
            )
        );
    }


    function emitConnectionState(
        status,
        transport
    ) {
        const detail = {
            status,
            transport
        };

        if (
            typeof state.liveOptions
                ?.onConnectionState ===
            "function"
        ) {
            state.liveOptions
                .onConnectionState(
                    detail
                );
        }

        window.dispatchEvent(
            new CustomEvent(
                "phoenixchart:connection",
                {
                    detail
                }
            )
        );
    }


    // ============================================================
    // PUBLIC API
    // ============================================================

    window.PhoenixChart = {
        render(
            containerId,
            rawBars,
            options = {}
        ) {
            const container =
                document.getElementById(
                    containerId
                );

            if (!container) {
                return;
            }

            state.destroyed =
                false;

            const symbol =
                String(
                    options.symbol ??
                    ""
                )
                    .trim()
                    .toUpperCase();

            const symbolChanged =
                state.symbol &&
                symbol &&
                state.symbol !== symbol;

            if (
                state.container !==
                    container ||
                !state.chart
            ) {
                this.destroy();

                state.destroyed =
                    false;

                state.container =
                    container;

                makeChart(
                    container
                );
            }

            state.symbol =
                symbol;

            state.timeframe =
                String(
                    options.timeframe ??
                    ""
                );

            state.range =
                String(
                    options.range ??
                    ""
                );

            state.liveOptions =
                options;

            container.dataset.symbol =
                state.symbol;

            container.dataset.timeframe =
                state.timeframe;

            container.dataset.range =
                state.range;

            const bars =
                normalizeBars(
                    rawBars
                );

            state.bars =
                bars;

            renderMainSeries();

            setIndicatorVisibility(
                options.indicators !==
                false
            );

            if (
                options.fitContent !==
                false
            ) {
                state.chart
                    .timeScale()
                    .fitContent();
            }

            if (
                symbolChanged
            ) {
                state.drawings = [];
            }

            loadDrawings();

            if (
                options.levels
            ) {
                setLevels(
                    options.levels
                );
            }

            if (
                options.tradeLevels
            ) {
                setTradeLevels(
                    options.tradeLevels
                );
            }

            if (
                options.events
            ) {
                applyMarkers(
                    normalizeEvents(
                        options.events
                    )
                );
            }

            if (
                options.rsiContainerId
            ) {
                const rsiContainer =
                    document.getElementById(
                        options.rsiContainerId
                    );

                if (rsiContainer) {
                    createRsiChart(
                        rsiContainer
                    );
                }
            }

            if (
                options.macdContainerId
            ) {
                const macdContainer =
                    document.getElementById(
                        options.macdContainerId
                    );

                if (
                    macdContainer
                ) {
                    createMacdChart(
                        macdContainer
                    );
                }
            }

            if (
                options.wsUrl ||
                options.pollUrl
            ) {
                startWebSocket(
                    options
                );
            }

            return {
                bars:
                    state.bars.length,

                symbol:
                    state.symbol,

                timeframe:
                    state.timeframe,

                range:
                    state.range
            };
        },


        updateLiveBar(raw) {
            return updateBar(
                raw
            );
        },


        setLevels(levels) {
            setLevels(
                levels
            );
        },


        setTradeLevels(levels) {
            setTradeLevels(
                levels
            );
        },


        clearTradeLevels() {
            clearTradeLevels();
        },


        setEvents(events) {
            applyMarkers(
                normalizeEvents(
                    events
                )
            );
        },


        setIndicators(show) {
            setIndicatorVisibility(
                show
            );
        },


        setDrawingTool(tool) {
            state.drawingTool =
                tool ||
                "crosshair";
        },


        clearDrawings() {
            state.drawings = [];

            persistDrawings();
            renderDrawings();
        },


        undoDrawing() {
            if (
                !state.drawings.length
            ) {
                return;
            }

            state.drawings.pop();

            persistDrawings();
            renderDrawings();
        },


        fit() {
            state.chart
                ?.timeScale
                ?.()
                .fitContent
                ?.();

            state.rsiChart
                ?.timeScale
                ?.()
                .fitContent
                ?.();

            state.macdChart
                ?.timeScale
                ?.()
                .fitContent
                ?.();

            renderDrawings();
        },


        resetPriceScale() {
            try {
                state.chart
                    ?.priceScale(
                        "right"
                    )
                    ?.applyOptions({
                        autoScale: true
                    });
            } catch {
            }
        },


        scrollToRealtime() {
            try {
                state.chart
                    ?.timeScale()
                    ?.scrollToRealTime();
            } catch {
            }
        },


        setVisibleRange(
            from,
            to
        ) {
            if (!state.chart) {
                return;
            }

            try {
                state.chart
                    .timeScale()
                    .setVisibleRange({
                        from:
                            parseTime(
                                from
                            ),

                        to:
                            parseTime(
                                to
                            )
                    });
            } catch {
            }

            renderDrawings();
        },


        attachRsi(
            containerId
        ) {
            const container =
                document.getElementById(
                    containerId
                );

            if (container) {
                createRsiChart(
                    container
                );
            }
        },


        attachMacd(
            containerId
        ) {
            const container =
                document.getElementById(
                    containerId
                );

            if (container) {
                createMacdChart(
                    container
                );
            }
        },


        startLive(options = {}) {
            state.liveOptions = {
                ...state.liveOptions,
                ...options
            };

            startWebSocket(
                state.liveOptions
            );
        },


        stopLive() {
            closeWebSocket();
            stopPolling();
        },


        screenshot(filename) {
            if (
                !state.chart
                    ?.takeScreenshot
            ) {
                return;
            }

            const canvas =
                state.chart
                    .takeScreenshot();

            const link =
                document.createElement(
                    "a"
                );

            link.download =
                `${filename || "phoenixtrend-chart"}.png`;

            link.href =
                canvas.toDataURL(
                    "image/png"
                );

            link.click();
        },


        async toggleFullscreen(
            containerId
        ) {
            const container =
                document.getElementById(
                    containerId
                );

            if (!container) {
                return;
            }

            const target =
                container.parentElement ??
                container;

            if (
                !document.fullscreenElement
            ) {
                await target
                    .requestFullscreen
                    ?.();
            } else {
                await document
                    .exitFullscreen
                    ?.();
            }
        },


        getState() {
            return {
                symbol:
                    state.symbol,

                timeframe:
                    state.timeframe,

                range:
                    state.range,

                barCount:
                    state.bars.length,

                drawingTool:
                    state.drawingTool,

                drawingCount:
                    state.drawings.length,

                indicatorsVisible:
                    state.indicatorsVisible
            };
        },


        destroy() {
            state.destroyed =
                true;

            closeWebSocket();
            stopPolling();

            state.resizeObserver
                ?.disconnect
                ?.();

            state.resizeObserver =
                null;

            if (
                state.chart &&
                state.crosshairHandler
            ) {
                try {
                    state.chart
                        .unsubscribeCrosshairMove(
                            state.crosshairHandler
                        );
                } catch {
                }
            }

            if (
                state.chart &&
                state.visibleRangeHandler
            ) {
                try {
                    state.chart
                        .timeScale()
                        .unsubscribeVisibleLogicalRangeChange(
                            state.visibleRangeHandler
                        );
                } catch {
                }
            }

            destroyRsiChart();
            destroyMacdChart();

            if (state.chart) {
                try {
                    state.chart.remove();
                } catch {
                }
            }

            state.chart =
                null;

            state.candleSeries =
                null;

            state.volumeSeries =
                null;

            state.ema9Series =
                null;

            state.ema20Series =
                null;

            state.ema50Series =
                null;

            state.ema200Series =
                null;

            state.container =
                null;

            state.drawingOverlay =
                null;

            state.crosshairHandler =
                null;

            state.visibleRangeHandler =
                null;

            state.supportLines =
                [];

            state.resistanceLines =
                [];

            state.tradeLines =
                [];

            state.eventMarkers =
                [];

            state.bars =
                [];

            state.liveOptions =
                null;
        }
    };


    // ============================================================
    // PAGE BOOTSTRAP
    // ============================================================

    window.PhoenixPage_charts = () => {
        if (
            window.PhoenixPremium
                ?.init
        ) {
            window.PhoenixPremium.init(
                "charts"
            );
        }
    };
})();