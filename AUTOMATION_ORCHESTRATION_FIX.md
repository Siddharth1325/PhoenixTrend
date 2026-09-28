# PhoenixTrend Automation Orchestration Fix

Implemented master-to-asset runtime orchestration.

- Master Start starts every enabled implemented asset automation runtime.
- Enabling an asset while Master is running starts that asset runtime immediately.
- Enabling an asset while Master is stopped arms it for the next Master Start.
- Disabling an asset stops its runtime.
- Master Stop stops configured automation runtimes and asset automation runtimes.
- Emergency Stop emergency-stops all running asset automation runtimes.
- Section status now reports the real asset runtime and marks the section running when its backend runtime is active.
- Automations UI Running counters now include active asset runtimes.
- Empty asset pages now explain when the automatic runtime is actively discovering/analyzing/executing rather than incorrectly asking for a manual automation configuration.

Existing asset runtime implementations found: Stocks, Options, Crypto, ETFs, Forex, Bonds.
Futures has a UI tab but no futures automation runtime implementation in this package, so it remains unsupported rather than faking execution.
