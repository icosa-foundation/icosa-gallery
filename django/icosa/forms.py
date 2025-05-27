from constance import config
from dal import autocomplete
from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, validate_slug
from django.forms.widgets import (
    ClearableFileInput,
    EmailInput,
    HiddenInput,
    PasswordInput,
)
from django.utils.translation import gettext_lazy as _
from icosa.helpers.file import validate_mime
from icosa.models import (
    PRIVATE,
    V3_CC_LICENSE_MAP,
    V3_CC_LICENSES,
    V4_CC_LICENSE_CHOICES,
    V4_CC_LICENSES,
    VALID_THUMBNAIL_MIME_TYPES,
    Asset,
    AssetOwner,
    User,
)

ARTIST_QUERY_SUBJECT_CHOICES = [
    ("WORK_REMOVED", "I want my work removed from this website"),
    ("EXISTING_ACCOUNT", "I want to tie my work to an existing account"),
    ("NEW_ACCOUNT", "I want to create an account based on my work"),
    ("CREDITED_TO_SOMEONE_ELSE", "My work is credited to someone else"),
]


class CustomImageInput(ClearableFileInput):
    clear_checkbox_label = _("Remove")
    initial_text = _("Currently")
    input_text = _("New thumbnail")
    template_name = "widgets/custom_clearable_image_input.html"


class CameraButton(HiddenInput):
    input_type = "hidden"
    template_name = "widgets/camera_input.html"


class AssetUploadForm(forms.Form):
    file = forms.FileField(validators=[FileExtensionValidator(allowed_extensions=["zip", "glb"])])

    def clean(self):
        cleaned_data = super().clean()
        uploaded_file = cleaned_data.get("file")
        if uploaded_file:
            if not validate_mime(next(uploaded_file.chunks(chunk_size=2048)), ["application/zip", "model/gltf-binary"]):
                self.add_error("file", "File is not a zip archive or a glb.")


class AssetReportForm(forms.Form):
    asset_url = forms.CharField(widget=forms.widgets.HiddenInput())
    reason_for_reporting = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 4}),
        label="Your reason for reporting this work. (Maximum length is 1,000 characters)",
    )
    contact_email = forms.CharField(
        label="The email address you can be contacted at (optional)",
        required=False,
    )


class AssetPublishForm(forms.ModelForm):
    editable_fields = [
        "name",
    ]

    class Meta:
        model = Asset

        fields = [
            "name",
            "license",
        ]


class AssetEditForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.model_is_editable:
            del self.fields["zip_file"]
        self.fields["name"].required = True
        license_value = self["license"].value()

        self.fields["thumbnail_override"] = forms.BooleanField(required=False)

        #  CC licenses are non-revokable, but are upgradeable. If the license
        # is cc but not in our current menu of options, they can upgrade and so
        # should be able to choose a different one.
        self.fields["license"].disabled = self.instance.license in V4_CC_LICENSES and self.instance.visibility in [
            "PUBLIC",
            "UNLISTED",
        ]

        if self.instance.license in V3_CC_LICENSES and license_value not in V4_CC_LICENSES:
            self.fields["license"].choices = [
                ("CREATIVE_COMMONS_BY_4_0", "CC BY Attribution 4.0 International"),
            ] + [
                (license_value, V3_CC_LICENSE_MAP[license_value]),
            ]
        else:
            self.fields["license"].choices = (
                [
                    ("", "No license chosen"),
                ]
                + V4_CC_LICENSE_CHOICES
                + [
                    ("ALL_RIGHTS_RESERVED", "All rights reserved"),
                ]
            )

    def clean(self):
        cleaned_data = super().clean()
        license = cleaned_data.get("license")
        if self.instance.visibility in ["PUBLIC", "UNLISTED"] and not license:
            self.add_error("license", "Please add a CC License.")
        if not self.instance.model_is_editable and self.instance.visibility == PRIVATE:
            self.add_error(
                "visibility",
                "You cannot make this model private because you have published this work under a CC license.",
            )

        for field in self.fields:
            if not self.instance.model_is_editable and field not in self.editable_fields and field in self.changed_data:
                self.add_error(
                    field,
                    "You cannot modify this field because this work is not private and has a CC license.",
                )
        thumbnail = cleaned_data.get("thumbnail")
        if thumbnail:
            if not validate_mime(next(thumbnail.chunks(chunk_size=2048)), VALID_THUMBNAIL_MIME_TYPES):
                self.add_error("thumbnail", "Image is not a png or jpg.")
        zip_file = cleaned_data.get("zip_file")
        if zip_file:
            if not validate_mime(next(zip_file.chunks(chunk_size=2048)), ["application/zip"]):
                self.add_error("zip_file", "File is not a zip archive.")

    thumbnail = forms.FileField(
        required=False, widget=CustomImageInput
    )  # No validator needed here; it's on the model field definition.
    zip_file = forms.FileField(required=False, validators=[FileExtensionValidator(allowed_extensions=["zip"])])

    editable_fields = [
        "name",
        "description",
        "thumbnail",
        "thumbnail_override",
        "thumbnail_override_data",
        "camera",
        "category",
        "tags",
    ]

    class Meta:
        model = Asset

        fields = [
            "name",
            "description",
            "license",
            "thumbnail",
            "category",
            "tags",
            "camera",
            "zip_file",
        ]
        widgets = {
            "tags": autocomplete.ModelSelect2Multiple(
                url="icosa:tag-autocomplete",
            ),
            "camera": CameraButton(),
        }


class UserSettingsForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email_confirm"] = forms.CharField(required=False, widget=EmailInput)
        if self.instance.has_single_owner:
            owner = self.instance.assetowner_set.first()
            self.fields["description"] = forms.CharField(required=False, widget=forms.Textarea)
            self.fields["description"].initial = owner.description
            self.fields["url"] = forms.CharField(required=False)
            self.fields["url"].initial = owner.url
        self.fields["password_current"] = forms.CharField(required=False, widget=PasswordInput)
        self.fields["password_new"] = forms.CharField(
            required=False, widget=PasswordInput, validators=[validate_password]
        )
        self.fields["password_confirm"] = forms.CharField(required=False, widget=PasswordInput)

    def clean(self):
        cleaned_data = super().clean()

        password_current = cleaned_data.get("password_current")
        password_new = cleaned_data.get("password_new")
        password_confirm = cleaned_data.get("password_confirm")
        email = cleaned_data.get("email")
        email_confirm = cleaned_data.get("email_confirm")
        url = cleaned_data.get("url")

        if not self.instance.check_password(password_current):
            self.add_error("password_current", "You must enter your password to make changes")

        if (password_new or password_confirm) and password_new != password_confirm:
            msg = "Passwords must match"
            self.add_error("password_new", msg)
            self.add_error("password_confirm", msg)

        if (password_new or password_confirm) and not password_current:
            msg = "Please enter your current password"
            self.add_error("password_current", msg)

        if password_new and password_confirm and password_current:
            msg = "Your current password is incorrect"
            try:
                if not self.instance.check_password(password_current):
                    self.add_error("password_current", msg)
            except AttributeError:
                self.add_error("password_current", msg)

        if email and email != self.instance.email:
            if email != email_confirm:
                msg = "Email addresses must match"
                self.add_error("email", msg)
                self.add_error("email_confirm", msg)
            else:
                if User.objects.filter(email=email_confirm).exists():
                    msg = "Cannot use this email address, please try another"
                    self.add_error("email", msg)
                    self.add_error("email_confirm", msg)
        if self.instance.has_single_owner:
            owner = self.instance.assetowner_set.first()
            if url:
                try:
                    validate_slug(url)
                except ValidationError:
                    msg = "Enter a valid url consisting of letters, numbers, underscores or hyphens."
                    self.add_error("url", msg)
                # TODO(performance) This is to simulate saving the asset owner
                # and returning errors from the db to the form. There must be a
                # better way.
                is_not_unique = AssetOwner.objects.filter(url=url).exclude(pk=owner.pk).exists()
                if is_not_unique:
                    msg = "That url is already taken. Please choose another."
                    self.add_error("url", msg)

    class Meta:
        model = User

        fields = [
            "displayname",
            "email",
        ]


class NewUserForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password_new"] = forms.CharField(
            required=True, widget=PasswordInput, validators=[validate_password]
        )
        self.fields["password_confirm"] = forms.CharField(required=False, widget=PasswordInput)

    def clean(self):
        cleaned_data = super().clean()

        email = self.cleaned_data.get("email")
        if config.REGISTRATION_ALLOW_LIST and email not in [
            x.strip() for x in config.REGISTRATION_ALLOW_LIST.split(",")
        ]:
            msg = "New registrations are currently by invitation only. It looks like that email address is not on the invitation list."
            self.add_error("email", msg)

        password_new = cleaned_data.get("password_new")
        password_confirm = cleaned_data.get("password_confirm")

        if (password_new or password_confirm) and password_new != password_confirm:
            msg = "Passwords must match"
            self.add_error("password_new", msg)
            self.add_error("password_confirm", msg)

    class Meta:
        model = User

        fields = [
            "email",
            "displayname",
            "username",
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
            required=True, widget=PasswordInput, validators=[validate_password]
        )
        self.fields["password_confirm"] = forms.CharField(required=False, widget=PasswordInput)

    def clean(self):
        cleaned_data = super().clean()

        password_new = cleaned_data.get("password_new")
        password_confirm = cleaned_data.get("password_confirm")

        if (password_new or password_confirm) and password_new != password_confirm:
            msg = "Passwords must match"
            self.add_error("password_new", msg)
            self.add_error("password_confirm", msg)

    class Meta:
        model = User
        fields = []


class ArtistQueryForm(forms.Form):
    subject = forms.ChoiceField(
        choices=ARTIST_QUERY_SUBJECT_CHOICES,
        widget=forms.widgets.HiddenInput(),
        required=True,
    )
    message = forms.CharField(
        widget=forms.widgets.Textarea(),
        required=True,
    )
    contact_email = forms.EmailField(
        widget=forms.TextInput(),
        required=True,
    )
