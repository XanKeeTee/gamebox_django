from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .services import IGDBService
from django.views.decorators.http import require_POST
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db.models import Q, Count
from .models import Game, UserGame, Profile, Comment, GameList, ListEntry
from .models import Game, UserGame, Profile, Comment, GameList, ListEntry, Notification
from .models import Game, UserGame, Profile, Comment, GameList, ListEntry
from django.http import HttpResponseNotFound, JsonResponse


def index(request):
    service = IGDBService()

    # 1. Cargar juegos Trending (Como siempre)
    trending_games = service.get_top_games()
    # (Limpieza de imágenes de trending...)
    for game in trending_games:
        if "cover" in game:
            game["cover"]["url"] = game["cover"]["url"].replace(
                "t_thumb", "t_cover_big"
            )

    # 2. Cargar FEED SOCIAL (Solo si estás logueado)
    feed_items = []
    if request.user.is_authenticated:
        # Obtener IDs de la gente a la que sigues
        following_ids = request.user.profile.follows.values_list("user__id", flat=True)

        # Traer sus actividades (UserGame) más recientes
        # select_related optimiza la carga de datos
        feed_items = (
            UserGame.objects.filter(user__id__in=following_ids)
            .exclude(status="backlog")
            .select_related("user__profile", "game")
            .prefetch_related("comments__user__profile", "likes")
            .order_by("-updated_at")[:20]
        )  # Limitamos a 20 posts

    return render(
        request, "games/index.html", {"games": trending_games, "feed_items": feed_items}
    )


def detail(request, game_id):
    service = IGDBService()
    game = service.get_game_detail(game_id)

    # Limpieza de imágenes (igual que antes)
    if game:
        if "cover" in game:
            game["cover"]["url"] = game["cover"]["url"].replace(
                "t_thumb", "t_cover_big"
            )
        if "screenshots" in game:
            for screen in game["screenshots"]:
                screen["url"] = screen["url"].replace("t_thumb", "t_screenshot_huge")

    # Datos del usuario actual (TU interacción)
    user_game = None
    user_game_status = None

    # --- NUEVO: RESEÑAS DE LA COMUNIDAD ---
    community_reviews = []

    # Buscamos si el juego existe en nuestra BD local
    local_game = Game.objects.filter(igdb_id=game_id).first()

    if local_game:
        # 1. Tu interacción personal
        if request.user.is_authenticated:
            user_game = UserGame.objects.filter(
                user=request.user, game=local_game
            ).first()
            if user_game:
                user_game_status = user_game.status

        # 2. Buscar reseñas de OTROS (excluyendo vacías)
        # select_related('user__profile') es vital para cargar los avatares rápido
        community_reviews = (
            UserGame.objects.filter(game=local_game)
            .exclude(review__exact="")
            .exclude(review__isnull=True)
            .select_related("user__profile")
            .order_by("-updated_at")
        )

    return render(
        request,
        "games/detail.html",
        {
            "game": game,
            "user_game_status": user_game_status,
            "user_game": user_game,
            "community_reviews": community_reviews,  # <--- Pasamos esto al HTML
        },
    )


# En games/views.py


@login_required(login_url="/admin/login/")
def add_to_library(request, game_id, status):
    # 1. Verificar si el juego ya existe en nuestra BD local (Igual que antes)
    game = Game.objects.filter(igdb_id=game_id).first()

    # Si no existe, lo traemos de la API (Igual que antes)
    if not game:
        service = IGDBService()
        game_data = service.get_game_detail(game_id)

        if game_data:
            cover_url = (
                game_data.get("cover", {})
                .get("url", "")
                .replace("t_thumb", "t_cover_big")
            )
            game = Game.objects.create(
                igdb_id=game_data["id"],
                name=game_data["name"],
                slug=game_data.get("slug", f"game-{game_id}"),
                cover_url=cover_url,
            )

    # 2. LÓGICA DE TOGGLE (Aquí está el cambio)
    if game:
        # Buscamos si ya tienes este juego en tu lista
        existing_entry = UserGame.objects.filter(user=request.user, game=game).first()

        if existing_entry:
            # CASO A: Si le das click al mismo botón que ya tenías marcado...
            if existing_entry.status == status:
                existing_entry.delete()  # ...¡Lo borramos! (Quitar like/estado)

            # CASO B: Si le das click a un botón distinto (ej: pasar de Backlog a Playing)...
            else:
                existing_entry.status = status  # ...Actualizamos el estado
                existing_entry.save()

        else:
            # CASO C: No lo tenías, así que lo creamos nuevo
            UserGame.objects.create(user=request.user, game=game, status=status)

    return redirect("detail", game_id=game_id)


# games/views.py


@login_required(login_url="login")
def profile(request):
    my_games = (
        UserGame.objects.filter(user=request.user)
        .select_related("game")
        .order_by("-updated_at")
    )
    my_lists = request.user.lists.all().order_by("-created_at")

    # --- LÓGICA DE ESTADÍSTICAS ---
    # 1. Contar estados para el gráfico de "Pastel"
    # Esto devuelve algo como: {'playing': 2, 'completed': 5, 'backlog': 10}
    status_counts = my_games.values("status").annotate(total=Count("status"))

    # Formateamos para pasar fácil al HTML
    status_data = {"playing": 0, "completed": 0, "backlog": 0, "dropped": 0}
    for item in status_counts:
        if item["status"] in status_data:
            status_data[item["status"]] = item["total"]

    # 2. Distribución de Notas (Histograma)
    # Agrupamos notas en rangos (1-20, 21-40, 41-60, 61-80, 81-100)
    ratings_distribution = [0, 0, 0, 0, 0]  # 5 grupos
    rated_games = my_games.filter(rating__isnull=False)

    for game in rated_games:
        score = game.rating
        if score <= 20:
            ratings_distribution[0] += 1
        elif score <= 40:
            ratings_distribution[1] += 1
        elif score <= 60:
            ratings_distribution[2] += 1
        elif score <= 80:
            ratings_distribution[3] += 1
        else:
            ratings_distribution[4] += 1

    context = {
        "playing": my_games.filter(status="playing"),
        "backlog": my_games.filter(status="backlog"),
        "completed": my_games.filter(status="completed"),
        "favorites": my_games.filter(is_favorite=True),
        "reviews": my_games.exclude(review__exact="").exclude(review__isnull=True),
        "lists": my_lists,
        "total_count": my_games.count(),
        "fav_count": my_games.filter(is_favorite=True).count(),
        # DATOS PARA GRÁFICOS
        "status_data": status_data,
        "ratings_distribution": ratings_distribution,
    }
    return render(request, "games/profile.html", context)


def search(request):
    query = request.GET.get("q")  # Capturamos lo que viene de la URL ?q=zelda
    games = []

    if query:
        service = IGDBService()
        games = service.search_games(query)

        # Limpieza de imágenes (igual que en el index)
        for game in games:
            if "cover" in game:
                game["cover"]["url"] = game["cover"]["url"].replace(
                    "t_thumb", "t_cover_big"
                )

    return render(
        request, "games/search_results.html", {"games": games, "query": query}
    )


@login_required(login_url="/admin/login/")
@require_POST  # Solo aceptamos envíos de formulario, no visitas directas
def update_review(request, game_id):
    # Buscamos el juego en local (ya debe existir porque primero lo añades a la librería)
    game = get_object_or_404(Game, igdb_id=game_id)

    # Buscamos o creamos la entrada del usuario
    user_game, created = UserGame.objects.get_or_create(
        user=request.user,
        game=game,
        defaults={"status": "playing"},  # Por defecto si no existía
    )

    # Capturamos los datos del formulario HTML
    review_text = request.POST.get("review")
    rating_val = request.POST.get("rating")
    is_fav = (
        request.POST.get("is_favorite") == "on"
    )  # Checkbox HTML envía 'on' si está marcado

    # Actualizamos
    user_game.review = review_text
    user_game.is_favorite = is_fav

    if rating_val:
        user_game.rating = int(rating_val)

    user_game.save()

    return redirect("detail", game_id=game_id)


@login_required(login_url="/admin/login/")
def edit_profile(request):
    if not hasattr(request.user, "profile"):
        Profile.objects.create(user=request.user)

    if request.method == "POST":
        u_form = UserUpdateForm(request.POST, instance=request.user)
        # IMPORTANTE: request.FILES es necesario para subir imágenes
        p_form = ProfileUpdateForm(
            request.POST, request.FILES, instance=request.user.profile
        )

        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            return redirect("profile")  # Redirige al perfil al terminar
    else:
        u_form = UserUpdateForm(instance=request.user)
        p_form = ProfileUpdateForm(instance=request.user.profile)

    context = {"u_form": u_form, "p_form": p_form}
    return render(request, "games/edit_profile.html", context)


def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Logueamos al usuario automáticamente tras registrarse
            login(request, user)
            return redirect("index")
    else:
        form = UserCreationForm()

    return render(request, "registration/register.html", {"form": form})


def public_profile(request, username):
    # Buscamos al usuario por su nombre
    profile_user = get_object_or_404(User, username=username)

    # Traemos sus juegos (Igual que en tu perfil, pero filtrando por ESE usuario)
    my_games = (
        UserGame.objects.filter(user=profile_user)
        .select_related("game")
        .order_by("-updated_at")
    )

    user_lists = profile_user.lists.all().order_by("-created_at")

    # Filtros
    playing = my_games.filter(status="playing")
    backlog = my_games.filter(status="backlog")
    completed = my_games.filter(status="completed")
    favorites = my_games.filter(is_favorite=True)
    reviews = my_games.exclude(review__exact="").exclude(review__isnull=True)

    # Comprobar si TÚ (el que mira) ya sigues a este usuario
    is_following = False
    if request.user.is_authenticated:
        if request.user.profile.follows.filter(id=profile_user.profile.id).exists():
            is_following = True

    context = {
        "profile_user": profile_user,
        "playing": my_games.filter(status="playing"),
        "backlog": my_games.filter(status="backlog"),
        "completed": my_games.filter(status="completed"),
        "favorites": my_games.filter(is_favorite=True),
        "reviews": my_games.exclude(review__exact="").exclude(review__isnull=True),
        "lists": user_lists,  # <--- AÑADIR ESTO
        "total_count": my_games.count(),
        "fav_count": my_games.filter(is_favorite=True).count(),
        "is_following": is_following,
        "followers_count": profile_user.profile.followed_by.count(),
        "following_count": profile_user.profile.follows.count(),
    }
    return render(request, "games/public_profile.html", context)


# --- ACCIÓN DE SEGUIR ---
@login_required(login_url="login")
def toggle_follow(request, username):
    target_user = get_object_or_404(User, username=username)
    my_profile = request.user.profile

    # No puedes seguirte a ti mismo
    if target_user != request.user:
        if my_profile.follows.filter(id=target_user.profile.id).exists():
            # Si ya lo sigo, lo borro (Unfollow)
            my_profile.follows.remove(target_user.profile)
        else:
            # Si no lo sigo, lo añado (Follow)
            my_profile.follows.add(target_user.profile)

    return redirect("public_profile", username=username)


def community(request):
    # 1. Buscar usuarios populares (ordenados por número de seguidores)
    # Annotate crea un campo "falso" temporal llamado num_followers para ordenar
    popular_users = User.objects.annotate(
        num_followers=Count("profile__followed_by")
    ).order_by("-num_followers")[
        :6
    ]  # Top 6

    # 2. Reseñas recientes globales (de cualquier usuario)
    recent_reviews = (
        UserGame.objects.exclude(review="")
        .exclude(review__isnull=True)
        .select_related("user__profile", "game")
        .prefetch_related("likes", "comments")
        .order_by("-updated_at")[:20]
    )

    return render(
        request,
        "games/community.html",
        {"popular_users": popular_users, "recent_reviews": recent_reviews},
    )


@login_required(login_url="login")
def toggle_like(request, review_id):
    review = get_object_or_404(UserGame, id=review_id)
    if request.user in review.likes.all():
        review.likes.remove(request.user)
    else:
        review.likes.add(request.user)
    # Redirigir a donde estabas (index o perfil)
    return redirect(request.META.get("HTTP_REFERER", "index"))


@login_required(login_url="login")
def add_comment(request, review_id):
    review = get_object_or_404(UserGame, id=review_id)
    if request.method == "POST":
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.user = request.user
            comment.user_game = review
            comment.save()
    return redirect(request.META.get("HTTP_REFERER", "index"))


@login_required(login_url="login")
def create_list(request):
    if request.method == "POST":
        form = GameListForm(request.POST)
        if form.is_valid():
            new_list = form.save(commit=False)
            new_list.user = request.user
            new_list.save()
            return redirect("profile")  # O redirigir a la lista creada
    else:
        form = GameListForm()
    return render(request, "games/create_list.html", {"form": form})


def list_detail(request, username, slug):
    # Buscamos la lista por usuario y slug
    game_list = get_object_or_404(GameList, user__username=username, slug=slug)
    return render(request, "games/list_detail.html", {"game_list": game_list})


@login_required(login_url="login")
def add_to_list_view(request, game_id):
    # 1. Intentamos buscar el juego en la base de datos local
    game = Game.objects.filter(igdb_id=game_id).first()

    # 2. Si NO existe en local, lo descargamos de la API de IGDB y lo creamos
    if not game:
        service = IGDBService()
        game_data = service.get_game_detail(game_id)

        if game_data:
            # Aseguramos la URL de la portada en alta calidad
            cover_url = (
                game_data.get("cover", {})
                .get("url", "")
                .replace("t_thumb", "t_cover_big")
            )

            game = Game.objects.create(
                igdb_id=game_data["id"],
                name=game_data["name"],
                slug=game_data.get("slug", f"game-{game_id}"),
                cover_url=cover_url,
            )
        else:
            # Si el juego no existe ni en la API, devolvemos error 404
            return HttpResponseNotFound("Juego no encontrado")

    # 3. Lógica original para guardar en la lista
    if request.method == "POST":
        list_id = request.POST.get("list_id")
        comment = request.POST.get("comment")

        # Aseguramos que la lista pertenezca al usuario
        target_list = get_object_or_404(GameList, id=list_id, user=request.user)

        # Evitar duplicados en la misma lista
        if not ListEntry.objects.filter(game_list=target_list, game=game).exists():
            ListEntry.objects.create(
                game_list=target_list,
                game=game,
                comment=comment,
                order=target_list.entries.count() + 1,
            )
        # Volver a la ficha del juego
        return redirect("detail", game_id=game_id)

    # GET: Mostrar formulario de selección
    my_lists = GameList.objects.filter(user=request.user)
    return render(
        request, "games/add_to_list.html", {"game": game, "my_lists": my_lists}
    )


@login_required(login_url="login")
def toggle_like(request, review_id):
    review = get_object_or_404(UserGame, id=review_id)

    liked = False
    if request.user in review.likes.all():
        review.likes.remove(request.user)
        liked = False
    else:
        review.likes.add(request.user)
        liked = True

    # Si la petición viene por AJAX (fetch), devolvemos JSON
    return JsonResponse({"liked": liked, "count": review.likes.count()})


@login_required(login_url="login")
def toggle_follow(request, username):
    target_user = get_object_or_404(User, username=username)
    my_profile = request.user.profile

    following = False
    if target_user != request.user:
        if my_profile.follows.filter(id=target_user.profile.id).exists():
            my_profile.follows.remove(target_user.profile)
            following = False
        else:
            my_profile.follows.add(target_user.profile)
            following = True

    return JsonResponse(
        {
            "following": following,
            "followers_count": target_user.profile.followed_by.count(),
        }
    )


@login_required(login_url="login")
def notifications_view(request):
    # Obtener todas ordenadas por fecha
    notifs = Notification.objects.filter(user=request.user).order_by("-date")

    # Marcar todas como vistas al entrar
    unseen = notifs.filter(is_seen=False)
    unseen.update(is_seen=True)

    return render(request, "games/notifications.html", {"notifs": notifs})


def releases(request):
    service = IGDBService()
    upcoming_games = service.get_upcoming_games()

    # Arreglamos las imágenes como siempre
    for game in upcoming_games:
        if "cover" in game:
            game["cover"]["url"] = game["cover"]["url"].replace(
                "t_thumb", "t_cover_big"
            )

    return render(request, "games/releases.html", {"games": upcoming_games})
