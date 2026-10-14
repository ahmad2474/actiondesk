class DomainError(Exception):
    def __init__(
        self, status: int, title: str, detail: str, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.title = title
        self.detail = detail
        self.headers = headers or {}
