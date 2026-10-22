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


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/tasks", "get"),
        ("/api/tasks", "post"),
        ("/api/tasks/{task_id}", "get"),
        ("/api/tasks/{task_id}", "patch"),
        ("/api/tasks/{task_id}", "delete"),
    ],
)
def test_task_endpoints_require_bearer_auth_in_openapi(openapi, path, method):
    assert openapi["paths"][path][method]["security"] == [{SCHEME: []}]


def test_task_list_documents_each_filter_as_query_param(openapi):
    params = {p["name"]: p["in"] for p in openapi["paths"]["/api/tasks"]["get"]["parameters"]}

    assert params == dict.fromkeys(
        ["status", "priority", "due_from", "due_to", "overdue", "q", "sort", "limit", "offset"], "query"
    )


def test_task_read_schema_does_not_expose_user_id(openapi):
    assert "user_id" not in openapi["components"]["schemas"]["TaskRead"]["properties"]


@pytest.mark.parametrize("schema", ["TaskCreate", "TaskUpdate"])
def test_task_input_schemas_forbid_extra_fields(openapi, schema):
    assert openapi["components"]["schemas"][schema]["additionalProperties"] is False
