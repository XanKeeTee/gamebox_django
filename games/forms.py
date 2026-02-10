from django import forms
from django.contrib.auth.models import User
from .models import Profile, Comment
from .models import GameList  # <--- Asegúrate de importar Comment aquí


class UserUpdateForm(forms.ModelForm):
    email = forms.EmailField()

    class Meta:
        model = User
        fields = ["username", "email"]


class ProfileUpdateForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["avatar", "banner", "bio", "location"]


# --- AQUÍ ESTABA EL ERROR, YA CORREGIDO ---
class CommentForm(forms.ModelForm):  # <--- Debe ser forms.ModelForm
    class Meta:
        model = Comment
        fields = ["text"]
        widgets = {
            "text": forms.TextInput(
                attrs={
                    "class": "w-full bg-zinc-900 border border-white/10 rounded-full px-4 py-2 text-sm text-white focus:outline-none focus:border-indigo-500 placeholder-gray-500",
                    "placeholder": "Escribe un comentario...",
                }
            )
        }


class GameListForm(forms.ModelForm):
    class Meta:
        model = GameList
        fields = ["name", "description"]
        widgets = {
            "name": forms.TextInput(
                attrs={
                    "class": "w-full bg-zinc-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-indigo-500 placeholder-gray-500 font-bold",
                    "placeholder": "Título de la lista (ej: Mis Favoritos de 2024)",
                }
            ),
            "description": forms.Textarea(
                attrs={
                    "class": "w-full bg-zinc-900 border border-white/10 rounded-xl px-4 py-3 text-white focus:outline-none focus:border-indigo-500 placeholder-gray-500",
                    "placeholder": "¿De qué va esta lista?",
                    "rows": 3,
                }
            ),
        }
