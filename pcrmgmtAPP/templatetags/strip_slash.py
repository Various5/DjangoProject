# pcrmgmtAPP/templatetags/strip_slash.py

from django import template

register = template.Library()

@register.filter
def strip_slash(value):
    if isinstance(value, str):
        return value.rstrip('/')
    return value
