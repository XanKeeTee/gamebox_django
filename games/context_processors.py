def notifications_count(request):
    # Si el usuario no existe o no ha iniciado sesión, devolvemos 0
    if not request.user.is_authenticated:
        return {'notif_count': 0}

    # IMPORTANTE: El import DENTRO de la función
    from .models import Notification
    
    try:
        count = Notification.objects.filter(user=request.user, is_seen=False).count()
        return {'notif_count': count}
    except:
        return {'notif_count': 0}