import json

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import (
    HttpResponseBadRequest,
    HttpResponseForbidden,
    HttpResponseRedirect,
)
from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from icosa.helpers.moderation import (
    get_objects_to_moderate,
    get_str_content_type,
)
from icosa.model_mixins import (
    MOD_APPROVED,
    MOD_NEW,
    MOD_QUERIED,
    MOD_REJECTED,
)
from icosa.models import Asset, AssetCollection, AssetOwner
from icosa.models.moderation import ModerationEvent


@never_cache
@login_required
def moderation_queue(request):
    if not request.user.groups.filter(name="Moderator").exists():
        return HttpResponseForbidden()
    if request.method == "POST":
        obj_contenttype = request.POST.get("obj_contenttype")
        obj_id = request.POST.get("obj_id")
        if not obj_contenttype:
            return HttpResponseBadRequest("Missing contenttype")
        if obj_contenttype not in ["asset", "asset owner", "asset collection"]:
            return HttpResponseBadRequest(f"Invalid contenttype: {obj_contenttype}")
        if not obj_id:
            return HttpResponseBadRequest("Missing object id")

        # Get the object. TODO This could maybe be neater.
        obj = None
        if obj_contenttype == "asset":
            try:
                obj = Asset.objects.get(id=obj_id)
            except Asset.DoesNotExist:
                pass
        if obj_contenttype == "asset owner":
            try:
                obj = AssetOwner.objects.get(id=obj_id)
            except AssetOwner.DoesNotExist:
                pass
        if obj_contenttype == "asset collection":
            try:
                obj = AssetCollection.objects.get(id=obj_id)
            except AssetOwner.DoesNotExist:
                pass

        if obj is None:
            return HttpResponseBadRequest(
                f"Cannot find item to save for moderation. Type: {obj_contenttype}, ID: {obj_id}."
            )
        with transaction.atomic():
            if "_approve" in request.POST:
                obj.moderation_state = MOD_APPROVED
            elif "_reject" in request.POST:
                obj.moderation_state = MOD_REJECTED
            elif "_query" in request.POST:
                obj.moderation_state = MOD_QUERIED
            else:
                return HttpResponseBadRequest("Invalid moderation action")

            obj.moderation_state_change_by = request.user
            obj.moderation_state_change_time = timezone.now()
            obj.moderation_changed_fields = []

            obj.save(
                # `update_timestamps` is not strictly required given we are using
                # `bypass_custom_logic`, but making it explicit here.
                update_timestamps=False,
                bypass_custom_logic=True,
                bypass_moderation_logging=True,
            )

            ModerationEvent.objects.create(
                source_object=obj,
                state=obj.moderation_state,
                notes=request.POST.get("notes", None),
                user=request.user,
                data=json.loads(request.POST.get("data", "")),
            )

            return HttpResponseRedirect(reverse("icosa:moderation_queue"))

    template = "moderation/queue.html"
    objects_to_moderate = get_objects_to_moderate()
    obj = objects_to_moderate.fetch_one()

    content_type = get_str_content_type(obj)
    moderation_template = None
    if content_type is not None:
        moderation_template = f"moderation/moderate_{content_type.replace(' ', '')}.html"

    if obj is not None and obj.moderation_state == MOD_NEW and not obj.moderation_changed_fields:
        # This is likely because assets exist/have been imported outside the
        # moderation flow.
        obj.moderation_changed_fields = obj.moderation_watch_fields
        obj.save(bypass_custom_logic=True)

    changed_data = {}
    if obj is not None:
        for field in obj.moderation_changed_fields:
            if field in ["thumbnail", "preview_image", "image"]:
                name = ""
                field = getattr(obj, field)
                if field:
                    file = getattr(field, "file")
                    if file:
                        name = getattr(file, "name")
                changed_data[field] = name
            else:
                changed_data[field] = getattr(obj, field, "")

    context = {
        "objects_to_moderate": objects_to_moderate,
        "queue_length": objects_to_moderate.count(),
        "content_type": content_type,
        "obj": obj,
        "moderation_template": moderation_template,
        "is_moderating": True,  # XXX Currently forces viewer.html to load the experimental js.
        "changed_data": json.dumps(changed_data),
    }

    return render(
        request,
        template,
        context,
    )
