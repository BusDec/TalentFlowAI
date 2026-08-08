"""Custom template filters for TalentFlow AI."""

from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Return dictionary[key] or None. Usage: {{ dict|get_item:"key" }}"""
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter
def score_class(score):
    """Return the CSS score class for a 0-100 score.

    >= 80 -> high (green), 50-79 -> mid (yellow), < 50 -> low (red).
    """
    try:
        score = int(score)
    except (TypeError, ValueError):
        return "low"
    if score >= 80:
        return "high"
    if score >= 50:
        return "mid"
    return "low"
