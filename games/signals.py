# games/signals.py

from django.db.models.signals import post_save, m2m_changed
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import UserGame, Badge, UserBadge, Profile, Notification, Comment


# 1. Logro BIENVENIDO (Al crear usuario)
@receiver(post_save, sender=User)
def grant_welcome_badge(sender, instance, created, **kwargs):
    if created:
        badge = Badge.objects.filter(slug="welcome").first()
        if badge:
            UserBadge.objects.create(user=instance, badge=badge)


# 2. Logro COLECCIONISTA y CRÍTICO (Al guardar un juego/review)
@receiver(post_save, sender=UserGame)
def check_game_badges(sender, instance, created, **kwargs):
    user = instance.user

    # Logro: Primer Juego
    if UserGame.objects.filter(user=user).count() >= 1:
        badge = Badge.objects.filter(slug="first-game").first()
        if badge and not UserBadge.objects.filter(user=user, badge=badge).exists():
            UserBadge.objects.create(user=user, badge=badge)

    # Logro: Crítico (Si tiene texto en review)
    if instance.review and len(instance.review) > 10:
        badge = Badge.objects.filter(slug="critic").first()
        if badge and not UserBadge.objects.filter(user=user, badge=badge).exists():
            UserBadge.objects.create(user=user, badge=badge)


# 3. Logro INFLUENCER (Cuando te siguen)
# Usamos m2m_changed porque los seguidores son ManyToMany
@receiver(m2m_changed, sender=Profile.follows.through)
def check_follow_badges(sender, instance, action, pk_set, **kwargs):
    # 'instance' es el perfil que ESTÁ SIGUIENDO a alguien.
    # Pero queremos premiar al que ES SEGUIDO.
    if action == "post_add":
        for target_profile_id in pk_set:  # IDs de a quienes has seguido
            target_profile = Profile.objects.get(pk=target_profile_id)
            target_user = target_profile.user

            # Si tiene al menos 1 seguidor
            if target_profile.followed_by.count() >= 1:
                badge = Badge.objects.filter(slug="social").first()
                if (
                    badge
                    and not UserBadge.objects.filter(
                        user=target_user, badge=badge
                    ).exists()
                ):
                    UserBadge.objects.create(user=target_user, badge=badge)


@receiver(post_save, sender=Comment)
def notify_comment(sender, instance, created, **kwargs):
    if created:
        # No notificarte si te comentas a ti mismo
        if instance.user != instance.user_game.user:
            Notification.objects.create(
                sender=instance.user,
                user=instance.user_game.user,  # El dueño de la review
                notification_type="comment",
                text_preview=instance.user_game.game.name[:30],  # Nombre del juego
                target_object_id=instance.user_game.game.igdb_id,
            )


# --- NOTIFICACIÓN: SEGUIR ---
@receiver(m2m_changed, sender=Profile.follows.through)
def notify_follow(sender, instance, action, pk_set, **kwargs):
    if action == "post_add":
        for target_id in pk_set:
            target_user = User.objects.get(
                pk=target_profile_id_to_user_id(target_id)
            )  # Helper necesario abajo
            # Creamos la notificación
            Notification.objects.create(
                sender=instance.user,  # El que sigue
                user=target_user,  # El seguido
                notification_type="follow",
                target_object_id=instance.user.id,  # ID del que sigue para ir a su perfil
            )


# Helper para obtener usuario desde perfil ID (necesario para el signal de follow)
def target_profile_id_to_user_id(profile_id):
    return Profile.objects.get(pk=profile_id).user.id
