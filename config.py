import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base configuration"""
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or 'dev-key-change-me'
    DM_API_BASE = os.environ.get('DM_API_BASE', 'https://digitaltmuseum.se/api/1/')
    
    # Wikimedia OAuth settings
    WIKIMEDIA_OAUTH = {
        'consumer_key': os.environ.get('WIKIMEDIA_CONSUMER_KEY'),
        'consumer_secret': os.environ.get('WIKIMEDIA_CONSUMER_SECRET'),
        'base_url': 'https://commons.wikimedia.org/w/',
        'callback_url': os.environ.get('OAUTH_CALLBACK_URL')
    }

class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True

class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}