from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import HouseholdForm, LoginForm, RegisterForm
from .models import Household, Membership, PrivacyConsent


def home(request):
    if request.user.is_authenticated:
        return redirect("groups")
    return redirect("login")


def login_view(request):
    form = LoginForm(request.POST or None)
    error = None

    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].lower()
        password = form.cleaned_data["password"]
        user_record = User.objects.filter(email__iexact=email).first()
        user = authenticate(request, username=user_record.username, password=password) if user_record else None

        if user is not None:
            login(request, user)
            return redirect("groups")

        error = "El correo o la contraseña no son correctos."

    return render(request, "registration/login.html", {"form": form, "error": error})


def register(request):
    form = RegisterForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            email = form.cleaned_data["email"]
            user = User.objects.create_user(
                username=email,
                email=email,
                first_name=form.cleaned_data["name"],
                password=form.cleaned_data["password"],
            )
            PrivacyConsent.objects.create(user=user)

        login(request, user)
        messages.success(request, "Tu cuenta fue creada correctamente.")
        return redirect("groups")

    return render(request, "registration/register.html", {"form": form})


@login_required
@require_POST
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def groups(request):
    form = HouseholdForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            household = Household.objects.create(
                name=form.cleaned_data["name"],
                created_by=request.user,
            )
            Membership.objects.create(
                household=household,
                user=request.user,
                role=Membership.ADMIN,
            )

        messages.success(request, "El grupo fue creado correctamente.")
        return redirect("groups")

    memberships = Membership.objects.filter(
        user=request.user,
        is_active=True,
        household__is_active=True,
    ).select_related("household", "household__created_by")

    return render(request, "core/groups.html", {"form": form, "memberships": memberships})
