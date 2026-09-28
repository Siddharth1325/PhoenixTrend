# PhoenixTrend v50 UI / wiring pass

- Added application-level authentication gate. Only `/login` and `/register` are public; protected routes redirect to login before page content is rendered.
- Portfolio, Risk and Settings section tabs now use Phosphor duotone icons and a consistent premium segmented-control design.
- Replaced oversized duplicated page JS with focused responsive/tab accessibility runtime for Portfolio, Risk, Settings and Trady AI.
- Portfolio Orders tab is now wired to `/api/broker/orders`, backed by the connected Alpaca broker open-orders API.
- Trady AI mode tabs now use the premium Phosphor icon library and the workspace layout has been tightened for useful vertical space and responsive behavior.
- Added responsive horizontal section navigation and compact/narrow page behavior.
- Existing real-user authentication, broker account/position wiring, risk calculations and previously fixed execution path remain intact.

Validation in this environment:
- Python backend syntax compilation: passed.
- JavaScript syntax checks for the four updated page runtimes: passed.
- Backend test run reached the existing authentication expectation mismatch: 7 tests passed before `test_strategy_http_endpoints_are_wired` expected anonymous 200 but the secured app correctly returned 401.
- .NET SDK is not installed in this artifact environment, so `dotnet build` could not be executed here.
