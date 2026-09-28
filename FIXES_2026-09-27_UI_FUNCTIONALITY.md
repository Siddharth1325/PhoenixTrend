# PhoenixTrend UI / Runtime Integration Fixes

- Preserved existing Automations and Manual Trade hero/banner artwork.
- Removed the redundant Automations hero refresh card and expanded hero copy/background across the full width.
- Added `/api/automation/activity` backed by the real asset automation runtime events/decisions/candidates.
- Wired Automations Engine Activity and Activity tab to real Stocks/Options/Crypto/etc. asset runtime telemetry.
- Added automatic 5-second Automations telemetry refresh; no manual refresh is required for live activity.
- Preserved the working master engine / section runtime orchestration.
- Added periodic top-level system/broker state rehydration and Manual Trade broker-status retry to prevent transient auth-on-refresh state from presenting a healthy backend broker as disconnected.
- Replaced the decorative notification badge with a functional status notification dropdown and corrected top-bar spacing.
- Manual Trade now defaults to AAPL when there are no positions, so the existing fixed chart logic has a valid initial symbol.
- Preserved the existing chart API/rendering logic; no replacement chart engine was introduced.
- Enabled the existing backend-supported Market, Limit, Stop and Stop-Limit order types in Manual Trade and passed limit/stop/TIF fields through PhoenixApi.
- Updated Manual Trade layout/CSS toward the approved chart-left / order-ticket-right / account-summary / positions structure without changing the hero image.

Validation:
- `python -m compileall backend/app`: PASS
- Backend tests: 13 PASS, 3 existing auth-expectation failures (tests call protected strategy endpoints without authentication).
- .NET SDK is not installed in this execution environment, so a local `dotnet build` could not be executed here.
