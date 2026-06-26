from django.shortcuts import redirect
from django.urls import reverse


class LoginRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        allowed_paths = [
            reverse("login"),
        ]

        if (
            request.path.startswith("/admin/")
            or request.path.startswith("/static/")
            or request.path.startswith("/users/accept/")
        ):
            return self.get_response(request)

        if request.path not in allowed_paths and not request.user.is_authenticated:
            return redirect("login")

        return self.get_response(request)