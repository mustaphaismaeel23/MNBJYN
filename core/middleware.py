class NoStoreHTMLMiddleware:
    """Never let a browser or CDN keep an old copy of a page.

    Without this, changes made in /admin could look 'not applied' because an
    older copy of the page was served from a cache.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if "text/html" in response.get("Content-Type", "") and "Cache-Control" not in response:
            response["Cache-Control"] = "no-store, max-age=0"
        return response
