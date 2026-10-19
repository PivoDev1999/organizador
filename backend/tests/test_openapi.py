import pytest

SCHEME = "OAuth2PasswordBearer"


@pytest.fixture
def openapi(client):
    response = client.get("/api/openapi.json")
    assert response.status_code == 200
    return response.json()


def test_openapi_declares_oauth2_password_bearer_scheme(openapi):
    scheme = openapi["components"]["securitySchemes"][SCHEME]

    assert scheme["type"] == "oauth2"
    assert scheme["flows"]["password"]["tokenUrl"] == "/api/auth/login"


def test_me_requires_bearer_auth_in_openapi(openapi):
    assert openapi["paths"]["/api/auth/me"]["get"]["security"] == [{SCHEME: []}]


@pytest.mark.parametrize("path", ["/api/auth/login", "/api/auth/register"])
def test_public_auth_endpoints_do_not_require_auth_in_openapi(openapi, path):
    assert "security" not in openapi["paths"][path]["post"]


def test_login_is_documented_as_form_request(openapi):
    content = openapi["paths"]["/api/auth/login"]["post"]["requestBody"]["content"]

    assert list(content) == ["application/x-www-form-urlencoded"]


def test_user_read_schema_does_not_expose_password(openapi):
    properties = openapi["components"]["schemas"]["UserRead"]["properties"]

    assert "password" not in properties
    assert "password_hash" not in properties
