from django.urls import path

from .views import (
    CustomLoginView,
    CustomLogoutView,
    invite_user,
    accept_invitation,
)

urlpatterns = [
    path("login/", CustomLoginView.as_view(), name="login"),
    path("logout/", CustomLogoutView.as_view(), name="logout"),
    path("users/invite/", invite_user, name="invite_user"),
    path("users/accept/<uuid:token>/", accept_invitation, name="accept_invitation"),
]