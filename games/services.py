import requests
import time
from django.conf import settings

class IGDBService:
    def __init__(self):
        self.client_id = settings.IGDB_CLIENT_ID
        self.client_secret = settings.IGDB_CLIENT_SECRET
        
        # --- ESTA ERA LA LÍNEA QUE FALTABA ---
        self.base_url = 'https://api.igdb.com/v4'
        self.auth_url = 'https://id.twitch.tv/oauth2/token'
        
        self.access_token = self._get_access_token()
        self.headers = {
            'Client-ID': self.client_id,
            'Authorization': f'Bearer {self.access_token}',
        }

    def _get_access_token(self):
        params = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'grant_type': 'client_credentials'
        }
        response = requests.post(self.auth_url, params=params)
        return response.json().get('access_token')

    def _build_query(self, data):
        # Convierte el diccionario de python a string para la API de IGDB
        return f'fields {data["fields"]}; where {data["where"]}; sort {data.get("sort", "name asc")}; limit {data.get("limit", "10")};'

    def search_games(self, query):
        data = {
            "fields": "name, cover.url, first_release_date, total_rating, slug",
            "where": f"name ~ *\"{query}\"* & cover != null",
            "limit": "20"
        }
        response = requests.post(f"{self.base_url}/games", headers=self.headers, data=self._build_query(data))
        if response.status_code == 200:
            return response.json()
        return []

    def get_top_games(self):
        data = {
            "fields": "name, cover.url, total_rating, slug",
            "where": "total_rating > 80 & cover != null & rating_count > 50",
            "sort": "total_rating desc",
            "limit": "12"
        }
        response = requests.post(f"{self.base_url}/games", headers=self.headers, data=self._build_query(data))
        if response.status_code == 200:
            return response.json()
        return []

    def get_game_detail(self, game_id):
        data = {
            # AÑADIMOS: videos.name (antes solo teniamos videos.video_id)
            "fields": "name, cover.url, summary, first_release_date, total_rating, genres.name, platforms.name, screenshots.url, slug, videos.video_id, videos.name, similar_games.name, similar_games.cover.url, similar_games.slug",
            "where": f"id = {game_id}",
            "limit": "1"
        }
        
        response = requests.post(f"{self.base_url}/games", headers=self.headers, data=self._build_query(data))
        
        if response.status_code == 200:
            results = response.json()
            if results:
                game = results[0]
                
                # Arreglar calidad portada principal
                if 'cover' in game:
                    game['cover']['url'] = game['cover']['url'].replace('t_thumb', 't_cover_big')
                
                # Arreglar calidad screenshots
                if 'screenshots' in game:
                    for screen in game['screenshots']:
                        screen['url'] = screen['url'].replace('t_thumb', 't_screenshot_big')

                # NUEVO: Arreglar calidad portadas de juegos similares
                if 'similar_games' in game:
                    for sim in game['similar_games']:
                        if 'cover' in sim:
                            sim['cover']['url'] = sim['cover']['url'].replace('t_thumb', 't_cover_big')

                return game
        return None

    def get_upcoming_games(self):
        # Obtenemos el "timestamp" de ahora mismo
        current_time = int(time.time())
        
        # Pedimos juegos que salgan en el futuro
        data = {
            "fields": "name, cover.url, first_release_date, platforms.name, genres.name, summary",
            "where": f"first_release_date > {current_time} & cover != null & rating_count > 0", 
            "sort": "first_release_date asc",
            "limit": "24"
        }
        
        response = requests.post(f"{self.base_url}/games", headers=self.headers, data=self._build_query(data))
        
        if response.status_code == 200:
            return response.json()
        return []