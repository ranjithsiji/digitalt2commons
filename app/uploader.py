import os
import json
import requests
from requests_oauthlib import OAuth1Session
from urllib.parse import urlencode
from config import Config
from flask import current_app

class WikimediaUploader:
    def __init__(self, access_token=None, access_token_secret=None):
        self.config = Config.WIKIMEDIA_OAUTH
        self.oauth_token = None
        self.oauth_token_secret = None
        
        # For OAuth1 session
        self.session = OAuth1Session(
            self.config['consumer_key'],
            client_secret=self.config['consumer_secret'],
            resource_owner_key=access_token,
            resource_owner_secret=access_token_secret
        )
    
    def get_authorization_url(self):
        """Get the OAuth authorization URL."""
        request_token_url = f"{self.config['base_url']}index.php?title=Special:OAuth/initiate"
        
        try:
            # Get request token
            response = self.session.fetch_request_token(
                request_token_url,
                params={'oauth_callback': self.config['callback_url']}
            )
            
            self.oauth_token = response.get('oauth_token')
            self.oauth_token_secret = response.get('oauth_token_secret')
            
            if not self.oauth_token or not self.oauth_token_secret:
                raise ValueError("Failed to get OAuth token")
            
            # Return authorization URL
            return f"{self.config['base_url']}index.php?title=Special:OAuth/authorize&oauth_token={self.oauth_token}"
        
        except Exception as e:
            current_app.logger.error(f"Error getting authorization URL: {str(e)}")
            raise
    
    def get_access_token(self, oauth_verifier):
        """Exchange the OAuth verifier for access tokens."""
        if not self.oauth_token or not self.oauth_token_secret:
            raise ValueError("OAuth tokens not initialized")
        
        access_token_url = f"{self.config['base_url']}index.php?title=Special:OAuth/token"
        
        try:
            # Update session with temporary tokens
            self.session = OAuth1Session(
                self.config['consumer_key'],
                client_secret=self.config['consumer_secret'],
                resource_owner_key=self.oauth_token,
                resource_owner_secret=self.oauth_token_secret,
                verifier=oauth_verifier
            )
            
            # Get access token
            response = self.session.fetch_access_token(access_token_url)
            
            access_token = response.get('oauth_token')
            access_token_secret = response.get('oauth_token_secret')
            
            if not access_token or not access_token_secret:
                raise ValueError("Failed to get access token")
            
            return access_token, access_token_secret
        
        except Exception as e:
            current_app.logger.error(f"Error getting access token: {str(e)}")
            raise
    
    def upload_to_commons(self, filename, image_data, description, categories, structured_data):
        """Upload a file to Wikimedia Commons."""
        upload_url = f"{self.config['base_url']}api.php"
        
        try:
            # Step 1: Get edit token
            token_params = {
                'action': 'query',
                'meta': 'tokens',
                'type': 'csrf',
                'format': 'json'
            }
            
            token_response = self.session.get(upload_url, params=token_params)
            token_response.raise_for_status()
            token_data = token_response.json()
            
            edit_token = token_data.get('query', {}).get('tokens', {}).get('csrftoken')
            if not edit_token:
                raise ValueError("Failed to get edit token")
            
            # Step 2: Prepare upload parameters
            params = {
                'action': 'upload',
                'filename': filename,
                'comment': f"Uploaded from Digitalt Museum",
                'text': description,
                'tags': 'DigitaltMuseumUploader',
                'format': 'json',
                'token': edit_token,
                'ignorewarnings': 1
            }
            
            # Add categories
            for i, category in enumerate(categories, 1):
                params[f'categories[{i}]'] = category
            
            # Prepare multipart form data
            files = {
                'file': (filename, image_data)
            }
            
            # Step 3: Upload the file
            upload_response = self.session.post(
                upload_url,
                data=params,
                files=files
            )
            upload_response.raise_for_status()
            upload_result = upload_response.json()
            
            # Step 4: Add structured data if upload was successful
            if upload_result.get('upload', {}).get('result') == 'Success':
                self.add_structured_data(upload_result['upload']['filename'], structured_data)
            
            return upload_result
        
        except Exception as e:
            current_app.logger.error(f"Upload error: {str(e)}")
            return {
                'error': {
                    'code': 'upload_failed',
                    'info': str(e)
                }
            }
    
    def add_structured_data(self, filename, structured_data):
        """Add structured data to the uploaded file."""
        if not structured_data or not structured_data.get('statements'):
            return
        
        api_url = f"{self.config['base_url']}api.php"
        
        try:
            # Get edit token
            token_params = {
                'action': 'query',
                'meta': 'tokens',
                'type': 'csrf',
                'format': 'json'
            }
            
            token_response = self.session.get(api_url, params=token_params)
            token_response.raise_for_status()
            token_data = token_response.json()
            
            edit_token = token_data.get('query', {}).get('tokens', {}).get('csrftoken')
            if not edit_token:
                raise ValueError("Failed to get edit token")
            
            # Prepare structured data payload
            params = {
                'action': 'wbeditentity',
                'format': 'json',
                'token': edit_token,
                'new': 'item',
                'data': json.dumps(structured_data)
            }
            
            # Add structured data
            response = self.session.post(api_url, data=params)
            response.raise_for_status()
            
            return response.json()
        
        except Exception as e:
            current_app.logger.error(f"Structured data error: {str(e)}")
            raise
    
    def make_api_request(self, params):
        """Make a generic API request to Wikimedia Commons."""
        api_url = f"{self.config['base_url']}api.php"
        
        try:
            response = self.session.get(api_url, params=params)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            current_app.logger.error(f"API request error: {str(e)}")
            raise