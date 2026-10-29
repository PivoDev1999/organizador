import re


def test_docs_page_loads_nothing_from_outside(client):
    response = client.get("/api/docs")

    assert response.status_code == 200
    assert "script-src 'self';" in response.headers["content-security-policy"]
    # Every src/href is a local path: no CDN, so the page works without internet.
    urls = re.findall(r'(?:src|href)="([^"]+)"', response.text)
    assert urls and all(url.startswith("/api/") for url in urls)
    assert "<script>" not in response.text  # no inline script, required by the CSP

    init = client.get("/api/docs/init.js")
    assert init.status_code == 200
    assert '"/api/openapi.json"' in init.text
    assert "validatorUrl: null" in init.text


def test_docs_assets_are_served_from_the_local_package(client, override_settings, tmp_path):
    (tmp_path / "swagger-ui.css").write_text("body {}")
    (tmp_path / "index.html").write_text("<html></html>")
    override_settings(swagger_ui_dir=tmp_path)

    assert client.get("/api/docs-assets/swagger-ui.css").text == "body {}"
    # Only the files the page uses, and missing ones are a plain 404.
    assert client.get("/api/docs-assets/index.html").status_code == 404
    assert client.get("/api/docs-assets/swagger-ui-bundle.js").status_code == 404


def test_redoc_is_disabled(client):
    assert client.get("/api/redoc").status_code == 404
