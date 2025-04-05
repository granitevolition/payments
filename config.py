import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev_secret_key')
    
    # Set default MongoDB URI
    default_mongo_uri = 'mongodb+srv://edgarmaina003:Andikar_25@oldtrafford.id96k.mongodb.net/?retryWrites=true&w=majority&appName=OldTrafford'
    
    # Get MongoDB URI from environment, or use default
    MONGO_URI = os.getenv('MONGO_URI', default_mongo_uri)
    
    # Ensure the URI is properly formatted
    if MONGO_URI and '<db_password>' in MONGO_URI:
        MONGO_URI = MONGO_URI.replace('<db_password>', 'Andikar_25')
    
    # Ensure the URI begins with the required scheme
    if MONGO_URI and not (MONGO_URI.startswith('mongodb://') or MONGO_URI.startswith('mongodb+srv://')):
        # This is a fallback in case the URI is malformed
        MONGO_URI = default_mongo_uri
    
    API_BASE_URL = os.getenv('API_BASE_URL', 'https://lipia-api.kreativelabske.com/api')
    API_KEY = os.getenv('API_KEY', '7c8a3202ae14857e71e3a9db78cf62139772cae6')
    PAYMENT_URL = os.getenv('PAYMENT_URL', 'https://lipia-online.vercel.app/link/andikartill')
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    DEBUG = os.getenv('FLASK_ENV') == 'development'
