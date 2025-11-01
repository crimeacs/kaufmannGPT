from typing import Optional, Tuple, Dict, Any
from datetime import datetime


def error_payload(code: str, message: str, *, upstream_status: Optional[int] = None, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "error": {
            "code": code,
            "message": message,
            "upstream_status": upstream_status,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }
    }


def map_exception(e: Exception) -> Tuple[int, Dict[str, Any]]:
    msg = str(e) if e else ""

    # Authentication / authorization with upstream
    if "401" in msg or "Unauthorized" in msg or "invalid_api_key" in msg:
        return 502, error_payload("UPSTREAM_AUTH", "Upstream authentication failed (check OPENAI_API_KEY)", upstream_status=401)

    # Timeouts
    if "Timeout" in msg or "timed out" in msg:
        return 504, error_payload("UPSTREAM_TIMEOUT", "Upstream request timed out")

    # Upstream errors (generic)
    if "API error" in msg or "Failed to connect" in msg or "Connection" in msg or "Service Unavailable" in msg:
        return 502, error_payload("UPSTREAM_ERROR", "Upstream service error", details={"message": msg})

    # Validation errors
    if isinstance(e, ValueError):
        return 400, error_payload("VALIDATION_ERROR", msg or "Invalid request")

    # Default internal
    return 500, error_payload("INTERNAL_ERROR", msg or "Internal server error")

