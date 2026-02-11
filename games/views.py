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

    return render(request, 'games/index.html', {
        'hero_game': trending_games[0] if trending_games else None,
        'trending_games': trending_games[1:],
        'upcoming': upcoming_games,
        'feed_items': feed_items
    })


def detail(request, game_id):
    service = IGDBService()
    game = service.get_game_detail(game_id)

    if game:
        if "cover" in game:
            game["cover"]["url"] = game["cover"]["url"].replace(
                "t_thumb", "t_cover_big"
            )
        if "screenshots" in game:
            for screen in game["screenshots"]:
                screen["url"] = screen["url"].replace("t_thumb", "t_screenshot_huge")

    user_game = None
    user_game_status = None

    community_reviews = []

    local_game = Game.objects.filter(igdb_id=game_id).first()

    if local_game:
        if request.user.is_authenticated:
            user_game = UserGame.objects.filter(
                user=request.user, game=local_game
            ).first()
            if user_game:
                user_game_status = user_game.status

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
            "community_reviews": community_reviews,
        },
    )


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


@login_required(login_url="login")
def profile(request):
    my_games = (
        UserGame.objects.filter(user=request.user)
        .select_related("game")
        .order_by("-updated_at")
    )
    my_lists = request.user.lists.all().order_by("-created_at")

    status_counts = my_games.values("status").annotate(total=Count("status"))

    status_data = {"playing": 0, "completed": 0, "backlog": 0, "dropped": 0}
    for item in status_counts:
        if item["status"] in status_data:
            status_data[item["status"]] = item["total"]

    ratings_distribution = [0, 0, 0, 0, 0]
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
        "status_data": status_data,
        "ratings_distribution": ratings_distribution,
    }
    return render(request, "games/profile.html", context)


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
        request, "games/search_results.html", {"games": games, "query": query}
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


@login_required(login_url="/admin/login/")
def edit_profile(request):
    if not hasattr(request.user, "profile"):
        Profile.objects.create(user=request.user)

    if request.method == "POST":
        u_form = UserUpdateForm(request.POST, instance=request.user)
        p_form = ProfileUpdateForm(
            request.POST, request.FILES, instance=request.user.profile
        )

        if u_form.is_valid() and p_form.is_valid():
            u_form.save()
            p_form.save()
            return redirect("profile")
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
        "lists": user_lists,
        "total_count": my_games.count(),
        "fav_count": my_games.filter(is_favorite=True).count(),
        "is_following": is_following,
        "followers_count": profile_user.profile.followed_by.count(),
        "following_count": profile_user.profile.follows.count(),
    }
    return render(request, "games/public_profile.html", context)


@login_required(login_url="login")
def toggle_follow(request, username):
    target_user = get_object_or_404(User, username=username)
    my_profile = request.user.profile

    if target_user != request.user:
        if my_profile.follows.filter(id=target_user.profile.id).exists():
            my_profile.follows.remove(target_user.profile)
        else:
            my_profile.follows.add(target_user.profile)

    return redirect("public_profile", username=username)


def community(request):
    popular_users = User.objects.annotate(
        num_followers=Count("profile__followed_by")
    ).order_by("-num_followers")[
        :6
    ]

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
            return redirect("profile")
    else:
        form = GameListForm()
    return render(request, "games/create_list.html", {"form": form})


def list_detail(request, username, slug):
    game_list = get_object_or_404(GameList, user__username=username, slug=slug)
    return render(request, "games/list_detail.html", {"game_list": game_list})


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

    return render(request, "games/notifications.html", {"notifs": notifs})


def releases(request):
    service = IGDBService()
    upcoming_games = service.get_upcoming_games()

    for game in upcoming_games:
        if "cover" in game:
            game["cover"]["url"] = game["cover"]["url"].replace(
                "t_thumb", "t_cover_big"
            )

    return render(request, "games/releases.html", {"games": upcoming_games})

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
    
    return render(request, 'games/category.html', {'games': games, 'title': title})

