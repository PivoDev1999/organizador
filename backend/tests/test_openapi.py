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


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/routines", "get"),
        ("/api/routines", "post"),
        ("/api/routines/today", "get"),
        ("/api/routines/{routine_id}", "get"),
        ("/api/routines/{routine_id}", "patch"),
        ("/api/routines/{routine_id}", "delete"),
        ("/api/routines/{routine_id}/logs", "get"),
        ("/api/routines/{routine_id}/logs", "post"),
        ("/api/routines/{routine_id}/logs/{done_on}", "delete"),
    ],
)
def test_routine_endpoints_require_bearer_auth_in_openapi(openapi, path, method):
    assert openapi["paths"][path][method]["security"] == [{SCHEME: []}]


def test_routine_logs_document_from_and_to_query_params(openapi):
    params = {
        p["name"]: p["in"] for p in openapi["paths"]["/api/routines/{routine_id}/logs"]["get"]["parameters"]
    }

    assert params == {"routine_id": "path", **dict.fromkeys(["from", "to", "limit", "offset"], "query")}


def test_routine_read_schema_does_not_expose_user_id(openapi):
    assert "user_id" not in openapi["components"]["schemas"]["RoutineRead"]["properties"]


@pytest.mark.parametrize(
    ("path", "method"),
    [
        ("/api/pantry", "get"),
        ("/api/pantry", "post"),
        ("/api/pantry/alerts", "get"),
        ("/api/pantry/categories", "get"),
        ("/api/pantry/locations", "get"),
        ("/api/pantry/{item_id}", "get"),
        ("/api/pantry/{item_id}", "patch"),
        ("/api/pantry/{item_id}", "delete"),
        ("/api/pantry/{item_id}/consume", "post"),
        ("/api/pantry/{item_id}/restock", "post"),
    ],
)
def test_pantry_endpoints_require_bearer_auth_in_openapi(openapi, path, method):
    assert openapi["paths"][path][method]["security"] == [{SCHEME: []}]


def test_pantry_read_exposes_quantities_as_decimal_strings_and_no_user_id(openapi):
    properties = openapi["components"]["schemas"]["PantryItemRead"]["properties"]

    assert "user_id" not in properties
    assert (properties["quantity"]["type"], properties["quantity"]["format"]) == ("string", "decimal")


@pytest.mark.parametrize(
    ("schema", "field", "bound"),
    [
        ("StockChange", "amount", {"exclusiveMinimum": 0}),
        ("PantryItemCreate", "quantity", {"minimum": 0}),
    ],
)
def test_decimal_fields_keep_their_bounds_in_openapi(client, schema, field, bound):
    prop = client.get("/api/openapi.json").json()["components"]["schemas"][schema]["properties"][field]
    assert bound.items() <= prop.items()
    assert prop["maximum"] == 9999999.999
