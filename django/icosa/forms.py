from icosa.models import User

from django import forms
from django.forms.widgets import EmailInput, PasswordInput


class UserSettingsForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user")
        super().__init__(*args, **kwargs)
        self.fields["email_confirm"] = forms.CharField(
            required=False, widget=EmailInput
        )
        self.fields["password_current"] = forms.CharField(
            required=False, widget=PasswordInput
        )
        self.fields["password_new"] = forms.CharField(
            required=False, widget=PasswordInput
        )
        self.fields["password_confirm"] = forms.CharField(
            required=False, widget=PasswordInput
        )

    def clean(self):
        cleaned_data = super().clean()
        user = self.user

        password_current = cleaned_data.get("password_current")
        password_new = cleaned_data.get("password_new")
        password_confirm = cleaned_data.get("password_confirm")
        email = cleaned_data.get("email")
        email_confirm = cleaned_data.get("email_confirm")

        if (
            password_new or password_confirm
        ) and password_new != password_confirm:
            msg = "Passwords must match"
            self.add_error("password_new", msg)
            self.add_error("password_confirm", msg)

        if (password_new or password_confirm) and not password_current:
            msg = "Please enter your current password"
            self.add_error("password_current", msg)

        if password_new and password_confirm and password_current:
            msg = "Your current password is incorrect"
            try:
                if not user.check_password(password_current):
                    self.add_error("password_current", msg)
            except AttributeError:
                self.add_error("password_current", msg)

        if email and email != user.email:
            if email != email_confirm:
                msg = "Email addresses must match"
                self.add_error("email", msg)
                self.add_error("email_confirm", msg)

    class Meta:
        model = User

        fields = [
            "url",
            "displayname",
            "description",
            "email",
        ]
