# PhoenixTrend package fixes — 2026-09-28

Implemented in this package:

- Sidebar PhoenixTrend logo enlarged and blended into the sidebar.
- Header account control now uses the authenticated `/api/auth/me` user, has a working menu, broker/settings navigation, and logout.
- Home welcome name uses the authenticated user.
- Settings Account profile uses the authenticated user and real initials/email.
- Broker account response is enriched with real daily P&L, weekly P&L, gross exposure and daily P&L percentage where Alpaca supplies the required source data.
- Risk `AccountState` now carries real account fields and weekly P&L from broker portfolio history; no zero-value bypass was added.
- Analytics now combines persisted trade analytics with available Alpaca portfolio equity history for portfolio/risk charts, total return and drawdown.
- TradeDesk checks the execution result and only shows success when a real broker order object was returned; risk/broker errors are surfaced to the user.
- Portfolio and Risk use the existing mountain banner asset.
- Portfolio and Risk no longer render fake allocation/risk donuts when there are no positions/exposure.
- Trady AI workspace layout uses the available conversation canvas and removes the forced 650px blank workspace.
- Settings header/tabs compacted.
- Arena uses the supplied runway sunset image and supplied red biplane image while preserving existing multiplier/bet/cash-out mechanics.
- Arena uses the supplied announcement audio for the first ~4 seconds, then the supplied looping flight audio while flying; audio is reset/stopped between rounds and on unmount.
- Arena player name is loaded from the authenticated user instead of a hardcoded name.
- `/api/execution/status` is no longer in the unauthenticated public API allowlist.

Validation performed:

- Python syntax compilation passed for modified backend modules.
- Arena JavaScript syntax check passed with Node.
- Backend pytest result: 13 passed, 3 failed. The three failures are existing endpoint tests that call authenticated strategy endpoints without an auth token and therefore receive 401; they are unrelated to the package fixes above.
