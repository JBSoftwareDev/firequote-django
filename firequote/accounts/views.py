from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User, Group
from django.contrib.auth.views import LoginView, LogoutView
from django.core.mail import send_mail
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from .forms import InvitationForm, AcceptInvitationForm
from .models import UserInvitation


class CustomLoginView(LoginView):
    template_name = "accounts/login.html"


class CustomLogoutView(LogoutView):
    pass


def can_invite_users(user):
    return user.is_authenticated and (
        user.is_superuser or user.groups.filter(name="User Managers").exists()
    )


@login_required
@user_passes_test(can_invite_users)
def invite_user(request):
    if request.method == "POST":
        form = InvitationForm(request.POST)

        if form.is_valid():
            invitation = UserInvitation.objects.create(
                email=form.cleaned_data["email"],
                invited_by=request.user,
            )

            invite_url = request.build_absolute_uri(
                reverse("accept_invitation", args=[invitation.token])
            )

            send_mail(
                subject="Acceso a FireQuote",
                message=f"Crea tu cuenta de FireQuote aquí:\n\n{invite_url}",
                from_email=None,
                recipient_list=[invitation.email],
                fail_silently=False,
            )

            messages.success(request, "Correo enviado.")
            return redirect("invite_user")
    else:
        form = InvitationForm()

    return render(request, "accounts/invite_user.html", {"form": form})


def accept_invitation(request, token):
    invitation = get_object_or_404(UserInvitation, token=token, is_used=False)

    if request.method == "POST":
        form = AcceptInvitationForm(request.POST)

        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                email=invitation.email,
                password=form.cleaned_data["password"],
            )

            invitation.is_used = True
            invitation.used_at = timezone.now()
            invitation.save()

            messages.success(request, "Cuenta creada. Inicia sesión.")
            return redirect("login")
    else:
        form = AcceptInvitationForm()

    return render(
        request,
        "accounts/accept_invitation.html",
        {
            "form": form,
            "invitation": invitation,
        },
    )