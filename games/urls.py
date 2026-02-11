from django.urls import path
from django.contrib.auth import views as auth_views  # Importar esto
from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("game/<int:game_id>/", views.detail, name="detail"),
    path(
        "game/<int:game_id>/add/<str:status>/",
        views.add_to_library,
        name="add_to_library",
    ),
    path("profile/", views.profile, name="profile"),
    path("search/", views.search, name="search"),
    path("game/<int:game_id>/review/", views.update_review, name="update_review"),
    path("profile/edit/", views.edit_profile, name="edit_profile"),
    path("register/", views.register, name="register"),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("u/<str:username>/", views.public_profile, name="public_profile"),
    # Ruta para seguir
    path("u/<str:username>/follow/", views.toggle_follow, name="toggle_follow"),
    path("community/", views.community, name="community"),
    path("review/<int:review_id>/like/", views.toggle_like, name="toggle_like"),
    path("review/<int:review_id>/comment/", views.add_comment, name="add_comment"),
    path("lists/create/", views.create_list, name="create_list"),
    path("u/<str:username>/list/<slug:slug>/", views.list_detail, name="list_detail"),
    path(
        "game/<int:game_id>/add-to-list/",
        views.add_to_list_view,
        name="add_to_list_view",
    ),
    path('notifications/', views.notifications_view, name='notifications'),
    path('releases/', views.releases, name='releases'),
    path('category/<int:genre_id>/', views.category, name='category'),
]
