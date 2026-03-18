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

@register.filter(name='replace')
def replace(value, arg):
    """
    Reemplaza una cadena de texto por otra. 
    Uso en HTML: {{ texto|replace:"buscar,reemplazar" }}
    """
    if not value or isinstance(value, str) is False:
        return value
        
    try:
        buscar, reemplazar = arg.split(',')
        return value.replace(buscar, reemplazar)
    except ValueError:
        return value