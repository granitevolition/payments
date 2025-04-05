import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    # Application configuration
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev_secret_key')
    DEBUG = os.getenv('FLASK_ENV') == 'development'
    
    # MongoDB configuration 
    # Note: We specify the database in app.py with DB_NAME = "lipia_payments"
    MONGO_URI = os.getenv(
        'MONGO_URI', 
        'mongodb+srv://edgarmaina003:Andikar_25@oldtrafford.id96k.mongodb.net/?retryWrites=true&w=majority&appName=OldTrafford'
    )
    
    # API configuration
    API_BASE_URL = os.getenv('API_BASE_URL', 'https://lipia-api.kreativelabske.com/api')
    API_KEY = os.getenv('API_KEY', '7c8a3202ae14857e71e3a9db78cf62139772cae6')
    PAYMENT_URL = os.getenv('PAYMENT_URL', 'https://lipia-online.vercel.app/link/andikartill')
    
    # Session configuration
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
