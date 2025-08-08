import requests
from config.settings import Config

class DigitaltMuseumClient:
    def __init__(self):
        self.base_url = Config.DM_API_BASE
    
    def get_artifact(self, artifact_id):
        url = f"{self.base_url}object/{artifact_id}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    
    def get_media(self, media_id):
        url = f"{self.base_url}media/{media_id}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()