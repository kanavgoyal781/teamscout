import re
from typing import Any
def _service_label(service: str) -> str:
    name = (service or "Service").strip()
    return name if re.search(r"(?i)\bapi\s*$", name) else f"{name} API"
class TeamScoutError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        error_code: str = "internal_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        from app.core.redact import redact_details, redact_error
        safe_message = redact_error(message)
        safe_details = redact_details(details)
        super().__init__(safe_message)
        self.message = safe_message
        self.status_code = status_code
        self.error_code = error_code
        self.details = safe_details
class ServiceNotConfiguredError(TeamScoutError):
    def __init__(self, service: str, env_var: str) -> None:
        super().__init__(
            f"{_service_label(service)} not configured — set {env_var}",
            status_code=503, error_code="service_not_configured",
            details={"service": service, "env_var": env_var},
        )
class ServiceFailingError(TeamScoutError):
    def __init__(self, service: str, reason: str) -> None:
        from app.core.redact import redact_error
        safe_reason = redact_error(reason)
        super().__init__(
            f"{_service_label(service)} is failing — {safe_reason}",
            status_code=503, error_code="service_failing",
            details={"service": service, "reason": safe_reason},
        )
class ValidationError(TeamScoutError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None, status_code: int = 400) -> None:
        super().__init__(message, status_code=status_code, error_code="validation_error", details=details)
class NotFoundError(TeamScoutError):
    def __init__(self, resource: str, resource_id: str) -> None:
        super().__init__(
            f"{resource} not found: {resource_id}",
            status_code=404,
            error_code="not_found",
            details={"resource": resource, "id": resource_id},
        )
class CostCeilingExceededError(TeamScoutError):
    """Daily LLM cost or Sumble credit ceiling hit — fail closed (HTTP 429)."""
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(
            message,
            status_code=429,
            error_code="cost_ceiling_exceeded",
            details=details,
        )
class OpsAuthError(TeamScoutError):
    def __init__(self, message: str = "Ops access denied") -> None:
        super().__init__(message, status_code=401, error_code="ops_unauthorized")
