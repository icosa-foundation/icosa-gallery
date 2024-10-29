from icosa.models import (
    LICENSE_CHOICES,
    V3_CC_LICENSE_CHOICES,
    V4_CC_LICENSE_CHOICES,
    Asset,
    User,
)

from django import forms
from django.forms.widgets import ClearableFileInput, EmailInput, PasswordInput
from django.utils.translation import gettext_lazy as _


class CustomImageInput(ClearableFileInput):
    clear_checkbox_label = _("Remove")
    initial_text = _("Currently")
    input_text = _("New thumbnail")
    template_name = "widgets/custom_clearable_image_input.html"


class AssetUploadForm(forms.Form):
    file = forms.FileField()
    license = forms.ChoiceField(choices=LICENSE_CHOICES)


class AssetSettingsForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        license_value = self["license"].value()
        V3_CC_LICENSES = [x[0] for x in V3_CC_LICENSE_CHOICES]
        V4_CC_LICENSES = [x[0] for x in V4_CC_LICENSE_CHOICES]
        V3_CC_LICENSE_MAP = {x[0]: x[1] for x in V3_CC_LICENSE_CHOICES}
        V4_CC_LICENSE_MAP = {x[0]: x[1] for x in V4_CC_LICENSE_CHOICES}
        V3_TO_V4_UPGRADE_MAP = {
            x[0]: x[1] for x in zip(V3_CC_LICENSES, V4_CC_LICENSES)
        }

        #  CC licenses are non-revokable, but are upgradeable. If the license
        # is cc but not in our current menu of options, they can upgrade and so
        # should be able to choose a different one.
        self.fields["license"].disabled = (
            self.instance.license in V4_CC_LICENSES
        )

        if (
            self.instance.license in V3_CC_LICENSES
            and license_value not in V4_CC_LICENSES
        ):
            upgrade_option = V3_TO_V4_UPGRADE_MAP[license_value]
            self.fields["license"].choices = [
                (upgrade_option, V4_CC_LICENSE_MAP[upgrade_option]),
            ] + [
                (license_value, V3_CC_LICENSE_MAP[license_value]),
            ]

    def clean(self):
        cleaned_data = super().clean()
        license = cleaned_data.get("license")
        visibility = cleaned_data.get("visibility")
        if visibility in ["PUBLIC", "UNLISTED"] and not license:
            self.add_error("license", "Please add a CC License.")

    thumbnail = forms.FileField(required=False, widget=CustomImageInput)

    class Meta:
        model = Asset

        fields = [
            "name",
            "description",
            "visibility",
            "license",
            "thumbnail",
        ]


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


class NewUserForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password_new"] = forms.CharField(
            required=True, widget=PasswordInput
        )
        self.fields["password_confirm"] = forms.CharField(
            required=False, widget=PasswordInput
        )

    def clean(self):
        cleaned_data = super().clean()

        password_new = cleaned_data.get("password_new")
        password_confirm = cleaned_data.get("password_confirm")

        if (
            password_new or password_confirm
        ) and password_new != password_confirm:
            msg = "Passwords must match"
            self.add_error("password_new", msg)
            self.add_error("password_confirm", msg)

    class Meta:
        model = User

        fields = [
            "url",
            "displayname",
            "email",
        ]


class PasswordResetForm(forms.ModelForm):
    class Meta:
        model = User

        fields = [
            "email",
        ]


class PasswordResetConfirmForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password_new"] = forms.CharField(
            required=True, widget=PasswordInput
        )
        self.fields["password_confirm"] = forms.CharField(
            required=False, widget=PasswordInput
        )

    def clean(self):
        cleaned_data = super().clean()

        password_new = cleaned_data.get("password_new")
        password_confirm = cleaned_data.get("password_confirm")

        if (
            password_new or password_confirm
        ) and password_new != password_confirm:
            msg = "Passwords must match"
            self.add_error("password_new", msg)
            self.add_error("password_confirm", msg)

    class Meta:
        model = User
        fields = []
