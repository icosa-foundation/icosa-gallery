from django import template

register = template.Library()


@register.filter(name="get_attr")
def get_attr(obj, field_name):
    if isinstance(obj, dict):
        return obj.get(field_name)
    return getattr(obj, field_name)
