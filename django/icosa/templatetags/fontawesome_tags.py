from django import template
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def fa_icon(variant, name, extra_classes=None):
    if extra_classes is None:
        extra_classes = ""
    else:
        extra_classes = f" {extra_classes}"
    template = f"include/fontawesome-svgs/{variant}/{name}.svg"
    icon = render_to_string(template, {})

    return mark_safe(
        f"""<span class="fa-icon{extra_classes}">
{icon}
</span>"""
    )
