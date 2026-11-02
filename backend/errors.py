"""API errors in the documented shape: {"error": {"code", "message", ...}}."""


class ApiError(Exception):
    def __init__(self, status, code, message, **extra):
        super().__init__(message)
        self.status, self.code, self.message, self.extra = status, code, message, extra

    def body(self):
        return {"error": {"code": self.code, "message": self.message, **self.extra}}


def not_found(message="Not found."):
    return ApiError(404, "not_found", message)


def forbidden(message="You don't have access to this."):
    return ApiError(403, "forbidden", message)


def conflict(message):
    return ApiError(409, "conflict", message)


def invalid(message, **fields):
    return ApiError(422, "invalid", message, fields=fields) if fields else ApiError(422, "invalid", message)


def unauthenticated(message="Please sign in."):
    return ApiError(401, "unauthenticated", message)
