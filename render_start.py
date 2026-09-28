import os
import uvicorn
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from app.main import app

WEB_ROOT = os.path.join(os.path.dirname(__file__), "wwwroot")
INDEX = os.path.join(WEB_ROOT, "index.html")

# API/WebSocket routes from app.main are registered first.
@app.get("/health", include_in_schema=False)
async def render_health():
    return {"status": "ok"}

# Static files are mounted last so they cannot shadow /api routes.
if os.path.isdir(WEB_ROOT):
    app.mount("/_content", StaticFiles(directory=os.path.join(WEB_ROOT, "_content"), check_dir=False), name="content")
    app.mount("/_framework", StaticFiles(directory=os.path.join(WEB_ROOT, "_framework"), check_dir=False), name="framework")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        requested = os.path.join(WEB_ROOT, full_path)
        if full_path and os.path.isfile(requested):
            return FileResponse(requested)
        return FileResponse(INDEX)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "10000"))
    uvicorn.run(app, host="0.0.0.0", port=port, proxy_headers=True, forwarded_allow_ips="*")
