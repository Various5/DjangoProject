from datetime import timedelta
from django import template

register = template.Library()

@register.filter
def add_hours(value, hours):
    """
    Addiert die angegebene Anzahl Stunden (als Zahl) zu einem datetime-Objekt.
    """
    try:
        return value + timedelta(hours=float(hours))
    except Exception:
        return value
