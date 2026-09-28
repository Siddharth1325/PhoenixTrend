using Microsoft.AspNetCore.Components.Web;
using Microsoft.AspNetCore.Components.WebAssembly.Hosting;
using PhoenixTrend.Web;
using PhoenixTrend.Web.Services;


// ============================================================
// PHOENIXTREND WEB APPLICATION
// ============================================================

var builder =
    WebAssemblyHostBuilder.CreateDefault(args);


// ============================================================
// ROOT COMPONENTS
// ============================================================

builder.RootComponents.Add<App>("#app");

builder.RootComponents.Add<HeadOutlet>(
    "head::after"
);


// ============================================================
// API CONFIGURATION
// ============================================================

/*
 * Production / Docker:
 *
 * The frontend is served by nginx.
 *
 * Browser:
 *      http://localhost:89
 *
 * API calls:
 *      http://localhost:89/api/...
 *
 * nginx then proxies:
 *
 *      /api/*
 *          ->
 *      http://backend:8080/api/*
 *
 *
 * Local development:
 *
 * ApiBaseUrl can be supplied through configuration
 * when the backend is running separately.
 */

var configuredApiBaseUrl =
    builder.Configuration["ApiBaseUrl"];


var apiBaseUrl =
    !string.IsNullOrWhiteSpace(configuredApiBaseUrl)
        ? configuredApiBaseUrl
        : builder.HostEnvironment.BaseAddress;


// ============================================================
// HTTP CLIENT
// ============================================================

builder.Services.AddScoped(
    _ => new HttpClient
    {
        BaseAddress =
            new Uri(apiBaseUrl)
    });


// ============================================================
// PHOENIXTREND SERVICES
// ============================================================

builder.Services.AddScoped<PhoenixApi>();
builder.Services.AddScoped<AuthService>();


// ============================================================
// START APPLICATION
// ============================================================

await builder
    .Build()
    .RunAsync();