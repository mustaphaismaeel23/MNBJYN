"""CORS + hardening headers for everything under /api/.

* Public read-only endpoints answer ``Access-Control-Allow-Origin: *`` (GET only).
* Every other endpoint only allows the origins listed in API_CORS_ORIGINS.
  Native mobile apps do not use CORS at all, so by default no browser origin is allowed.
"""
from django.conf import settings
from django.http import HttpResponse

PUBLIC_PREFIXES = ("/api/v1/public/", "/api/v1/health", "/api/v1/openapi.json")


class ApiMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith("/api/"):
            return self.get_response(request)
        if request.method == "OPTIONS":
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)
        self._cors(request, response)
        response["X-Content-Type-Options"] = "nosniff"
        response["Referrer-Policy"] = "no-referrer"
        response["Cross-Origin-Resource-Policy"] = "cross-origin"
        return response

    @staticmethod
    def _cors(request, response):
        origin = request.META.get("HTTP_ORIGIN")
        if not origin:
            return
        is_public = request.path.startswith(PUBLIC_PREFIXES) and request.method in ("GET", "HEAD", "OPTIONS")
        allowed = settings.API_CORS_ORIGINS
        if is_public:
            response["Access-Control-Allow-Origin"] = "*"
        elif "*" in allowed or origin in allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Vary"] = "Origin"
        else:
            return
        if request.method == "OPTIONS":
            response["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
            response["Access-Control-Allow-Headers"] = "Authorization, Content-Type"
            response["Access-Control-Max-Age"] = "600"
