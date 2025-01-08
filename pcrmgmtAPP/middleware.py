from django.db.utils import OperationalError
from django.shortcuts import render

class DatabaseErrorMiddleware:
    """
    Middleware to catch database-related errors and render a fallback page.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        except OperationalError:
            return render(request, 'fallback.html', status=503)
