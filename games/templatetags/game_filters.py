from django import template
import datetime

register = template.Library()

@register.filter
def unix_to_date(timestamp):
    if not timestamp:
        return "Desconocido"
    try:
        # Convierte los segundos en una fecha legible (ej: 15/04/2026)
        return datetime.datetime.fromtimestamp(timestamp).strftime('%d/%m/%Y')
    except:
        return "Desconocido"