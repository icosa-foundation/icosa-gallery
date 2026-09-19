from django import template
from django.utils.safestring import mark_safe
from markdown_it import MarkdownIt

register = template.Library()

markdown_renderer = MarkdownIt("js-default")


@register.filter(name="markdown")
def render_markdown(value):
    return mark_safe(markdown_renderer.render(value or ""))
