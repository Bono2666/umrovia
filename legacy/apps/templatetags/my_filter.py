import os

from django import template


register = template.Library()


@register.filter
def get_item(dictionary, key):
    """Get item from dictionary by key."""
    if isinstance(dictionary, dict):
        return dictionary.get(key, {})
    return {}


@register.filter
def filename(value):
    return os.path.basename(value.file.name)


@register.filter
def to_space(value):
    return value.replace('%20', ' ').replace('25', '')


@register.filter
def split(value, delimiter=','):
    """Split a string by delimiter."""
    return [item.strip() for item in value.split(delimiter)]


@register.filter
def day_name(day_code):
    """Convert day code to day name."""
    day_map = {
        'MON': 'Senin',
        'TUE': 'Selasa',
        'WED': 'Rabu',
        'THU': 'Kamis',
        'FRI': 'Jumat',
        'SAT': 'Sabtu',
        'SUN': 'Ahad',
    }
    return day_map.get(day_code, day_code)


@register.filter
def color_by_group(value):
    """Map subject group code to a pastel background color for schedule display."""
    color_map = {
        'MTK': '#e3f2fd',   # Matematika - light blue
        'IPA': '#e8f5e9',   # IPA - light green
        'IPS': '#fff3e0',   # IPS - light orange
        'BHS': '#f3e5f5',   # Bahasa - light purple
        'AGM': '#e0f7fa',   # Agama - light cyan
        'PJOK': '#fce4ec',  # PJOK - light pink
        'TIK': '#f1f8e9',   # TIK - light lime
        'SBY': '#fff8e1',   # Seni Budaya - light yellow
        'BDD': '#efebe9',   # Bimbingan - light brown
        'AKL': '#e8eaf6',   # Akuntansi - light indigo
    }
    # Fallback colors for unknown groups
    fallback_colors = ['#e3f2fd', '#e8f5e9', '#fff3e0', '#f3e5f5', '#e0f7fa',
                       '#fce4ec', '#f1f8e9', '#fff8e1', '#efebe9', '#e8eaf6']

    if not value:
        return '#f5f5f5'  # Default gray if empty

    code = str(value).strip().upper()

    # Try exact match first
    if code in color_map:
        return color_map[code]

    # Try partial match (e.g., "MTK01" matches "MTK")
    for key in color_map:
        if key in code:
            return color_map[key]

    # Use hash for consistent fallback color
    index = hash(code) % len(fallback_colors)
    return fallback_colors[index]


@register.filter
def js_num(value):
    """Convert number to JS-safe string with dot decimal separator."""
    try:
        return str(float(value)).replace(',', '.')
    except (ValueError, TypeError):
        return '0'
