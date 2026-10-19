import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.errors import register_exception_handlers
from app.core.errors import ConflictError, DomainError, ForbiddenError, NotFoundError, UnauthorizedError


class PetNotFound(NotFoundError):
    detail = "Pet não encontrado."


ERRORS = {
    "base": DomainError,
    "not-found": NotFoundError,
    "subclass": PetNotFound,
    "conflict": ConflictError,
    "forbidden": ForbiddenError,
    "unauthorized": UnauthorizedError,
}


@pytest.fixture(scope="module")
def errors_client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/raise/{name}")
    def raise_error(name: str, detail: str | None = None) -> None:
        raise ERRORS[name](detail)

    return TestClient(app)


@pytest.mark.parametrize(
    ("name", "status_code", "detail"),
    [
        ("base", 400, "Não foi possível concluir a operação."),
        ("not-found", 404, "Registro não encontrado."),
        ("subclass", 404, "Pet não encontrado."),
        ("conflict", 409, "Conflito com um registro existente."),
        ("forbidden", 403, "Operação não permitida."),
        ("unauthorized", 401, "Não autenticado."),
    ],
)
def test_domain_errors_map_to_http_status(errors_client, name, status_code, detail):
    response = errors_client.get(f"/raise/{name}")

    assert response.status_code == status_code
    assert response.json() == {"detail": detail}


def test_domain_error_accepts_custom_detail(errors_client):
    response = errors_client.get("/raise/conflict", params={"detail": "Já existe."})

    assert response.json() == {"detail": "Já existe."}


@pytest.mark.parametrize("name", ["unauthorized", "not-found", "conflict"])
def test_only_401_sends_www_authenticate(errors_client, name):
    response = errors_client.get(f"/raise/{name}")

    assert ("www-authenticate" in response.headers) == (name == "unauthorized")
    if name == "unauthorized":
        assert response.headers["WWW-Authenticate"] == "Bearer"
