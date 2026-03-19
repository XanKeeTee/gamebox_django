import requests
import time
from datetime import datetime 
from django.conf import settings
from dateutil.relativedelta import relativedelta

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
        try:
            query_clean = query.replace('"', '')
            
            # 1. Búsqueda limpia a IGDB (sin WHERE restrictivos). 
            # Pedimos los campos 'category' y 'version_parent' para usarlos nosotros.
            query_string = (
                f'search "{query_clean}"; '
                'fields name, cover.url, first_release_date, total_rating_count, total_rating, slug, category, version_parent; '
                'limit 50;'
            )
            
            response = requests.post(f"{self.base_url}/games", headers=self.headers, data=query_string)
            
            if response.status_code == 200:
                raw_games = response.json()
                juegos_limpios = []
                
                # 2. FILTRADO EN PYTHON (Magia pura)
                for game in raw_games:
                    categoria = game.get('category', 0)
                    tiene_padre = 'version_parent' in game # Si tiene padre, es una edición rara o DLC
                    
                    # Solo aceptamos: Juegos principales (0), Remakes (8), Remasters (9)
                    # Y que NO sean una edición alternativa (tiene_padre == False)
                    if categoria in [0, 8, 9] and not tiene_padre:
                        
                        # Arreglamos la imagen si la tiene
                        if 'cover' in game:
                            game['cover']['url'] = game['cover']['url'].replace('t_thumb', 't_cover_big')
                            
                        juegos_limpios.append(game)
                
                # 3. ORDENAMOS por popularidad para que los famosos queden arriba
                juegos_limpios.sort(key=lambda x: x.get('total_rating_count') or 0, reverse=True)
                
                return juegos_limpios
            else:
                print(f"❌ ERROR IGDB {response.status_code}: {response.text}")
                return []
                
        except Exception as e:
            print(f"❌ ERROR PYTHON EN SEARCH_GAMES: {e}")
            return []

    def get_top_games(self):
        seis_meses_atras = int((datetime.now() - relativedelta(months=6)).timestamp())
        
        data = {
            "fields": "name, cover.url, first_release_date, total_rating, slug",
            "where": f"first_release_date > {seis_meses_atras} & total_rating_count > 10 & cover != null",
            "sort": "total_rating desc",
            "limit": "15"
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
    
    def advanced_search(self, platform=None, genre=None, year=None, min_rating=None):
        where_clauses = ["cover != null"]
        
        if platform and platform != 'all':
            where_clauses.append(f"platforms = ({platform})")
        
        if genre and genre != 'all':
            where_clauses.append(f"genres = ({genre})")
            
        if year and year != 'all':
            from datetime import datetime
            start_date = int(datetime(int(year), 1, 1).timestamp())
            end_date = int(datetime(int(year), 12, 31).timestamp())
            where_clauses.append(f"first_release_date >= {start_date} & first_release_date <= {end_date}")
            
        if min_rating and min_rating != 'all':
            where_clauses.append(f"total_rating >= {min_rating}")

        final_where = " & ".join(where_clauses)
        
        data = {
            "fields": "name, cover.url, first_release_date, total_rating, slug",
            "where": final_where,
            "sort": "total_rating desc",
            "limit": "30"
        }
        
        response = requests.post(f"{self.base_url}/games", headers=self.headers, data=self._build_query(data))
        
        if response.status_code == 200:
            games = response.json()
            for game in games:
                if 'cover' in game:
                    game['cover']['url'] = game['cover']['url'].replace('t_thumb', 't_cover_big')
            return games
        return []