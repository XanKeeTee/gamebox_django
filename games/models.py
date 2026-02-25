from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils.text import slugify

class Game(models.Model):
    igdb_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    cover_url = models.URLField(null=True, blank=True)
    url = models.URLField(null=True, blank=True)  # Campo para la URL del vídeo

    def __str__(self):
        return self.name
    
    @property
    def embed_link(self):
        """
        Transforma cualquier enlace de YouTube (normal o corto) en un enlace 'embed' válido.
        Elimina parámetros extra como &t= o &feature=.
        """
        if not self.url:
            return ""
            
        # Si la URL tiene 'v=', coge lo que hay justo después hasta el próximo '&'
        if 'v=' in self.url:
            try:
                return 'https://www.youtube.com/embed/' + self.url.split('v=')[1].split('&')[0]
            except IndexError:
                return self.url  # Si falla el split, devuelve la original por seguridad
        
        # Si es un enlace corto tipo youtu.be/CODIGO
        elif 'youtu.be' in self.url:
            try:
                return 'https://www.youtube.com/embed/' + self.url.split('/')[-1].split('?')[0]
            except IndexError:
                return self.url

        return self.url


class UserGame(models.Model):
    STATUS_CHOICES = [
        ("playing", "Jugando"),
        ("completed", "Completado"),
        ("backlog", "Pendiente"),
        ("dropped", "Abandonado"),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    rating = models.IntegerField(null=True, blank=True)
    review = models.TextField(blank=True, null=True)
    is_favorite = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    # Likes a la reseña
    likes = models.ManyToManyField(User, related_name="liked_reviews", blank=True)

    def total_likes(self):
        return self.likes.count()

    def __str__(self):
        return f"{self.user.username} - {self.game.name}"


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    bio = models.TextField(max_length=500, blank=True)
    location = models.CharField(max_length=30, blank=True)
    avatar = models.ImageField(upload_to="avatars/", null=True, blank=True)
    banner = models.ImageField(upload_to="banners/", null=True, blank=True)

    follows = models.ManyToManyField(
        "self", related_name="followed_by", symmetrical=False, blank=True
    )

    def __str__(self):
        return f"{self.user.username} Profile"

# Señales para crear perfil automáticamente al crear usuario
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()


class Comment(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    user_game = models.ForeignKey(
        UserGame, related_name="comments", on_delete=models.CASCADE
    )
    text = models.TextField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comentario de {self.user.username}"


class GameList(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="lists")
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    slug = models.SlugField(blank=True, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    likes = models.ManyToManyField(User, related_name="liked_lists", blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while GameList.objects.filter(slug=slug).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name


class ListEntry(models.Model):
    game_list = models.ForeignKey(
        GameList, on_delete=models.CASCADE, related_name="entries"
    )
    game = models.ForeignKey(Game, on_delete=models.CASCADE)
    order = models.PositiveIntegerField(default=0)
    comment = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["order"]


class Badge(models.Model):
    name = models.CharField(max_length=50)
    description = models.TextField()
    slug = models.SlugField(unique=True)
    icon_name = models.CharField(max_length=50, default="star")
    color = models.CharField(max_length=20, default="yellow")

    def __str__(self):
        return self.name


class UserBadge(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="badges")
    badge = models.ForeignKey(Badge, on_delete=models.CASCADE)
    earned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "badge")


class Notification(models.Model):
    TYPE_CHOICES = (
        ("like", "Me Gusta"),
        ("comment", "Comentario"),
        ("follow", "Nuevo Seguidor"),
    )

    sender = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="sent_notifications"
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="notifications"
    )
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    text_preview = models.CharField(max_length=100, blank=True)
    date = models.DateTimeField(auto_now_add=True)
    is_seen = models.BooleanField(default=False)

    target_object_id = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.sender} -> {self.user} ({self.notification_type})"