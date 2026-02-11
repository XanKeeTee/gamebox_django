import requests
import time
from datetime import datetime 
from django.conf import settings

class IGDBService:
    def __init__(self):
        self.base_url = "https://api.igdb.com/v4"
        self.client_id = settings.IGDB_CLIENT_ID
        self.access_token = settings.IGDB_ACCESS_TOKEN
        self.headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}",
        }

    def _build_query(self, data):
        return f'fields {data["fields"]}; where {data["where"]}; sort {data.get("sort", "id desc")}; limit {data.get("limit", "10")}; offset {data.get("offset", "0")};'

    def get_games(self, search_query=None, page=1):
        limit = 24
        offset = (page - 1) * limit
        
        data = {
            "fields": "name, cover.url, first_release_date, total_rating, slug",
            "where": "total_rating_count > 0 & cover != null",
            "limit": str(limit),
            "offset": str(offset)
        }
        
        if search_query:
            data["where"] = f'name ~ *"{search_query}"* & cover != null'
        
        response = requests.post(f"{self.base_url}/games", headers=self.headers, data=self._build_query(data))
        
        if response.status_code == 200:
            games = response.json()
            for game in games:
                if 'cover' in game:
                    game['cover']['url'] = game['cover']['url'].replace('t_thumb', 't_cover_big')
            return games
        return []

    def search_games(self, query):
        return self.get_games(search_query=query)

    def get_top_games(self):
        data = {
            "fields": "name, cover.url, first_release_date, total_rating, slug",
            "where": "total_rating >= 85 & total_rating_count > 50 & cover != null",
            "sort": "total_rating desc",
            "limit": "10"
        }
        
        response = requests.post(f"{self.base_url}/games", headers=self.headers, data=self._build_query(data))
        
        if response.status_code == 200:
            games = response.json()
            for game in games:
                if 'cover' in game:
                    game['cover']['url'] = game['cover']['url'].replace('t_thumb', 't_cover_big')
            return games
        return []

    def get_game_detail(self, game_id):
        data = {
            "fields": "name, cover.url, summary, first_release_date, total_rating, genres.name, platforms.name, screenshots.url, slug, videos.video_id, videos.name, similar_games.name, similar_games.cover.url, similar_games.slug",
            "where": f"id = {game_id}",
            "limit": "1"
        }
        
        response = requests.post(f"{self.base_url}/games", headers=self.headers, data=self._build_query(data))
        
        if response.status_code == 200:
            results = response.json()
            if results:
                game = results[0]
                if 'cover' in game:
                    game['cover']['url'] = game['cover']['url'].replace('t_thumb', 't_cover_big')
                if 'screenshots' in game:
                    for screen in game['screenshots']:
                        screen['url'] = screen['url'].replace('t_thumb', 't_screenshot_big')
                if 'similar_games' in game:
                    for sim in game['similar_games']:
                        if 'cover' in sim:
                            sim['cover']['url'] = sim['cover']['url'].replace('t_thumb', 't_cover_big')
                return game
        return None

    def get_upcoming_games(self):
        current_time = int(time.time())
        data = {
            "fields": "name, cover.url, first_release_date, slug",
            "where": f"first_release_date > {current_time} & cover != null", 
            "sort": "first_release_date asc",
            "limit": "10"
        }
        response = requests.post(f"{self.base_url}/games", headers=self.headers, data=self._build_query(data))
        if response.status_code == 200:
            games = response.json()
            for game in games:
                if 'cover' in game:
                    game['cover']['url'] = game['cover']['url'].replace('t_thumb', 't_cover_big')
                if 'first_release_date' in game:
                    game['first_release_date'] = datetime.fromtimestamp(game['first_release_date'])
            return games
        return []

    def get_games_by_genre(self, genre_id):
        data = {
            "fields": "name, cover.url, first_release_date, total_rating, slug",
            "where": f"genres = ({genre_id}) & total_rating_count > 10 & cover != null",
            "sort": "total_rating desc",
            "limit": "24"
        }
        response = requests.post(f"{self.base_url}/games", headers=self.headers, data=self._build_query(data))
        if response.status_code == 200:
            games = response.json()
            for game in games:
                if 'cover' in game:
                    game['cover']['url'] = game['cover']['url'].replace('t_thumb', 't_cover_big')
            return games
        return []