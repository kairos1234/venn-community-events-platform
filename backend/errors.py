class AppError(Exception):
    """An expected, client-facing failure. Carries a stable code and a safe message."""

    status = 500

    def __init__(self, code: str, message: str, fields: dict | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.fields = fields

    def to_dict(self) -> dict:
        body = {"code": self.code, "message": self.message}
        if self.fields:
            body["fields"] = self.fields
        return body


class ValidationError(AppError):
    status = 400


class ForbiddenError(AppError):
    status = 403


class NotFoundError(AppError):
    status = 404


class ConflictError(AppError):
    status = 409


class PayloadTooLargeError(AppError):
    status = 413
