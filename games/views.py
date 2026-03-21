import json,random
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
import requests
from .services import IGDBService
from django.views.decorators.http import require_POST
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login
from django.contrib.auth.models import User
from django.db.models import Q, Count
from .models import Game, UserGame, Profile, Comment, GameList, ListEntry, Notification,News, UserGame
from django.http import HttpResponseNotFound, JsonResponse
from django.views.decorators.cache import cache_page
from django.contrib import messages
from .forms import GameListForm 
from .forms import GameListForm
from django.utils.text import slugify

def index(request):
    import requests
    import random
    from .services import IGDBService
    from .models import News, UserGame, GameList

    # 1. NOTICIAS (Normalización para evitar errores de VariableDoesNotExist)
    news_api_key = "c015bf30b0fa40d59cb58a571abb2267"
    news_url = f"https://newsapi.org/v2/everything?q=videojuegos&language=es&sortBy=publishedAt&pageSize=3&apiKey={news_api_key}"
    
    noticias_finales = []
    try:
        news_res = requests.get(news_url)
        articles = news_res.json().get('articles', [])
        for a in articles:
            noticias_finales.append({
                'titulo': a.get('title'),
                'foto': a.get('urlToImage'),
                'fuente': a.get('source', {}).get('name'),
                'resumen': a.get('description'),
                'enlace': a.get('url'),
                'fecha': a.get('publishedAt')
            })
    except:
        # Si falla la API, usamos las noticias locales
        news_locales = News.objects.all().order_by('-created_at')[:3]
        for n in news_locales:
            noticias_finales.append({
                'titulo': n.title,
                'foto': n.image_url,
                'fuente': n.source,
                'resumen': n.content,
                'enlace': '#',
                'fecha': n.created_at
            })

    # 2. LÓGICA DE JUEGOS (IGDB)
    service = IGDBService()
    trending_games = service.get_top_games()
    
    # Hero Game
    hero_game = None
    if trending_games:
        hero_game = random.choice(trending_games[:5])
        trending_games = [g for g in trending_games if g['id'] != hero_game['id']]
        if 'cover' in hero_game:
            hero_game['cover']['url'] = hero_game['cover']['url'].replace('t_thumb', 't_cover_big')

    # Top Games y Upcoming
    query = 'fields name, cover.url, total_rating; sort popularity desc; limit 6; where total_rating > 80;'
    response = requests.post(f"{service.base_url}/games", headers=service.headers, data=query)
    top_games = response.json() if response.status_code == 200 else []
    for g in top_games:
        if 'cover' in g:
            g['cover']['url'] = f"https:{g['cover']['url'].replace('t_thumb', 't_cover_big')}"

    upcoming_games = service.get_upcoming_games()[:10]
    for game in upcoming_games:
        if 'cover' in game:
            game['cover']['url'] = game['cover']['url'].replace('t_thumb', 't_cover_big')

    # 3. FEED Y LISTAS
    feed_items = []
    es_feed_global = False
    if request.user.is_authenticated:
        following_ids = request.user.profile.follows.values_list('user__id', flat=True)
        feed_items = UserGame.objects.filter(user__id__in=following_ids).exclude(status='backlog').order_by('-updated_at')[:20]
            
    if not feed_items:
        feed_items = UserGame.objects.exclude(review__isnull=True).exclude(review="").order_by('-updated_at')[:15]
        es_feed_global = True
        
    recent_lists = GameList.objects.select_related('user').order_by('-created_at')[:3]
        
    return render(request, 'games/home/index.html', {
        'hero_game': hero_game,
        'trending_games': trending_games[:8],
        'upcoming': upcoming_games,
        'feed_items': feed_items,
        'es_feed_global': es_feed_global,
        'recent_lists': recent_lists,
        'noticias': noticias_finales, # Usamos la lista normalizada
        'top_games': top_games
    })

def detail(request, game_id):
    from .models import Game, UserGame
    import requests
    import datetime

    service = IGDBService()
    
    query = (
        f'fields name, cover.url, artworks.url, first_release_date, total_rating, total_rating_count, summary, '
        f'genres.name, platforms.name, involved_companies.company.name, involved_companies.developer, '
        f'dlcs.name, dlcs.cover.url, similar_games.name, similar_games.cover.url, '
        f'expansions.name, expansions.cover.url, remakes.name, remakes.cover.url, '
        f'remasters.name, remasters.cover.url, ports.name, ports.cover.url; '
        f'where id = {game_id};'
    )
    
    response = requests.post(f"{service.base_url}/games", headers=service.headers, data=query)
    game = response.json()[0] if response.status_code == 200 and response.json() else None

    if not game:
        return redirect('index')

    if 'first_release_date' in game:
        game['first_release_date'] = datetime.datetime.fromtimestamp(game['first_release_date'])

    if 'cover' in game:
        game['cover']['url'] = game['cover']['url'].replace('t_thumb', 't_cover_big')
    if 'artworks' in game:
        game['artworks'][0]['url'] = game['artworks'][0]['url'].replace('t_thumb', 't_1080p')
    
    for category in ['dlcs', 'similar_games', 'expansions', 'remakes', 'remasters', 'ports']:
        if category in game:
            for item in game[category]:
                if 'cover' in item:
                    item['cover']['url'] = item['cover']['url'].replace('t_thumb', 't_cover_small')

    developers = []
    if 'involved_companies' in game:
        developers = [comp['company']['name'] for comp in game['involved_companies'] if comp.get('developer')]

    local_game = Game.objects.filter(igdb_id=game_id).first()
    reviews = []
    stats = {'plays': 0, 'playing': 0, 'backlogs': 0, 'dropped': 0}
    user_interaction = None

    if local_game:
        reviews = UserGame.objects.filter(game=local_game).exclude(review__isnull=True).exclude(review='').select_related('user__profile').order_by('-updated_at')
        stats['plays'] = UserGame.objects.filter(game=local_game, status='completed').count()
        stats['playing'] = UserGame.objects.filter(game=local_game, status='playing').count()
        stats['backlogs'] = UserGame.objects.filter(game=local_game, status='backlog').count()
        stats['dropped'] = UserGame.objects.filter(game=local_game, status='dropped').count()

        if request.user.is_authenticated:
            user_interaction = UserGame.objects.filter(user=request.user, game=local_game).first()

    return render(request, 'games/catalog/detail.html', {
        'game': game,
        'developers': developers,
        'reviews': reviews,
        'stats': stats,
        'user_interaction': user_interaction
    })

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
    # Traemos todos los juegos del usuario
    mis_juegos = UserGame.objects.filter(user=request.user).select_related('game')
    
    # 1. Contadores básicos
    completados = mis_juegos.filter(status='completed')
    backlog = mis_juegos.filter(status='backlog')
    jugando = mis_juegos.filter(status='playing')
    # Si tienes un campo de favoritos, ponlo aquí. Si no, puedes dejarlo a 0 o quitarlo.
    
    # 2. Distribución de Notas (Ajustado para 1 a 10)
    rating_counts = [0] * 10 # Crea una lista de 10 ceros
    for interaccion in mis_juegos.exclude(rating__isnull=True):
        if 1 <= interaccion.rating <= 10:
            rating_counts[interaccion.rating - 1] += 1
            
    # 3. Traemos las reseñas del usuario con el mismo formato que el Feed
    mis_resenas = mis_juegos.exclude(review__isnull=True).exclude(review="") \
        .prefetch_related('comments__user__profile', 'likes') \
        .order_by('-updated_at')

    context = {
        'total_games': mis_juegos.count(),
        'completados': completados,
        'backlog': backlog,
        'jugando': jugando,
        'rating_counts': json.dumps(rating_counts), # Pasamos los datos listos para Javascript
        'actividades': mis_resenas, # <--- ¡Tus reseñas!
    }
    
    return render(request, 'games/profile/profile.html', context)


def explore(request):
    import requests
    from datetime import datetime
    service = IGDBService()
    
    # Capturamos todos los posibles filtros
    query_text = request.GET.get('q')
    genre = request.GET.get('genre')
    platform = request.GET.get('platform')
    year = request.GET.get('year')
    min_rating = request.GET.get('rating')
    sort_by = request.GET.get('sort', 'popularity')

    filters = []
    
    # Si viene texto desde el buscador de arriba
    if query_text:
        filters.append(f'name ~ *"{query_text}"*')
    
    # Filtros avanzados del lateral
    if genre: filters.append(f'genres = ({genre})')
    if platform: filters.append(f'platforms = ({platform})')
    if min_rating and min_rating != '0': filters.append(f'total_rating >= {min_rating}')
    
    if year:
        try:
            start = int(datetime(int(year), 1, 1).timestamp())
            end = int(datetime(int(year), 12, 31).timestamp())
            filters.append(f'first_release_date >= {start} & first_release_date <= {end}')
        except: pass

    # Si no hay filtros, mostramos juegos populares por defecto
    where_clause = f"where {' & '.join(filters)};" if filters else "where total_rating_count > 20 & themes != (42);"
    
    # Ordenación
    order = "sort popularity desc;"
    if sort_by == 'rating': order = "sort total_rating desc;"
    elif sort_by == 'newest': order = "sort first_release_date desc;"

    query = f'fields name, cover.url, first_release_date, total_rating; {where_clause} {order} limit 50;'
    
    response = requests.post(f"{service.base_url}/games", headers=service.headers, data=query)
    games = response.json() if response.status_code == 200 and isinstance(response.json(), list) else []

    for g in games:
        if 'cover' in g:
            g['cover']['url'] = f"https:{g['cover']['url'].replace('t_thumb', 't_cover_big')}"

    return render(request, 'games/catalog/advanced_search.html', {
        'games': games,
        'current_filters': request.GET,
        'query_text': query_text
    })

def search(request):
    import requests
    query_user = request.GET.get('q') # Recoge lo que viene del input name="q"
    
    if not query_user:
        return redirect('index')

    service = IGDBService()
    
    # Buscamos juegos que coincidan con el nombre
    query = f'search "{query_user}"; fields name, cover.url, first_release_date, total_rating; limit 24;'
    
    response = requests.post(f"{service.base_url}/games", headers=service.headers, data=query)
    games = response.json() if response.status_code == 200 else []

    # Corregimos las URLs de las portadas
    for g in games:
        if 'cover' in g:
            g['cover']['url'] = f"https:{g['cover']['url'].replace('t_thumb', 't_cover_big')}"

    return render(request, 'games/catalog/search_results.html', {
        'games': games,
        'query': query_user
    })

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
    # 1. Buscamos al usuario que estamos visitando
    profile_user = get_object_or_404(User, username=username)
    
    # 2. Traemos SUS juegos
    sus_juegos = UserGame.objects.filter(user=profile_user).select_related('game')
    
    # Contadores
    completados = sus_juegos.filter(status='completed')
    backlog = sus_juegos.filter(status='backlog')
    jugando = sus_juegos.filter(status='playing')
    
    # 3. Distribución de Notas (1 a 10)
    rating_counts = [0] * 10
    for interaccion in sus_juegos.exclude(rating__isnull=True):
        if 1 <= interaccion.rating <= 10:
            rating_counts[interaccion.rating - 1] += 1
            
    # 4. Sus Reseñas
    sus_resenas = sus_juegos.exclude(review__isnull=True).exclude(review="") \
        .prefetch_related('comments__user__profile', 'likes') \
        .order_by('-updated_at')

    # 5. Comprobar si el usuario logueado ya le sigue (Ajusta esto si tu modelo de follows es distinto)
    is_following = False
    if request.user.is_authenticated and request.user != profile_user:
        # Aquí pon tu lógica real para saber si le sigues
        # Ejemplo: is_following = profile_user in request.user.profile.following.all()
        pass

    context = {
        'profile_user': profile_user, # ¡Importante! Pasamos al usuario visitado
        'total_games': sus_juegos.count(),
        'completados': completados,
        'backlog': backlog,
        'jugando': jugando,
        'rating_counts': json.dumps(rating_counts),
        'actividades': sus_resenas,
        'is_following': is_following,
    }
    
    return render(request, 'games/profile/public_profile.html', context)

# ¡OJO! Asegúrate de NO tener @cache_page encima de esta función
def community(request):
    # 1. Traemos TODAS las reseñas de la plataforma que tengan texto escrito
    actividad_reciente = UserGame.objects.exclude(review__isnull=True).exclude(review="") \
        .select_related('user__profile', 'game') \
        .prefetch_related('comments__user__profile', 'likes') \
        .order_by('-updated_at')[:30]

    # 2. Tu lógica para sacar usuarios recomendados (Asegúrate de que no dé error)
    usuarios_sugeridos = User.objects.exclude(id=request.user.id)[:5] if request.user.is_authenticated else User.objects.all()[:5]

    # 3. Mandamos los datos al HTML (IMPORTANTE: el nombre debe ser 'actividades')
    context = {
        'actividades': actividad_reciente, 
        'usuarios_comunidad': usuarios_sugeridos,
    }
    
    return render(request, 'games/community/community.html', context) # Ajusta la ruta si tu html se llama distinto

@login_required
def add_comment(request, review_id):
    if request.method == 'POST':
        texto = request.POST.get('text', '').strip()
        review = get_object_or_404(UserGame, id=review_id)
        
        if texto:
            Comment.objects.create(user=request.user, review=review, text=texto)
            
        referer = request.META.get('HTTP_REFERER', '/')
        return redirect(referer)


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
    mi_lista = get_object_or_404(GameList, user__username=username, slug=slug)
    
    return render(request, 'games/lists/list_detail.html', {
        'lista': mi_lista
    })


@login_required
def add_to_list_view(request, game_id):
    from .models import GameList, ListEntry, Game
    import requests
    from django.utils.text import slugify

    # Buscamos las listas del usuario
    listas = GameList.objects.filter(user=request.user).order_by('-created_at')
    
    # Intentamos obtener el juego de nuestra DB local
    juego = Game.objects.filter(igdb_id=game_id).first()
    
    # Si no existe localmente, lo traemos de IGDB y lo guardamos
    if not juego:
        service = IGDBService()
        query_string = f'fields name, cover.url; where id = {game_id};'
        response = requests.post(f"{service.base_url}/games", headers=service.headers, data=query_string)
        
        if response.status_code == 200 and response.json():
            game_data = response.json()[0]
            nombre = game_data['name']
            
            # Arreglamos la URL de la portada (añadiendo https: y mejorando calidad)
            cover_url = ""
            if 'cover' in game_data:
                raw_url = game_data['cover']['url']
                cover_url = f"https:{raw_url.replace('t_thumb', 't_cover_big')}"
                
            slug_generado = slugify(f"{nombre}-{game_id}")
            juego = Game.objects.create(
                igdb_id=game_id,
                name=nombre,
                cover_url=cover_url,
                slug=slug_generado
            )
        else:
            return redirect('index')
    else:
        # Si el juego ya existía en la DB, nos aseguramos que tenga https: si no lo tiene
        if juego.cover_url and not juego.cover_url.startswith('http'):
            juego.cover_url = f"https:{juego.cover_url}"

    if request.method == 'POST':
        lista_id = request.POST.get('lista_id')
        lista = get_object_or_404(GameList, id=lista_id, user=request.user)
        
        # Guardamos el juego en la lista (ajusta 'game_list' si tu modelo usa otro nombre)
        if not ListEntry.objects.filter(game_list=lista, game=juego).exists():
            ListEntry.objects.create(game_list=lista, game=juego)
            
        return redirect('list_detail', username=request.user.username, slug=lista.slug)
        
    return render(request, 'games/lists/add_to_list.html', {
        'juego': juego,
        'listas': listas
    })

@login_required
def toggle_like(request, review_id):
    if request.method == 'POST': # Importante que sea POST por seguridad
        review = get_object_or_404(UserGame, id=review_id)
        liked = False
        
        # Si el usuario ya le dio like, se lo quitamos. Si no, se lo ponemos.
        if request.user in review.likes.all():
            review.likes.remove(request.user)
        else:
            review.likes.add(request.user)
            liked = True
            
        return JsonResponse({'liked': liked, 'count': review.total_likes()})
    
    return JsonResponse({'error': 'Método no permitido'}, status=400)


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
    import requests
    from datetime import datetime
    service = IGDBService()
    
    # 1. Traer todos los GÉNEROS para el filtro
    genres_res = requests.post(f"{service.base_url}/genres", headers=service.headers, 
                               data='fields name; limit 50; sort name asc;')
    all_genres = genres_res.json() if genres_res.status_code == 200 else []

    # 2. Traer todas las PLATAFORMAS para el filtro
    platforms_res = requests.post(f"{service.base_url}/platforms", headers=service.headers, 
                                  data='fields name; limit 500; sort name asc;')
    all_platforms = platforms_res.json() if platforms_res.status_code == 200 else []

    # Lógica de paginación para el scroll infinito
    page = int(request.GET.get('page', 1))
    limit = 48
    offset = (page - 1) * limit

    # Captura de filtros
    query_text = request.GET.get('q', '')
    genre = request.GET.get('genre', '')
    platform = request.GET.get('platform', '')
    category = request.GET.get('category', '')
    year = request.GET.get('year', '')
    min_rating = request.GET.get('rating', '0')
    sort_by = request.GET.get('sort', 'popularity')

    filters = []
    if query_text: filters.append(f'name ~ *"{query_text}"*')
    if genre: filters.append(f'genres = ({genre})')
    if platform: filters.append(f'platforms = ({platform})')
    if category: filters.append(f'category = {category}')
    if min_rating and min_rating != '0': filters.append(f'total_rating >= {min_rating}')
    
    if year:
        try:
            start = int(datetime(int(year), 1, 1).timestamp())
            end = int(datetime(int(year), 12, 31).timestamp())
            filters.append(f'first_release_date >= {start} & first_release_date <= {end}')
        except: pass

    if not filters:
        where_clause = "where total_rating_count > 100 & version_parent = null & themes != (42);"
    else:
        where_clause = f"where {' & '.join(filters)} & version_parent = null;"
    
    if sort_by == 'rating': order = "sort total_rating desc;"
    elif sort_by == 'newest': order = "sort first_release_date desc;"
    else: order = "sort popularity desc;"

    query = f'fields name, cover.url, first_release_date, total_rating; {where_clause} {order} limit {limit}; offset {offset};'
    
    response = requests.post(f"{service.base_url}/games", headers=service.headers, data=query)
    games = response.json() if response.status_code == 200 and isinstance(response.json(), list) else []

    for g in games:
        if 'cover' in g:
            g['cover']['url'] = f"https:{g['cover']['url'].replace('t_thumb', 't_cover_big')}"

    if request.headers.get('x-requested-with') == 'XMLHttpRequest':
        return render(request, 'games/catalog/_game_grid_items.html', {'games': games})

    return render(request, 'games/catalog/advanced_search.html', {
        'games': games,
        'all_genres': all_genres,
        'all_platforms': all_platforms,
        'current_filters': request.GET,
        'query_text': query_text,
        'current_sort': sort_by,
        'next_page': page + 1
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

def update_review(request, game_id):
    if request.method == 'POST':
        # 1. Recogemos los datos del formulario (texto, nota, y datos del juego)
        texto_resena = request.POST.get('review', '')
        nota = request.POST.get('rating')
        nombre_juego = request.POST.get('game_name', f'Juego {game_id}')
        portada_url = request.POST.get('game_cover', '')

        # 2. MAGIA: Buscamos el juego. Si NO existe, Django lo crea en el acto.
        slug_generado = slugify(f"{nombre_juego}-{game_id}")
        juego, _ = Game.objects.get_or_create(
            igdb_id=game_id, 
            defaults={
                'name': nombre_juego, 
                'cover_url': portada_url,
                'slug': slug_generado
            }
        )

        # 3. Guardamos la reseña y la nota conectándola con el usuario y el juego
        interaccion, _ = UserGame.objects.get_or_create(user=request.user, game=juego)
        interaccion.review = texto_resena
        
        if nota and nota.isdigit():
            interaccion.rating = int(nota)
            
        interaccion.save()

    # 4. Devolvemos al usuario a la ficha del juego
    return redirect('detail', game_id=game_id)

def quick_search_api(request):
    query = request.GET.get('q', '')
    if len(query) < 3:
        return JsonResponse({'games': []})
    
    service = IGDBService()
    # Traemos solo los 5 mejores resultados para no saturar el modal
    results = service.search_games(query)[:5] 
    
    games_data = []
    for game in results:
        cover_url = ""
        if 'cover' in game:
            cover_url = game['cover']['url'].replace('t_thumb', 't_cover_small')
            
        # Intentamos sacar el año de lanzamiento para mostrarlo en la lista
        year = ""
        if 'first_release_date' in game:
            import datetime
            try:
                dt = datetime.datetime.fromtimestamp(game['first_release_date'])
                year = dt.year
            except:
                pass

        games_data.append({
            'id': game['id'],
            'name': game['name'],
            'cover_url': cover_url,
            'year': year
        })
        
    return JsonResponse({'games': games_data})

@login_required
def quick_log_save(request):
    """Guarda la reseña rápida enviada por AJAX desde el modal"""
    if request.method == 'POST':
        import json
        data = json.loads(request.body)
        
        game_id = data.get('game_id')
        nombre = data.get('name')
        cover_url = data.get('cover_url')
        status = data.get('status', 'completed')
        rating = data.get('rating')
        review = data.get('review', '')

        if not game_id or not nombre:
            return JsonResponse({'error': 'Faltan datos'}, status=400)

        # Generamos el slug como hacemos siempre
        slug_generado = slugify(f"{nombre}-{game_id}")
        
        # Buscamos o creamos el juego en nuestra BD local
        juego, _ = Game.objects.get_or_create(
            igdb_id=game_id, 
            defaults={
                'name': nombre, 
                'cover_url': cover_url,
                'slug': slug_generado
            }
        )

        # Buscamos o creamos la interacción
        interaccion, _ = UserGame.objects.get_or_create(user=request.user, game=juego)
        interaccion.status = status
        interaccion.review = review
        if rating and rating != "":
            interaccion.rating = int(rating)
        interaccion.save()

        return JsonResponse({'success': True})
        
    return JsonResponse({'error': 'Método no permitido'}, status=405)

def user_lists(request, username):
    # Buscamos al usuario por su nombre
    perfil_usuario = get_object_or_404(User, username=username)
    
    # Traemos todas sus listas, de la más nueva a la más antigua
    listas = GameList.objects.filter(user=perfil_usuario).order_by('-created_at')
    
    return render(request, 'games/lists/user_lists.html', {
        'perfil_usuario': perfil_usuario,
        'listas': listas
    })

@login_required
def edit_list(request, username, slug):
    lista = get_object_or_404(GameList, user__username=username, slug=slug)
    
    # Seguridad: Si el usuario actual no es el dueño, lo devolvemos a la lista
    if request.user != lista.user:
        return redirect('list_detail', username=username, slug=slug)
        
    if request.method == 'POST':
        # Recogemos los datos del formulario
        lista.name = request.POST.get('name', lista.name)
        lista.description = request.POST.get('description', lista.description)
        lista.save()
        return redirect('list_detail', username=username, slug=slug)
        
    return render(request, 'games/lists/edit_list.html', {'lista': lista})

@login_required
def delete_list(request, username, slug):
    lista = get_object_or_404(GameList, user__username=username, slug=slug)
    
    # Seguridad
    if request.user != lista.user:
        return redirect('list_detail', username=username, slug=slug)
        
    if request.method == 'POST':
        lista.delete()
        # Al borrarla, lo mandamos a su página de "Mis Listas"
        return redirect('user_lists', username=username)
        
    return render(request, 'games/lists/delete_list.html', {'lista': lista})

@login_required
def remove_from_list(request, list_id, game_id):
    from .models import GameList, ListEntry
    
    lista = get_object_or_404(GameList, id=list_id, user=request.user)
    entry = get_object_or_404(ListEntry, game_list=lista, game__igdb_id=game_id)
    
    entry.delete()
    
    return redirect('list_detail', username=request.user.username, slug=lista.slug)