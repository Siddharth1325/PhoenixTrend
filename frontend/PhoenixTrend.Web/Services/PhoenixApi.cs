// frontend/Services/PhoenixApi.cs

using System.Globalization;
using System.Net.Http.Json;
using System.Text.Json;

namespace PhoenixTrend.Web.Services;

public sealed class PhoenixApi
{
    private readonly HttpClient _http;

    private static readonly JsonSerializerOptions Json = new()
    {
        PropertyNameCaseInsensitive = true
    };

    public PhoenixApi(HttpClient http)
    {
        _http = http;
    }


    // ============================================================
    // GENERIC HTTP
    // ============================================================

    public async Task<JsonElement?> GetAsync(string path)
    {
        try
        {
            using var response =
                await _http.GetAsync(path);

            if (!response.IsSuccessStatusCode)
            {
                return null;
            }

            using var doc =
                JsonDocument.Parse(
                    await response.Content
                        .ReadAsStringAsync());

            return doc.RootElement.Clone();
        }
        catch
        {
            return null;
        }
    }


    public async Task<JsonElement?> PostAsync(
        string path,
        object body)
    {
        try
        {
            using var response =
                await _http.PostAsJsonAsync(
                    path,
                    body,
                    Json);

            if (!response.IsSuccessStatusCode)
            {
                return null;
            }

            using var doc =
                JsonDocument.Parse(
                    await response.Content
                        .ReadAsStringAsync());

            return doc.RootElement.Clone();
        }
        catch
        {
            return null;
        }
    }



    private async Task<JsonElement?> PostCheckedAsync(
        string path,
        object body)
    {
        using var response =
            await _http.PostAsJsonAsync(
                path,
                body,
                Json);

        var payload =
            await response.Content.ReadAsStringAsync();

        if (!response.IsSuccessStatusCode)
        {
            var message =
                $"Request failed ({(int)response.StatusCode}).";

            if (!string.IsNullOrWhiteSpace(payload))
            {
                try
                {
                    using var errorDoc =
                        JsonDocument.Parse(payload);

                    if (errorDoc.RootElement.ValueKind == JsonValueKind.Object &&
                        errorDoc.RootElement.TryGetProperty("detail", out var detail))
                    {
                        message = detail.ValueKind == JsonValueKind.String
                            ? detail.GetString() ?? message
                            : detail.ToString();
                    }
                }
                catch
                {
                    message = payload.Length <= 300
                        ? payload
                        : message;
                }
            }

            throw new InvalidOperationException(message);
        }

        if (string.IsNullOrWhiteSpace(payload))
            return null;

        using var doc = JsonDocument.Parse(payload);
        return doc.RootElement.Clone();
    }


    public async Task<JsonElement?> PutAsync(
        string path,
        object body)
    {
        try
        {
            using var response =
                await _http.PutAsJsonAsync(
                    path,
                    body,
                    Json);

            if (!response.IsSuccessStatusCode)
            {
                return null;
            }

            using var doc =
                JsonDocument.Parse(
                    await response.Content
                        .ReadAsStringAsync());

            return doc.RootElement.Clone();
        }
        catch
        {
            return null;
        }
    }


    public async Task<JsonElement?> DeleteAsync(
        string path)
    {
        try
        {
            using var response =
                await _http.DeleteAsync(path);

            if (!response.IsSuccessStatusCode)
            {
                return null;
            }

            using var doc =
                JsonDocument.Parse(
                    await response.Content
                        .ReadAsStringAsync());

            return doc.RootElement.Clone();
        }
        catch
        {
            return null;
        }
    }


    // ============================================================
    // HEALTH
    // ============================================================

    public Task<JsonElement?> Health() =>
        GetAsync("/api/health");


    // ============================================================
    // MARKET
    // ============================================================

    public Task<JsonElement?> Quote(
        string symbol) =>
        GetAsync(
            $"/api/market/{Uri.EscapeDataString(symbol)}");


    public Task<JsonElement?> ChartRange(
        string symbol,
        string range,
        string timeframe) =>
        GetAsync(
            $"/api/chart/{Uri.EscapeDataString(symbol)}" +
            $"?range={Uri.EscapeDataString(range)}" +
            $"&timeframe={Uri.EscapeDataString(timeframe)}");


    public Task<JsonElement?> Chart(
        string symbol,
        string timeframe = "1d",
        int limit = 120)
    {
        var normalized =
            timeframe
                .Trim()
                .ToLowerInvariant();

        var range =
            normalized switch
            {
                "1m" or "2m" or "5m" => "5D",

                "15m" or "30m" => "1M",

                "60m" or "1h" => "1M",

                "4h" => "6M",

                "1wk" or "1w" => "5Y",

                "1mo" => "5Y",

                _ => limit switch
                {
                    <= 7 => "5D",
                    <= 31 => "1M",
                    <= 100 => "3M",
                    <= 260 => "1Y",
                    _ => "5Y"
                }
            };

        return ChartRange(
            symbol,
            range,
            timeframe);
    }


    public Task<JsonElement?> ChartLatest(
        string symbol,
        string timeframe = "1M") =>
        GetAsync(
            $"/api/chart/{Uri.EscapeDataString(symbol)}/latest" +
            $"?timeframe={Uri.EscapeDataString(timeframe)}");


    public Task<JsonElement?> ChartLevels(
        string symbol,
        string range = "6M",
        string timeframe = "1D",
        int lookback = 120) =>
        GetAsync(
            $"/api/chart/{Uri.EscapeDataString(symbol)}/levels" +
            $"?range={Uri.EscapeDataString(range)}" +
            $"&timeframe={Uri.EscapeDataString(timeframe)}" +
            $"&lookback={Math.Clamp(lookback, 10, 1000)}");


    public Task<JsonElement?> ChartEvents(
        string symbol,
        string range = "5Y") =>
        GetAsync(
            $"/api/chart/{Uri.EscapeDataString(symbol)}/events" +
            $"?range={Uri.EscapeDataString(range)}");


    public Task<JsonElement?> Context(
        string symbol) =>
        GetAsync(
            $"/api/market-context/{Uri.EscapeDataString(symbol)}");


    // ============================================================
    // ANALYSIS
    // ============================================================

    public Task<JsonElement?> Analyze(
        string symbol) =>
        GetAsync(
            $"/api/analyze/{Uri.EscapeDataString(symbol)}");


    public Task<JsonElement?> Patterns(
        string symbol) =>
        GetAsync(
            $"/api/patterns/{Uri.EscapeDataString(symbol)}");


    // ============================================================
    // DISCOVER
    // ============================================================

    public Task<JsonElement?> Discover() =>
        GetAsync("/api/discover");


    public Task<JsonElement?> DiscoverCategory(
        string category) =>
        GetAsync(
            $"/api/discover/category/{Uri.EscapeDataString(category)}");


    public Task<JsonElement?> UnusualActivity(
        double minRatio = 1.5,
        int limit = 20) =>
        GetAsync(
            "/api/discover/unusual-activity" +
            $"?min_ratio={minRatio.ToString(CultureInfo.InvariantCulture)}" +
            $"&limit={limit}");


    // ============================================================
    // INTELLIGENCE
    // ============================================================

    public Task<JsonElement?> Intelligence(
        string symbol) =>
        GetAsync(
            $"/api/intelligence/{Uri.EscapeDataString(symbol)}");


    // ============================================================
    // NEWS
    // ============================================================

    public Task<JsonElement?> News(
        string symbol) =>
        GetAsync(
            $"/api/news/{Uri.EscapeDataString(symbol)}");


    // ============================================================
    // STRATEGIES
    // ============================================================

    public Task<JsonElement?> Strategies() =>
        GetAsync("/api/strategies");


    public Task<JsonElement?> StrategyPerformance(
        string strategy) =>
        GetAsync(
            $"/api/strategies/{Uri.EscapeDataString(strategy)}/performance");


    public Task<JsonElement?> EnableStrategy(
        string name) =>
        PostAsync(
            $"/api/strategies/{Uri.EscapeDataString(name)}/enable",
            new { });


    public Task<JsonElement?> DisableStrategy(
        string name) =>
        PostAsync(
            $"/api/strategies/{Uri.EscapeDataString(name)}/disable",
            new { });


    public Task<JsonElement?> ConfigureStrategy(
        string name,
        Dictionary<string, object> configuration) =>
        PutAsync(
            $"/api/strategies/{Uri.EscapeDataString(name)}/configuration",
            new
            {
                configuration,
                replace = false
            });


    public Task<JsonElement?> ResetStrategy(
        string name) =>
        DeleteAsync(
            $"/api/strategies/{Uri.EscapeDataString(name)}/configuration");


    public Task<JsonElement?> CreateCustomStrategy(
        string name,
        string baseStrategy,
        Dictionary<string, object> configuration) =>
        PostAsync(
            "/api/strategies/custom",
            new
            {
                name,
                base_strategy = baseStrategy,
                configuration
            });


    public Task<JsonElement?> DeleteCustomStrategy(
        string name) =>
        DeleteAsync(
            $"/api/strategies/custom/{Uri.EscapeDataString(name)}");


    // ============================================================
    // AUTOMATIONS
    // ============================================================

    public Task<JsonElement?> Automations() =>
        GetAsync("/api/automations");


    public Task<JsonElement?> AutomationRuntimes() =>
        GetAsync("/api/automations/runtime");

    public Task<JsonElement?> AutomationAssetActivity() =>
        GetAsync("/api/automation/activity");


    public Task<JsonElement?> CreateAutomation(
        string name,
        string[] symbols,
        string? strategy,
        bool autoSelectStrategy,
        double maxPositionValue) =>
        CreateAutomation(
            name,
            symbols,
            strategy,
            autoSelectStrategy,
            maxPositionValue,
            "stocks",
            "intraday",
            null,
            null,
            null,
            true,
            false,
            false);


    public Task<JsonElement?> CreateAutomation(
        string name,
        string[] symbols,
        string? strategy,
        bool autoSelectStrategy,
        double maxPositionValue,
        string assetClass,
        string tradingStyle,
        double? capitalAllocation,
        double? maxDailyLoss,
        int? maxOpenPositions,
        bool allowLong,
        bool allowShort,
        bool enabled = false) =>
        PostAsync(
            "/api/automations",
            new
            {
                name,
                symbols,
                strategy,

                auto_select_strategy =
                    autoSelectStrategy,

                max_position_value =
                    maxPositionValue,

                enabled,

                asset_class =
                    assetClass,

                trading_style =
                    tradingStyle,

                capital_allocation =
                    capitalAllocation,

                max_daily_loss =
                    maxDailyLoss,

                max_open_positions =
                    maxOpenPositions,

                allow_long =
                    allowLong,

                allow_short =
                    allowShort
            });


    public Task<JsonElement?> UpdateAutomation(
        string id,
        string? name = null,
        string[]? symbols = null,
        string? strategy = null,
        bool? autoSelectStrategy = null,
        double? maxPositionValue = null,
        string? assetClass = null,
        string? tradingStyle = null,
        double? capitalAllocation = null,
        double? maxDailyLoss = null,
        int? maxOpenPositions = null,
        bool? allowLong = null,
        bool? allowShort = null) =>
        PostAsync(
            $"/api/automations/{Uri.EscapeDataString(id)}/update",
            new
            {
                name,
                symbols,
                strategy,

                auto_select_strategy =
                    autoSelectStrategy,

                max_position_value =
                    maxPositionValue,

                asset_class =
                    assetClass,

                trading_style =
                    tradingStyle,

                capital_allocation =
                    capitalAllocation,

                max_daily_loss =
                    maxDailyLoss,

                max_open_positions =
                    maxOpenPositions,

                allow_long =
                    allowLong,

                allow_short =
                    allowShort
            });


    public Task<JsonElement?> EnableAutomation(
        string id) =>
        PostAsync(
            $"/api/automations/{Uri.EscapeDataString(id)}/enable",
            new { });


    public Task<JsonElement?> DisableAutomation(
        string id) =>
        PostAsync(
            $"/api/automations/{Uri.EscapeDataString(id)}/disable",
            new { });


    public Task<JsonElement?> StartAutomation(
        string id) =>
        PostAsync(
            $"/api/automations/{Uri.EscapeDataString(id)}/start",
            new { });


    public Task<JsonElement?> StopAutomation(
        string id) =>
        PostAsync(
            $"/api/automations/{Uri.EscapeDataString(id)}/stop",
            new { });


    public Task<JsonElement?> PauseAutomation(
        string id) =>
        PostAsync(
            $"/api/automations/{Uri.EscapeDataString(id)}/pause",
            new { });


    public Task<JsonElement?> ResumeAutomation(
        string id) =>
        PostAsync(
            $"/api/automations/{Uri.EscapeDataString(id)}/resume",
            new { });


    public Task<JsonElement?> EmergencyStopAutomation(
        string id) =>
        PostAsync(
            $"/api/automations/{Uri.EscapeDataString(id)}/emergency-stop",
            new { });


    // ============================================================
    // AUTOMATION MASTER ENGINE
    // ============================================================

    public Task<JsonElement?> AutomationEngineStatus() =>
        GetAsync(
            "/api/automation/engine/status");


    public Task<JsonElement?> StartAutomationEngine() =>
        PostAsync(
            "/api/automation/engine/start",
            new { });


    public Task<JsonElement?> StopAutomationEngine() =>
        PostAsync(
            "/api/automation/engine/stop",
            new { });


    public Task<JsonElement?> EmergencyStopAutomationEngine() =>
        PostAsync(
            "/api/automation/engine/emergency-stop",
            new { });


    public Task<JsonElement?> ClearAutomationEngineEmergencyStop() =>
        PostAsync(
            "/api/automation/engine/clear-emergency-stop",
            new { });


    // ============================================================
    // AUTOMATION CAPABILITIES
    // ============================================================

    public Task<JsonElement?> AutomationCapabilities() =>
        GetAsync(
            "/api/automation/capabilities");


    // ============================================================
    // AUTOMATION ASSET SECTIONS
    // ============================================================

    public Task<JsonElement?> AutomationAssetSections() =>
        GetAsync(
            "/api/automation/sections");


    public Task<JsonElement?> AutomationAssetSection(
        string assetClass) =>
        GetAsync(
            $"/api/automation/sections/" +
            $"{Uri.EscapeDataString(assetClass)}");


    public Task<JsonElement?> EnableAutomationAssetSection(
        string assetClass) =>
        PostAsync(
            $"/api/automation/sections/" +
            $"{Uri.EscapeDataString(assetClass)}/enable",
            new { });


    public Task<JsonElement?> DisableAutomationAssetSection(
        string assetClass) =>
        PostAsync(
            $"/api/automation/sections/" +
            $"{Uri.EscapeDataString(assetClass)}/disable",
            new { });


    // ============================================================
    // BROKER
    // ============================================================

    public Task<JsonElement?> BrokerStatus() =>
        GetAsync(
            "/api/broker/status");


    public Task<JsonElement?> BrokerAccount() =>
        GetAsync(
            "/api/broker/account");


    public Task<JsonElement?> BrokerPositions() =>
        GetAsync(
            "/api/broker/positions");


    public Task<JsonElement?> BrokerOrders() =>
        GetAsync(
            "/api/broker/orders");


    public Task<JsonElement?> ConnectAlpaca(
        string key,
        string secret,
        bool paper) =>
        PostAsync(
            "/api/broker/alpaca/connect",
            new
            {
                api_key = key,
                secret_key = secret,
                paper
            });


    public Task<JsonElement?> DisconnectBroker() =>
        PostAsync(
            "/api/broker/disconnect",
            new { });


    // ============================================================
    // ENGINE
    // ============================================================

    public Task<JsonElement?> EngineStatus() =>
        GetAsync(
            "/api/engine/status");


    // ============================================================
    // POSITIONS
    // ============================================================

    public Task<JsonElement?> Positions() =>
        GetAsync(
            "/api/positions");


    // ============================================================
    // ANALYTICS
    // ============================================================

    public Task<JsonElement?> Analytics() =>
        GetAsync(
            "/api/analytics");


    // ============================================================
    // ACTIVITY
    // ============================================================

    public Task<JsonElement?> Activity() =>
        GetAsync(
            "/api/activity");


    // ============================================================
    // MANUAL TRADING
    // ============================================================

    public Task<JsonElement?> ManualAnalyze(
        string symbol,
        string? strategy = null) =>
        PostAsync(
            "/api/manual/analyze",
            new
            {
                symbol,
                strategy
            });


    public Task<JsonElement?> ManualOrder(
        string symbol,
        string side,
        double quantity,
        string orderType = "market",
        double? limitPrice = null,
        double? stopPrice = null,
        string timeInForce = "day") =>
        PostCheckedAsync(
            "/api/manual/order",
            new
            {
                symbol,
                side,
                qty = quantity,

                order_type =
                    orderType,

                limit_price = limitPrice,
                stop_price = stopPrice,
                time_in_force = timeInForce
            });


    // ============================================================
    // AUTOMATIC TRADING
    // ============================================================

    public Task<JsonElement?> StartAutomatic(
        string? strategy = null) =>
        PostAsync(
            "/api/automatic/start",
            new
            {
                strategy,

                auto_select_strategy =
                    strategy is null
            });


    public Task<JsonElement?> StopAutomatic() =>
        PostAsync(
            "/api/automatic/stop",
            new { });


    // ============================================================
    // JSON HELPERS
    // ============================================================

    public static string Text(
        JsonElement? root,
        string property,
        string fallback = "—")
    {
        if (
            root is null
            || root.Value.ValueKind
                != JsonValueKind.Object
            || !root.Value.TryGetProperty(
                property,
                out var value)
        )
        {
            return fallback;
        }

        if (
            value.ValueKind
                is JsonValueKind.Null
                or JsonValueKind.Undefined
        )
        {
            return fallback;
        }

        return value.ValueKind switch
        {
            JsonValueKind.String =>
                value.GetString()
                ?? fallback,

            JsonValueKind.Number =>
                value.ToString(),

            JsonValueKind.True =>
                "true",

            JsonValueKind.False =>
                "false",

            _ =>
                value.ToString()
        };
    }


    public static double Number(
        JsonElement? root,
        string property,
        double fallback = 0)
    {
        var value =
            NullableNumber(
                root,
                property);

        return value
            ?? fallback;
    }


    /// <summary>
    /// Returns a genuine numeric JSON value or null.
    ///
    /// This should be used for trading performance metrics where
    /// "missing" must NOT be silently converted to zero.
    ///
    /// Examples:
    ///
    ///     win_rate
    ///     realized_pnl
    ///     profit_factor
    ///     average_trade
    ///     total_return
    /// </summary>
    public static double? NullableNumber(
        JsonElement? root,
        string property)
    {
        if (
            root is null
            || root.Value.ValueKind
                != JsonValueKind.Object
            || !root.Value.TryGetProperty(
                property,
                out var value)
        )
        {
            return null;
        }

        if (
            value.ValueKind
                is JsonValueKind.Null
                or JsonValueKind.Undefined
        )
        {
            return null;
        }

        if (
            value.ValueKind
                == JsonValueKind.Number
            && value.TryGetDouble(
                out var number)
        )
        {
            return number;
        }

        if (
            value.ValueKind
                == JsonValueKind.String
        )
        {
            var text =
                value.GetString();

            if (
                string.IsNullOrWhiteSpace(
                    text)
            )
            {
                return null;
            }

            if (
                double.TryParse(
                    text,
                    NumberStyles.Float
                    | NumberStyles.AllowThousands,
                    CultureInfo.InvariantCulture,
                    out number)
            )
            {
                return number;
            }
        }

        return null;
    }


    /// <summary>
    /// Returns a nested JSON object or null.
    ///
    /// /api/strategies returns each strategy with:
    ///
    ///     "performance": { ... }
    ///
    /// or:
    ///
    ///     "performance": null
    ///
    /// This helper keeps that distinction intact.
    /// </summary>
    public static JsonElement? Object(
        JsonElement? root,
        string property)
    {
        if (
            root is null
            || root.Value.ValueKind
                != JsonValueKind.Object
            || !root.Value.TryGetProperty(
                property,
                out var value)
        )
        {
            return null;
        }

        if (
            value.ValueKind
                != JsonValueKind.Object
        )
        {
            return null;
        }

        return value.Clone();
    }


    /// <summary>
    /// Returns a nested JSON array or null.
    /// </summary>
    public static JsonElement? Array(
        JsonElement? root,
        string property)
    {
        if (
            root is null
            || root.Value.ValueKind
                != JsonValueKind.Object
            || !root.Value.TryGetProperty(
                property,
                out var value)
        )
        {
            return null;
        }

        if (
            value.ValueKind
                != JsonValueKind.Array
        )
        {
            return null;
        }

        return value.Clone();
    }


    /// <summary>
    /// Returns a genuine integer JSON value or null.
    ///
    /// Useful for trade counts, wins and losses.
    /// </summary>
    public static int? NullableInt(
        JsonElement? root,
        string property)
    {
        if (
            root is null
            || root.Value.ValueKind
                != JsonValueKind.Object
            || !root.Value.TryGetProperty(
                property,
                out var value)
        )
        {
            return null;
        }

        if (
            value.ValueKind
                is JsonValueKind.Null
                or JsonValueKind.Undefined
        )
        {
            return null;
        }

        if (
            value.ValueKind
                == JsonValueKind.Number
        )
        {
            if (
                value.TryGetInt32(
                    out var integer)
            )
            {
                return integer;
            }

            if (
                value.TryGetDouble(
                    out var number)
            )
            {
                return Convert.ToInt32(
                    number);
            }
        }

        if (
            value.ValueKind
                == JsonValueKind.String
        )
        {
            var text =
                value.GetString();

            if (
                int.TryParse(
                    text,
                    NumberStyles.Integer,
                    CultureInfo.InvariantCulture,
                    out var integer)
            )
            {
                return integer;
            }
        }

        return null;
    }


    /// <summary>
    /// Returns a genuine boolean value or null.
    /// </summary>
    public static bool? NullableBool(
        JsonElement? root,
        string property)
    {
        if (
            root is null
            || root.Value.ValueKind
                != JsonValueKind.Object
            || !root.Value.TryGetProperty(
                property,
                out var value)
        )
        {
            return null;
        }

        if (
            value.ValueKind
                == JsonValueKind.True
        )
        {
            return true;
        }

        if (
            value.ValueKind
                == JsonValueKind.False
        )
        {
            return false;
        }

        if (
            value.ValueKind
                == JsonValueKind.String
            && bool.TryParse(
                value.GetString(),
                out var result)
        )
        {
            return result;
        }

        return null;
    }


    /// <summary>
    /// Checks whether an object has a non-null JSON property.
    /// </summary>
    public static bool HasValue(
        JsonElement? root,
        string property)
    {
        if (
            root is null
            || root.Value.ValueKind
                != JsonValueKind.Object
            || !root.Value.TryGetProperty(
                property,
                out var value)
        )
        {
            return false;
        }

        return value.ValueKind
            is not JsonValueKind.Null
            and not JsonValueKind.Undefined;
    }
}