import json

from django.contrib.auth.decorators import login_required
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
from icosa.models.moderation import ModerationEvent
from icosa.views.main import set_viewer_js_version


@never_cache
@login_required
def moderation_queue(request):
    if not request.user.groups.filter(name="Moderator").exists():
        return HttpResponseForbidden()

    template = "moderation/queue.html"

    set_viewer_js_version(request)

    objects_to_moderate = get_objects_to_moderate()

    current_obj = objects_to_moderate.fetch_one()

    if request.method == "POST":
        if current_obj is None:
            return HttpResponseBadRequest("No more objects to moderate")
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
        current_obj.moderation_changed_fields = []

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

    content_type = get_str_content_type(current_obj)
    moderation_template = None
    if content_type is not None:
        moderation_template = f"moderation/moderate_{content_type.replace(' ', '')}.html"

    if (
        current_obj is not None
        and current_obj.moderation_state == MOD_NEW
        and not current_obj.moderation_changed_fields
    ):
        # This is likely because assets exist/have been imported outside the
        # moderation flow.
        current_obj.moderation_changed_fields = current_obj.moderation_watch_fields
        current_obj.save(bypass_custom_logic=True)

    context = {
        "objects_to_moderate": objects_to_moderate,
        "queue_length": objects_to_moderate.count(),
        "content_type": content_type,
        "current_obj": current_obj,
        "moderation_template": moderation_template,
    }

    return render(
        request,
        template,
        context,
    )
