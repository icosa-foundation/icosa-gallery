from django import template

register = template.Library()


@register.simple_tag
def get_custom_elided_page_range(p, number, on_each_side=2, on_ends=2):
    return p.get_elided_page_range(
        number=number, on_each_side=on_each_side, on_ends=on_ends
    )
