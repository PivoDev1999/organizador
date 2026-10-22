"""Domain errors raised by services. The api layer maps each family to an HTTP status."""


class DomainError(Exception):
    detail = "Não foi possível concluir a operação."

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or type(self).detail
        super().__init__(self.detail)


class NotFoundError(DomainError):
    detail = "Registro não encontrado."


class ConflictError(DomainError):
    detail = "Conflito com um registro existente."


class ForbiddenError(DomainError):
    detail = "Operação não permitida."


class UnauthorizedError(DomainError):
    detail = "Não autenticado."


class ValidationError(DomainError):
    """Business-rule validation that needs state the schema does not have (the stored row, "today").

    Mapped to 422 in the same shape as Pydantic errors (`{"detail": [{"type", "loc", "msg"}]}`), so
    clients see a single 422 contract. The message goes straight to the client, so it never includes
    the input.
    Not to be confused with `pydantic.ValidationError`.
    """

    detail = "Dados inválidos."


class ConcurrentChangeError(ConflictError):
    """Another transaction changed the same data at the same time (deadlock, serialization failure,
    or a row that kept changing while a service tried to lock it). Retrying usually works."""

    detail = "A operação conflitou com outra alteração simultânea. Tente novamente."
