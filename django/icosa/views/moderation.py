import json

from django.contrib.auth.decorators import user_passes_test
from django.contrib.contenttypes.models import ContentType
from django.http import (
    Http404,
    HttpResponseBadRequest,
    HttpResponseRedirect,
)
from django.shortcuts import (
    get_object_or_404,
    render,
)
from django.urls import reverse
from django.utils import timezone
from icosa.models import (
    Asset,
    AssetCollection,
    AssetOwner,
)
from icosa.models.common import (
    MOD_APPROVED,
    MOD_MODIFIED,
    MOD_NEW,
    MOD_QUERIED,
    MOD_REJECTED,
    MOD_REPORTED,
)
from icosa.models.moderation import ModerationEvent

MOD_STATES_OF_INTEREST = [MOD_MODIFIED, MOD_NEW, MOD_REPORTED]


def get_str_content_type(obj):
    return str(ContentType.objects.get_for_model(obj)).split("|")[-1].strip()


@user_passes_test(lambda u: u.is_superuser)  # TODO, change to test for moderator group
def moderation_queue(request):
    template = "moderation/queue.html"
    content_type = request.GET.get("ct", None)
    object_id = request.GET.get("id", None)
    current_obj = None

    objects_to_moderate = []
    assets_to_moderate = Asset.objects.filter(moderation_state__in=MOD_STATES_OF_INTEREST).order_by("-create_time")
    objects_to_moderate = list(assets_to_moderate)

    if len(objects_to_moderate) == 0:
        context = {
            "objects_to_moderate": objects_to_moderate,
            "content_type": None,
            "current_obj": None,
            "moderation_template": None,
        }

        return render(
            request,
            template,
            context,
        )

    if content_type is None or object_id is None:
        try:
            current_obj = objects_to_moderate[0]
        except IndexError:
            raise Http404
        content_type = get_str_content_type(current_obj)
    else:
        if content_type == "asset":
            model = Asset
        elif content_type == "assetcollection":
            model = AssetCollection
        elif content_type == "assetowner":
            model = AssetOwner
        else:
            raise Http404

        current_obj = get_object_or_404(model, id=object_id, moderation_state__in=MOD_STATES_OF_INTEREST)

    if request.method == "POST":
        if "_approve" in request.POST:
            current_obj.moderation_state = MOD_APPROVED
        elif "_reject" in request.POST:
            current_obj.moderation_state = MOD_REJECTED
        elif "_query" in request.POST:
            current_obj.moderation_state = MOD_QUERIED
        else:
            return HttpResponseBadRequest("Invalid moderation action")

        current_obj.moderation_state_change_by = request.user
        current_obj.moderation_state_change_time = timezone.now()
        current_obj.moderation_changed_fields = None

        current_obj.save(
            # `update_timestamps` is not strictly required given we are using
            # `bypass_custom_logic`, but making it explicit here.
            update_timestamps=False,
            bypass_custom_logic=True,
            bypass_moderation_logging=True,
        )

        ModerationEvent.objects.create(
            source_object=current_obj,
            state=current_obj.moderation_state,
            notes=request.POST.get("notes", None),
            user=request.user,
            data=json.loads(request.POST.get("data", "")),
        )

        return HttpResponseRedirect(reverse("icosa:moderation_queue"))

    moderation_template = f"moderation/moderate_{content_type}.html"

    context = {
        "objects_to_moderate": objects_to_moderate,
        "queue_length": len(objects_to_moderate),
        "content_type": content_type,
        "current_obj": current_obj,
        "moderation_template": moderation_template,
    }

    return render(
        request,
        template,
        context,
    )
