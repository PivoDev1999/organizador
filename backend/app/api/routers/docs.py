"""Swagger UI without any CDN, so /api/docs works on a home network without internet.

The assets come from the npm package swagger-ui-dist (pinned in frontend/package.json):
- Docker stack: Nginx serves /api/docs-assets/ from a copy inside its image (these requests never get here).
- Development (uvicorn + vite): this router serves them from frontend/node_modules (SWAGGER_UI_DIR).

The page has no inline script (the initializer is a separate file), so it runs under a strict CSP.
"""

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import FileResponse, HTMLResponse

from app.api.deps import SettingsDep

DOCS_URL = "/api/docs"
DOCS_ASSETS_URL = "/api/docs-assets"
OPENAPI_URL = "/api/openapi.json"
# Only what the page loads: never the package's own index.html (it points to the petstore demo).
DOCS_ASSETS = ("swagger-ui-bundle.js", "swagger-ui.css", "favicon-32x32.png")

DOCS_HEADERS = {
    # Swagger UI only needs its own files, data: images (icons inside the CSS) and fetch to the API.
    "Content-Security-Policy": (
        "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
        "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
}

DOCS_HTML = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Organizador API - Swagger UI</title>
<link rel="stylesheet" href="{DOCS_ASSETS_URL}/swagger-ui.css">
<link rel="icon" type="image/png" href="{DOCS_ASSETS_URL}/favicon-32x32.png">
</head>
<body>
<div id="swagger-ui"></div>
<script src="{DOCS_ASSETS_URL}/swagger-ui-bundle.js"></script>
<script src="{DOCS_URL}/init.js"></script>
</body>
</html>
"""

# validatorUrl: null, otherwise Swagger UI loads a badge from validator.swagger.io (internet).
DOCS_INIT_JS = f"""window.ui = SwaggerUIBundle({{
  url: "{OPENAPI_URL}",
  dom_id: "#swagger-ui",
  layout: "BaseLayout",
  deepLinking: true,
  showExtensions: true,
  showCommonExtensions: true,
  validatorUrl: null,
  presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
}});
"""

router = APIRouter(include_in_schema=False)


@router.get(DOCS_URL)
def swagger_ui() -> HTMLResponse:
    return HTMLResponse(DOCS_HTML, headers=DOCS_HEADERS)


@router.get(f"{DOCS_URL}/init.js")
def swagger_ui_init() -> Response:
    return Response(DOCS_INIT_JS, media_type="text/javascript", headers=DOCS_HEADERS)


@router.get(DOCS_ASSETS_URL + "/{name}")
def swagger_ui_asset(name: str, settings: SettingsDep) -> FileResponse:
    path = settings.swagger_ui_dir / name
    if name not in DOCS_ASSETS or not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Arquivo não encontrado.")
    return FileResponse(path, headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "no-cache"})
