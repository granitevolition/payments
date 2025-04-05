import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev_secret_key')
    MONGO_URI = os.getenv('MONGO_URI', '').replace('<db_password>', 'Andikar_25')
    API_BASE_URL = os.getenv('API_BASE_URL', 'https://lipia-api.kreativelabske.com/api')
    API_KEY = os.getenv('API_KEY', '7c8a3202ae14857e71e3a9db78cf62139772cae6')
    PAYMENT_URL = os.getenv('PAYMENT_URL', 'https://lipia-online.vercel.app/link/andikartill')
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    DEBUG = os.getenv('FLASK_ENV') == 'development'
