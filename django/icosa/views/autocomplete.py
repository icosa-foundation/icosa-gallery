from dal import autocomplete

from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from icosa.models import Asset, AssetOwner, Tag


@method_decorator(never_cache, name="dispatch")
class TagAutocomplete(autocomplete.Select2QuerySetView):
    def create_object(self, text):
        name = text.strip()

        tag, created = Tag.objects.get_or_create(name=name)

        return tag

    def get_queryset(self):
        user = self.request.user
        owner = None
        no_tags = Tag.objects.none()

        if user.is_anonymous:
            return no_tags

        if user.is_superuser:
            qs = Tag.objects.all()
        else:
            try:
                owner = AssetOwner.objects.get(django_user=user)
            except AssetOwner.DoesNotExist:
                return no_tags

            asset_tags = list(
                set(
                    Asset.objects.filter(owner=owner).values_list(
                        "tags",
                        flat=True,
                    )
                )
            )

            if not asset_tags:
                return no_tags

            qs = Tag.objects.filter(pk__in=asset_tags)
        if self.q:
            qs = qs.filter(name__istartswith=self.q)
        return qs
