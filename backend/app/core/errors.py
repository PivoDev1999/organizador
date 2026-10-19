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
