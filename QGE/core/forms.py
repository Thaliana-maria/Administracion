from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


class RegisterForm(forms.Form):
    name = forms.CharField(max_length=100, label="Nombre")
    email = forms.EmailField(label="Correo electrónico")
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput)
    confirm_password = forms.CharField(label="Confirmar contraseña", widget=forms.PasswordInput)
    privacy_accept = forms.BooleanField(label="Autorizo el tratamiento de mis datos personales conforme a la Ley 1581 de 2012.")

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Este correo ya tiene una cuenta registrada.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error("confirm_password", "Las contraseñas no coinciden.")

        if password:
            try:
                validate_password(password)
            except ValidationError as error:
                self.add_error("password", error)

        return cleaned_data


class LoginForm(forms.Form):
    email = forms.EmailField(label="Correo electrónico")
    password = forms.CharField(label="Contraseña", widget=forms.PasswordInput)


class HouseholdForm(forms.Form):
    name = forms.CharField(max_length=100, label="Nombre del grupo")

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Escribe un nombre para el grupo.")
        return name


class ExpenseForm(forms.Form):
    description = forms.CharField(max_length=180, label="Descripción del ítem")
    amount = forms.DecimalField(min_value=0.01, max_digits=12, decimal_places=2, label="Valor")


class PaymentForm(forms.Form):
    payer = forms.ModelChoiceField(queryset=User.objects.none(), label="Quién paga")
    receiver = forms.ModelChoiceField(queryset=User.objects.none(), label="Quién recibe")
    amount = forms.DecimalField(min_value=0.01, max_digits=12, decimal_places=2, label="Valor pagado")
    note = forms.CharField(max_length=200, required=False, label="Nota")

    def __init__(self, *args, household=None, **kwargs):
        super().__init__(*args, **kwargs)
        if household:
            members = User.objects.filter(household_memberships__household=household, household_memberships__is_active=True).distinct()
            self.fields["payer"].queryset = members
            self.fields["receiver"].queryset = members
            for field in ("payer", "receiver"):
                self.fields[field].label_from_instance = lambda user: user.first_name or user.email or user.username

    def clean(self):
        data = super().clean()
        if data.get("payer") and data.get("payer") == data.get("receiver"):
            self.add_error("receiver", "El pagador y el receptor deben ser distintos.")
        return data
