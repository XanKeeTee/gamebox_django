import requests

# Tus credenciales
client_id = "gre1urnnley3l5ely8qdblj9cnrjck"
client_secret = "j9txsem2n7grkowaivra4gg4vq9ox8"

url = "https://id.twitch.tv/oauth2/token"
params = {
    "client_id": client_id,
    "client_secret": client_secret,
    "grant_type": "client_credentials"
}

response = requests.post(url, params=params)
print("\n=== COPIA ESTE TOKEN EN TU SETTINGS.PY ===")
print(f'IGDB_ACCESS_TOKEN = "{response.json()["access_token"]}"')
print("==========================================\n")