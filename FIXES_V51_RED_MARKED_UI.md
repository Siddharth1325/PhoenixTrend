# PhoenixTrend v51 — red-marked UI corrections

- Arena red biplane asset now has a real alpha channel; the checkerboard/white image rectangle is removed. Arena CSS no longer adds a card/background around the aircraft.
- Portfolio and Risk PageHero now explicitly receive `/assets/phoenix-mountain-horizontal.png`; premium hero CSS guarantees the banner is visible.
- Portfolio and Risk section tabs are page-scoped premium segmented navigation with duotone Phosphor icons and responsive horizontal overflow.
- Fixed a v50 CSS leak where unscoped `.tabbar` rules in Portfolio/Risk/Settings could override tabs on other pages.
- Settings tabs are now page-scoped and compact/premium.
- Trady AI mode tabs are premium segmented controls and the workspace is a true 3-column desktop layout: chat history / conversation / AI summary. This removes the large empty canvas caused by the previous 2-column override.
- Activity right-side summary was compacted: smaller activity visualization, premium legend tiles, 2x2 P&L metrics and compact alerts instead of oversized empty panels.
- Existing application-level authentication guard remains enabled; only Login and Register are public.
- Existing Phosphor regular + duotone icon libraries remain the common icon source.
