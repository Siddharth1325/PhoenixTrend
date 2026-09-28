using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.JSInterop;

namespace PhoenixTrend.Web.Services;

public sealed class AuthService
{
    private const string TokenKey = "phoenixtrend.auth.token";

    private readonly HttpClient _http;
    private readonly IJSRuntime _js;

    private bool _restored;

    public AuthService(
        HttpClient http,
        IJSRuntime js)
    {
        _http = http;
        _js = js;
    }

    public bool IsAuthenticated { get; private set; }

    public JsonElement? CurrentUser { get; private set; }


    public async Task<bool> RestoreAsync()
    {
        if (_restored)
        {
            return IsAuthenticated;
        }

        _restored = true;

        string? token;

        try
        {
            token = await _js.InvokeAsync<string?>(
                "phoenixAuth.get",
                TokenKey);
        }
        catch
        {
            return false;
        }

        if (string.IsNullOrWhiteSpace(token))
        {
            return false;
        }

        ApplyToken(token);

        try
        {
            using var response =
                await _http.GetAsync(
                    "/api/auth/me");

            if (!response.IsSuccessStatusCode)
            {
                await ClearAsync();
                return false;
            }

            var text =
                await response.Content
                    .ReadAsStringAsync();

            if (string.IsNullOrWhiteSpace(text))
            {
                await ClearAsync();
                return false;
            }

            using var document =
                JsonDocument.Parse(text);

            CurrentUser =
                ExtractUser(document.RootElement);

            if (CurrentUser is null)
            {
                await ClearAsync();
                return false;
            }

            IsAuthenticated = true;

            return true;
        }
        catch
        {
            await ClearAsync();
            return false;
        }
    }


    public Task<(bool Ok, string? Error)> LoginAsync(
        string email,
        string password)
    {
        return AuthenticateAsync(
            "/api/auth/login",
            new
            {
                email = email.Trim(),
                password
            });
    }


    public Task<(bool Ok, string? Error)> RegisterAsync(
        string email,
        string username,
        string displayName,
        string password)
    {
        return AuthenticateAsync(
            "/api/auth/register",
            new
            {
                email = email.Trim(),
                username = username.Trim(),
                display_name = displayName.Trim(),
                password
            });
    }


    private async Task<(bool Ok, string? Error)> AuthenticateAsync(
        string path,
        object body)
    {
        try
        {
            using var request =
                new HttpRequestMessage(
                    HttpMethod.Post,
                    path)
                {
                    Content =
                        JsonContent.Create(body)
                };

            using var response =
                await _http.SendAsync(request);

            var text =
                await response.Content
                    .ReadAsStringAsync();

            if (!response.IsSuccessStatusCode)
            {
                return (
                    false,
                    ExtractError(
                        text,
                        response.StatusCode));
            }

            if (string.IsNullOrWhiteSpace(text))
            {
                return (
                    false,
                    "Authentication service returned an empty response.");
            }

            using var document =
                JsonDocument.Parse(text);

            var root =
                document.RootElement;

            var token =
                ExtractToken(root);

            if (string.IsNullOrWhiteSpace(token))
            {
                return (
                    false,
                    "Authentication token was not returned.");
            }

            var user =
                ExtractUser(root);

            if (user is null)
            {
                return (
                    false,
                    "Authentication user information was not returned.");
            }

            try
            {
                await _js.InvokeVoidAsync(
                    "phoenixAuth.set",
                    TokenKey,
                    token);
            }
            catch
            {
                return (
                    false,
                    "PhoenixTrend could not save the authentication session.");
            }

            ApplyToken(token);

            CurrentUser = user;
            IsAuthenticated = true;
            _restored = true;

            return (
                true,
                null);
        }
        catch (HttpRequestException)
        {
            return (
                false,
                "PhoenixTrend could not reach the authentication service.");
        }
        catch (TaskCanceledException)
        {
            return (
                false,
                "PhoenixTrend authentication request timed out.");
        }
        catch (JsonException)
        {
            return (
                false,
                "PhoenixTrend authentication service returned an invalid response.");
        }
        catch (JSException)
        {
            return (
                false,
                "PhoenixTrend could not save the authentication session.");
        }
        catch
        {
            return (
                false,
                "PhoenixTrend authentication failed.");
        }
    }


    public async Task LogoutAsync()
    {
        try
        {
            using var request =
                new HttpRequestMessage(
                    HttpMethod.Post,
                    "/api/auth/logout")
                {
                    Content =
                        JsonContent.Create(
                            new { })
                };

            await _http.SendAsync(request);
        }
        catch
        {
            // Local logout must still succeed if the backend
            // is temporarily unavailable.
        }

        await ClearAsync();
    }


    private void ApplyToken(
        string token)
    {
        _http.DefaultRequestHeaders.Authorization =
            new AuthenticationHeaderValue(
                "Bearer",
                token);
    }


    private async Task ClearAsync()
    {
        IsAuthenticated = false;
        CurrentUser = null;

        _http.DefaultRequestHeaders.Authorization =
            null;

        try
        {
            await _js.InvokeVoidAsync(
                "phoenixAuth.remove",
                TokenKey);
        }
        catch
        {
            // Authentication state is still cleared in memory.
        }
    }


    private static string? ExtractToken(
        JsonElement root)
    {
        if (root.ValueKind !=
            JsonValueKind.Object)
        {
            return null;
        }

        if (root.TryGetProperty(
                "token",
                out var tokenElement) &&
            tokenElement.ValueKind ==
                JsonValueKind.String)
        {
            return tokenElement.GetString();
        }

        if (root.TryGetProperty(
                "access_token",
                out var accessTokenElement) &&
            accessTokenElement.ValueKind ==
                JsonValueKind.String)
        {
            return accessTokenElement.GetString();
        }

        return null;
    }


    private static JsonElement? ExtractUser(
        JsonElement root)
    {
        if (root.ValueKind !=
            JsonValueKind.Object)
        {
            return null;
        }

        if (root.TryGetProperty(
                "user",
                out var userElement) &&
            userElement.ValueKind ==
                JsonValueKind.Object)
        {
            return userElement.Clone();
        }

        if (root.TryGetProperty(
                "id",
                out _) ||
            root.TryGetProperty(
                "email",
                out _) ||
            root.TryGetProperty(
                "username",
                out _))
        {
            return root.Clone();
        }

        return null;
    }


    private static string ExtractError(
        string responseText,
        System.Net.HttpStatusCode statusCode)
    {
        if (!string.IsNullOrWhiteSpace(responseText))
        {
            try
            {
                using var document =
                    JsonDocument.Parse(
                        responseText);

                var root =
                    document.RootElement;

                if (root.ValueKind ==
                    JsonValueKind.Object)
                {
                    if (root.TryGetProperty(
                            "detail",
                            out var detail))
                    {
                        var message =
                            ReadErrorValue(detail);

                        if (!string.IsNullOrWhiteSpace(message))
                        {
                            return message;
                        }
                    }

                    if (root.TryGetProperty(
                            "message",
                            out var messageElement))
                    {
                        var message =
                            ReadErrorValue(
                                messageElement);

                        if (!string.IsNullOrWhiteSpace(message))
                        {
                            return message;
                        }
                    }

                    if (root.TryGetProperty(
                            "error",
                            out var errorElement))
                    {
                        var message =
                            ReadErrorValue(
                                errorElement);

                        if (!string.IsNullOrWhiteSpace(message))
                        {
                            return message;
                        }
                    }
                }
            }
            catch (JsonException)
            {
                // Use status-based message below.
            }
        }

        return statusCode switch
        {
            System.Net.HttpStatusCode.BadRequest =>
                "The authentication request was rejected.",

            System.Net.HttpStatusCode.Unauthorized =>
                "Invalid email or password.",

            System.Net.HttpStatusCode.Forbidden =>
                "This account is not permitted to sign in.",

            System.Net.HttpStatusCode.Conflict =>
                "An account with these details already exists.",

            System.Net.HttpStatusCode.TooManyRequests =>
                "Too many authentication attempts. Please try again shortly.",

            System.Net.HttpStatusCode.ServiceUnavailable =>
                "The authentication service is temporarily unavailable.",

            _ =>
                $"Authentication failed ({(int)statusCode})."
        };
    }


    private static string? ReadErrorValue(
        JsonElement element)
    {
        if (element.ValueKind ==
            JsonValueKind.String)
        {
            return element.GetString();
        }

        if (element.ValueKind ==
            JsonValueKind.Array)
        {
            foreach (
                var item
                in element.EnumerateArray())
            {
                if (item.ValueKind ==
                    JsonValueKind.String)
                {
                    var text =
                        item.GetString();

                    if (!string.IsNullOrWhiteSpace(text))
                    {
                        return text;
                    }
                }

                if (item.ValueKind ==
                    JsonValueKind.Object &&
                    item.TryGetProperty(
                        "msg",
                        out var message) &&
                    message.ValueKind ==
                        JsonValueKind.String)
                {
                    var text =
                        message.GetString();

                    if (!string.IsNullOrWhiteSpace(text))
                    {
                        return text;
                    }
                }
            }
        }

        if (element.ValueKind ==
            JsonValueKind.Object)
        {
            if (element.TryGetProperty(
                    "msg",
                    out var message) &&
                message.ValueKind ==
                    JsonValueKind.String)
            {
                return message.GetString();
            }

            if (element.TryGetProperty(
                    "message",
                    out var nestedMessage) &&
                nestedMessage.ValueKind ==
                    JsonValueKind.String)
            {
                return nestedMessage.GetString();
            }
        }

        return null;
    }
}