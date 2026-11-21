class ApiError(Exception):
    """Raised anywhere in the backend; rendered as JSON {"detail": ...} with the given HTTP status."""

    def __init__(self, status: int, detail: str = ""):
        super().__init__(detail)
        self.status = status
        self.detail = detail
