"""Reject unexpected browser origins and Host headers on the local-only app."""
from urllib.parse import urlsplit

from starlette.responses import JSONResponse


def local_authority(value, scheme="http"):
    try:
        parsed = urlsplit(f"{scheme}://{value}")
        if parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
            return None
        if parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
            return None
        return scheme, parsed.hostname, parsed.port or (443 if scheme == "https" else 80)
    except ValueError:
        return None


class LocalAccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = scope["headers"]
        hosts = [v.decode("latin1") for k, v in headers if k.lower() == b"host"]
        authority = local_authority(hosts[0], scope.get("scheme", "http")) if len(hosts) == 1 else None
        if authority is None:
            return await JSONResponse({"detail": "Only a localhost Host header is allowed."}, status_code=400)(scope, receive, send)
        origins = [v.decode("latin1") for k, v in headers if k.lower() == b"origin"]
        if origins:
            try:
                origin = urlsplit(origins[0]) if len(origins) == 1 else None
            except ValueError:
                origin = None
            allowed = {authority, ("http", "localhost", 5173), ("http", "127.0.0.1", 5173)}
            valid = (origin is not None and origin.scheme in {"http", "https"}
                     and not (origin.path or origin.query or origin.fragment)
                     and local_authority(origin.netloc, origin.scheme) in allowed)
            if not valid:
                return await JSONResponse({"detail": "This browser origin is not allowed."}, status_code=403)(scope, receive, send)
        # Native CLI clients may omit Origin. Browsers with opaque/sandboxed origins
        # send Origin: null, which is rejected above. CORS is not the access check.
        return await self.app(scope, receive, send)
