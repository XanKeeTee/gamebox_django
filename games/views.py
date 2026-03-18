import json

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from .services import IGDBService
from django.views.decorators.http import require_POST
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db.models import Q, Count
from .models import Game, UserGame, Profile, Comment, GameList, ListEntry, Notification
from django.http import HttpResponseNotFound, JsonResponse
from django.views.decorators.cache import cache_page
from django.contrib import messages
from .forms import GameListForm 
from .forms import GameListForm
from django.utils.text import slugify

@cache_page(60 * 15)
def index(request):
    service = IGDBService()
    
    trending_games = service.get_top_games()
    for game in trending_games:
        if 'cover' in game:
            game['cover']['url'] = game['cover']['url'].replace('t_thumb', 't_cover_big')

    upcoming_games = service.get_upcoming_games()[:10]
    for game in upcoming_games:
        if 'cover' in game:
            game['cover']['url'] = game['cover']['url'].replace('t_thumb', 't_cover_big')

    feed_items = []
    if request.user.is_authenticated:
        following_ids = request.user.profile.follows.values_list('user__id', flat=True)
        feed_items = UserGame.objects.filter(user__id__in=following_ids) \
            .exclude(status='backlog') \
            .select_related('user__profile', 'game') \
            .prefetch_related('comments__user__profile', 'likes') \
            .order_by('-updated_at')[:20]

    return render(request, 'games/home/index.html', {
        'hero_game': trending_games[0] if trending_games else None,
        'trending_games': trending_games[1:],
        'upcoming': upcoming_games,
        'feed_items': feed_items
    })


def detail(request, game_id):
    """
    Carga la ficha de un juego usando IGDBService y comprueba su estado local.
    """
    igdb = IGDBService()
    
    game = igdb.get_game_detail(game_id) 
    
    if not game:
        from django.http import Http404
        raise Http404("El juego no existe en la base de datos de IGDB")

    user_status = None
    user_review = ""

    if request.user.is_authenticated:
        interaccion = UserGame.objects.filter(
            user=request.user, 
            game__igdb_id=game_id
        ).first()

        if interaccion:
            user_status = interaccion.status
            user_review = interaccion.review

    context = {
        'game': game,
        'user_status': user_status,
        'user_review': user_review,
    }
    return render(request, 'games/catalog/detail.html', context)

@login_required(login_url="/admin/login/")
def add_to_library(request, game_id, status):
    game = Game.objects.filter(igdb_id=game_id).first()

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

    if game:
        existing_entry = UserGame.objects.filter(user=request.user, game=game).first()

        if existing_entry:
            if existing_entry.status == status:
                existing_entry.delete()

            else:
                existing_entry.status = status
                existing_entry.save()

        else:
            UserGame.objects.create(user=request.user, game=game, status=status)

    return redirect("detail", game_id=game_id)


@login_required
def profile(request):
    """Perfil privado con estadísticas y juegos reales"""
    user = request.user

    favorite_games = UserGame.objects.filter(user=user, is_favorite=True).select_related('game')
    backlog_games = UserGame.objects.filter(user=user, status='backlog').select_related('game')[:6]
    completed_games = UserGame.objects.filter(user=user, status='completed').select_related('game')[:6]

    count_playing = UserGame.objects.filter(user=user, status='playing').count()
    count_completed = UserGame.objects.filter(user=user, status='completed').count()
    count_backlog = UserGame.objects.filter(user=user, status='backlog').count()
    count_dropped = UserGame.objects.filter(user=user, status='dropped').count()
    
    dist_data = [count_playing, count_completed, count_backlog, count_dropped]

    ratings = []
    for i in range(1, 6):
        count = UserGame.objects.filter(user=user, rating=i).count()
        ratings.append(count)

    context = {
        'favorite_games': favorite_games,
        'backlog_games': backlog_games,
        'completed_games': completed_games,
        'total_count': UserGame.objects.filter(user=user).count(),
        'dist_data': json.dumps(dist_data),
        'rating_data': json.dumps(ratings),
        'rating_labels': json.dumps(['1★', '2★', '3★', '4★', '5★']),
    }
    
    return render(request, 'games/profile/profile.html', context)


def search(request):
    query = request.GET.get("q")
    games = []

    if query:
        service = IGDBService()
        games = service.search_games(query)

        for game in games:
            if "cover" in game:
                game["cover"]["url"] = game["cover"]["url"].replace(
                    "t_thumb", "t_cover_big"
                )

    return render(
        request, "games/catalog/search_results.html", {"games": games, "query": query}
    )


@login_required(login_url="/admin/login/")
@require_POST
def update_review(request, game_id):
    game = get_object_or_404(Game, igdb_id=game_id)

    user_game, created = UserGame.objects.get_or_create(
        user=request.user,
        game=game,
        defaults={"status": "playing"},
    )

    review_text = request.POST.get("review")
    rating_val = request.POST.get("rating")
    is_fav = (
        request.POST.get("is_favorite") == "on"
    )

    user_game.review = review_text
    user_game.is_favorite = is_fav

    if rating_val:
        user_game.rating = int(rating_val)

    user_game.save()

    return redirect("detail", game_id=game_id)


@login_required
def edit_profile(request):
    """Página para editar el perfil (avatar, bio, etc.)"""
    user = request.user
    
    if request.method == 'POST':
        user.first_name = request.POST.get('first_name', user.first_name)
        user.email = request.POST.get('email', user.email)
        user.save()
        
        profile = user.profile 
        
        if 'bio' in request.POST:
            profile.bio = request.POST.get('bio')
            
        if 'avatar' in request.FILES:
            profile.avatar = request.FILES['avatar']
        
        if 'banner' in request.FILES:
            profile.banner = request.FILES['banner']

        profile.save()
        
        messages.success(request, "¡Tu perfil se ha actualizado correctamente!")
        return redirect('profile') 

    return render(request, 'games/profile/edit_profile.html')

def register(request):
    if request.method == "POST":
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect("index")
    else:
        form = UserCreationForm()

    return render(request, "registration/register.html", {"form": form})


def public_profile(request, username):
    profile_user = get_object_or_404(User, username=username)

    my_games = (
        UserGame.objects.filter(user=profile_user)
        .select_related("game")
        .order_by("-updated_at")
    )

    user_lists = profile_user.lists.all().order_by("-created_at")

    playing = my_games.filter(status="playing")
    backlog = my_games.filter(status="backlog")
    completed = my_games.filter(status="completed")
    favorites = my_games.filter(is_favorite=True)
    reviews = my_games.exclude(review__exact="").exclude(review__isnull=True)
    usuario_visitado = get_object_or_404(User, username=username)

    # Comprobar si TÚ (el que mira) ya sigues a este usuario
    is_following = False
    if request.user.is_authenticated:
        if request.user.profile.follows.filter(id=profile_user.profile.id).exists():
            is_following = True

    context = {
        "profile_user": profile_user,
        "playing": my_games.filter(status="playing"),
        "backlog": my_games.filter(status="backlog"),
        'target_user': usuario_visitado,
        "completed": my_games.filter(status="completed"),
        "favorites": my_games.filter(is_favorite=True),
        "reviews": my_games.exclude(review__exact="").exclude(review__isnull=True),
        "lists": user_lists,
        "total_count": my_games.count(),
        "fav_count": my_games.filter(is_favorite=True).count(),
        "is_following": is_following,
        "followers_count": profile_user.profile.followed_by.count(),
        "following_count": profile_user.profile.follows.count(),
    }
    return render(request, "games/profile/public_profile.html", context)

def community(request):
    """
    Vista de la página de Comunidad.
    Carga el feed de actividad y los usuarios recomendados para seguir.
    """
    if request.user.is_authenticated:
        usuarios_sugeridos = User.objects.exclude(id=request.user.id).order_by('-date_joined')[:10]
    else:
        usuarios_sugeridos = User.objects.all().order_by('-date_joined')[:10]
    actividad_reciente = [] 

    context = {
        'usuarios_comunidad': usuarios_sugeridos,
        'actividades': actividad_reciente,
    }
    
    return render(request, 'games/community/community.html', context)

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
            return redirect("profile")
    else:
        form = GameListForm()
    return render(request, "games/lists/create_list.html", {"form": form})


def list_detail(request, username, slug):
    game_list = get_object_or_404(GameList, user__username=username, slug=slug)
    return render(request, "games/lists/list_detail.html", {"game_list": game_list})


@login_required(login_url="login")
def add_to_list_view(request, game_id):
    game = Game.objects.filter(igdb_id=game_id).first()

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
            return HttpResponseNotFound("Juego no encontrado")

    if request.method == "POST":
        list_id = request.POST.get("list_id")
        comment = request.POST.get("comment")

        target_list = get_object_or_404(GameList, id=list_id, user=request.user)

        if not ListEntry.objects.filter(game_list=target_list, game=game).exists():
            ListEntry.objects.create(
                game_list=target_list,
                game=game,
                comment=comment,
                order=target_list.entries.count() + 1,
            )
        return redirect("detail", game_id=game_id)

    my_lists = GameList.objects.filter(user=request.user)
    return render(
        request, "games/lists/add_to_list.html", {"game": game, "my_lists": my_lists}
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
    notifs = Notification.objects.filter(user=request.user).order_by("-date")

    unseen = notifs.filter(is_seen=False)
    unseen.update(is_seen=True)

    return render(request, "games/community/notifications.html", {"notifs": notifs})


def releases(request):
    service = IGDBService()
    upcoming_games = service.get_upcoming_games()

    for game in upcoming_games:
        if "cover" in game:
            game["cover"]["url"] = game["cover"]["url"].replace(
                "t_thumb", "t_cover_big"
            )

    return render(request, "games/home/releases.html", {"games": upcoming_games})

def category(request, genre_id):
    service = IGDBService()
    games = service.get_games_by_genre(genre_id)
    
    # Un pequeño diccionario para poner el título bonito
    genre_names = {
        12: "RPG (Rol)",
        5: "Shooter",
        31: "Aventura",
        32: "Indie",
        15: "Estrategia",
        14: "Deportes"
    }
    title = genre_names.get(genre_id, "Juegos")
    
    return render(request, 'games/home/category.html', {'games': games, 'title': title})

def advanced_search(request):
    platform = request.GET.get('platform')
    genre = request.GET.get('genre')
    year = request.GET.get('year')
    min_rating = request.GET.get('rating')
    
    games = []
    # Solo buscamos en la API si el usuario ha tocado algún filtro
    if platform or genre or year or min_rating:
        # Importamos el servicio si no estaba ya importado arriba
        from .services import IGDBService 
        service = IGDBService()
        games = service.advanced_search(platform, genre, year, min_rating)
        
    return render(request, 'games/catalog/advanced_search.html', {
        'games': games,
        'selected_platform': platform,
        'selected_genre': genre,
        'selected_year': year,
        'selected_rating': min_rating
    })

@login_required
def create_list(request):
    if request.method == 'POST':
        form = GameListForm(request.POST)
        if form.is_valid():
            # Guardamos la lista pero sin enviarla a la BD todavía
            game_list = form.save(commit=False)
            # Le asignamos el usuario logueado
            game_list.user = request.user
            # Ahora sí guardamos
            game_list.save()
            return redirect('profile') # O redirige a donde prefieras
    else:
        form = GameListForm()
    
    return render(request, 'games/create_list.html', {'form': form})

@login_required
def toggle_follow(request, username):
    """Vista asíncrona para seguir/dejar de seguir a un usuario"""
    if request.method == "POST":
        # Buscamos al usuario al que queremos seguir
        target_user = get_object_or_404(User, username=username)
        
        # No puedes seguirte a ti mismo
        if request.user == target_user:
            return JsonResponse({"error": "No puedes seguirte a ti mismo"}, status=400)

        mi_perfil = request.user.profile
        perfil_destino = target_user.profile

        if perfil_destino in mi_perfil.follows.all():
            mi_perfil.follows.remove(perfil_destino)
            is_following = False
        else:
            mi_perfil.follows.add(perfil_destino)
            is_following = True

        return JsonResponse({
            "is_following": is_following,
            "follower_count": perfil_destino.followed_by.count()
        })
        
    return JsonResponse({"error": "Método no permitido"}, status=400)

@login_required
def update_game_status(request, game_id):
    """Vista asíncrona para los botones de estado (Jugando, Completado, Backlog)"""
    if request.method == 'POST':
        data = json.loads(request.body)
        nuevo_estado = data.get('status')
        nombre_juego = data.get('name', 'Juego Desconocido')
        portada_url = data.get('cover_url', '')

        # Generamos un slug válido y único (ej: "gta-v-45131")
        slug_generado = slugify(f"{nombre_juego}-{game_id}")

        # Usamos exactamente TUS nombres de campos: igdb_id, name, cover_url y el slug
        juego, _ = Game.objects.get_or_create(
            igdb_id=game_id, 
            defaults={
                'name': nombre_juego, 
                'cover_url': portada_url,
                'slug': slug_generado
            }
        )

        # Buscamos o creamos la interacción
        interaccion, _ = UserGame.objects.get_or_create(user=request.user, game=juego)
        interaccion.status = nuevo_estado
        interaccion.save()

        return JsonResponse({'success': True, 'status': nuevo_estado})
    return JsonResponse({'error': 'Método no permitido'}, status=400)


@login_required
def save_game_review(request, game_id):
    """Vista tradicional para guardar la reseña escrita en el Diario"""
    if request.method == 'POST':
        texto_resena = request.POST.get('review', '')
        nombre_juego = request.POST.get('game_name', 'Juego Desconocido')
        portada_url = request.POST.get('game_cover', '')

        # Generamos el slug también aquí
        slug_generado = slugify(f"{nombre_juego}-{game_id}")

        # Misma estructura con TUS campos exactos
        juego, _ = Game.objects.get_or_create(
            igdb_id=game_id, 
            defaults={
                'name': nombre_juego, 
                'cover_url': portada_url,
                'slug': slug_generado
            }
        )

        interaccion, _ = UserGame.objects.get_or_create(user=request.user, game=juego)
        interaccion.review = texto_resena
        interaccion.save()

        # Recargamos la página del juego para ver la reseña
        return redirect('detail', game_id=game_id)