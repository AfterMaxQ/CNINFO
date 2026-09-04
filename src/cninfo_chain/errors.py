from __future__ import annotations


class CollectorError(RuntimeError):
    """Base error for stable collector failures."""


class SchemaChanged(CollectorError):
    pass


class SchemaConflict(CollectorError):
    pass


class ApiBusinessError(CollectorError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


class PaginationMismatch(CollectorError):
    pass


class NodeSetMismatch(CollectorError):
    pass


class UnknownZone(CollectorError):
    pass


class IdentityConflict(CollectorError):
    pass


class AuthenticationPaused(CollectorError):
    pass


class SecurityBoundaryError(CollectorError):
    pass


class ExportLocked(CollectorError):
    pass


class CompanyCellTooLong(CollectorError):
    pass
