from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .forms import HouseholdForm, LoginForm, RegisterForm, ExpenseForm, PaymentForm
from .models import Household, Membership, PrivacyConsent, Expense, Payment


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



def _household(request, pk):
    return get_object_or_404(Household, pk=pk, is_active=True, memberships__user=request.user, memberships__is_active=True)


def _balances(household):
    members = list(Membership.objects.filter(household=household, is_active=True).select_related("user"))
    total = household.expenses.aggregate(value=Sum("amount"))["value"] or Decimal("0")
    share = total / len(members) if members else Decimal("0")
    paid = {m.user_id: Decimal("0") for m in members}
    received = {m.user_id: Decimal("0") for m in members}
    for expense in household.expenses.all():
        if expense.created_by_id in paid:
            paid[expense.created_by_id] += expense.amount
    for payment in household.payments.all():
        paid[payment.payer_id] += payment.amount
        received[payment.receiver_id] += payment.amount
    return total, [{"user": m.user, "share": share, "paid": paid[m.user_id], "received": received[m.user_id], "balance": paid[m.user_id] - received[m.user_id] - share} for m in members]


@login_required
def dashboard(request, pk):
    household = _household(request, pk)
    total, balances = _balances(household)
    return render(request, "core/dashboard.html", {"household": household, "total": total, "balances": balances, "expenses": household.expenses.select_related("created_by")[:8], "payments": household.payments.count()})


@login_required
def expenses(request, pk):
    household = _household(request, pk)
    form = ExpenseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        Expense.objects.create(household=household, created_by=request.user, **form.cleaned_data)
        messages.success(request, "Ítem registrado correctamente.")
        return redirect("expenses", pk=pk)
    return render(request, "core/expenses.html", {"household": household, "form": form, "expenses": household.expenses.select_related("created_by")})


@login_required
def balances(request, pk):
    household = _household(request, pk)
    total, rows = _balances(household)
    return render(request, "core/balances.html", {"household": household, "total": total, "balances": rows})


@login_required
def payments(request, pk):
    household = _household(request, pk)
    form = PaymentForm(request.POST or None, household=household)
    if request.method == "POST" and form.is_valid():
        Payment.objects.create(household=household, **form.cleaned_data)
        messages.success(request, "Pago registrado correctamente.")
        return redirect("payments", pk=pk)
    return render(request, "core/payments.html", {"household": household, "form": form, "payments": household.payments.select_related("payer", "receiver")})
