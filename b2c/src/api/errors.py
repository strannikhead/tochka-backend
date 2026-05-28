from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse


def error_response(status_code: int, *args: Any, **kwargs: Any) -> JSONResponse:
    """
    Flexible error response helper.

    Accepts calls like:
      error_response(400, "message")
      error_response(401, "message", "CODE")  # (message, code)
      error_response(401, "CODE", "message")  # (code, message)
      error_response(status_code=401, code="CODE", message="message")
    """
    code = kwargs.get("code")
    message = kwargs.get("message")

    if not message and not code and len(args) == 1:
        message = args[0]
    elif not message and not code and len(args) == 2:
        a, b = args[0], args[1]
        # Heuristic: if first arg looks like a code (ALL_CAPS, underscores), treat it as code
        if isinstance(a, str) and a.isupper() and " " not in a:
            code, message = a, b
        else:
            message, code = a, b
    elif not message and not code and len(args) == 0:
        message = ""

    if message is None:
        message = ""
    if code is None:
        code = "ERROR"

    return JSONResponse(status_code=status_code, content={"code": code, "message": str(message)})
