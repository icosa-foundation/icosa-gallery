from django import template

register = template.Library()


@register.simple_tag
def get_custom_elided_page_range(p, number, on_each_side=2, on_ends=2):
    return p.get_elided_page_range(
        number=number, on_each_side=on_each_side, on_ends=on_ends
    )


@register.simple_tag(takes_context=True)
def clean_url(context):
    request = context["request"]
    return request.build_absolute_uri(request.path)
