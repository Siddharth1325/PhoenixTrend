# PhoenixTrend - Render single-service production image
# Builds the Blazor WebAssembly frontend and runs it with FastAPI in one container.

FROM mcr.microsoft.com/dotnet/sdk:8.0 AS frontend-build
WORKDIR /src
COPY frontend/PhoenixTrend.Web/ ./
RUN dotnet restore ./PhoenixTrend.Web.csproj
RUN dotnet publish ./PhoenixTrend.Web.csproj -c Release -o /app/publish --no-restore

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=10000
WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY --from=frontend-build /app/publish/wwwroot ./wwwroot
COPY render_start.py ./render_start.py

EXPOSE 10000
CMD ["python", "render_start.py"]
