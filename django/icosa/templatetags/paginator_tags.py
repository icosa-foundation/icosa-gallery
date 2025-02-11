from django import template
from django.core.paginator import Paginator

register = template.Library()


@register.simple_tag
def get_custom_elided_page_range(p, number, on_each_side=2, on_ends=2):
    paginator = Paginator(p.object_list, p.per_page)
    return paginator.get_elided_page_range(
        number=number, on_each_side=on_each_side, on_ends=on_ends
    )
