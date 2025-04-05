import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'development-key-change-in-production')
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() in ['true', '1', 't']
    MONGO_URI = os.environ.get('MONGO_URI', 'mongodb+srv://edgarmaina003:Andikar_25@oldtrafford.id96k.mongodb.net/lipia_payments?retryWrites=true&w=majority&appName=OldTrafford')
    API_KEY = os.environ.get('API_KEY', '7c8a3202ae14857e71e3a9db78cf62139772cae6')  # Default API key from original app
    API_BASE_URL = os.environ.get('API_BASE_URL', 'https://lipia-api.kreativelabske.com/api')
    CALLBACK_URL = os.environ.get('CALLBACK_URL')  # Will be set based on the deployment URL
    
    # Gunicorn settings
    GUNICORN_TIMEOUT = int(os.environ.get('GUNICORN_TIMEOUT', 120))
    GUNICORN_WORKERS = int(os.environ.get('GUNICORN_WORKERS', 3))
    GUNICORN_WORKER_CLASS = os.environ.get('GUNICORN_WORKER_CLASS', 'sync')

    # MongoDB settings
    MONGO_DB_NAME = 'lipia_payments'
    MONGO_MAX_POOL_SIZE = 50
    MONGO_MIN_POOL_SIZE = 10
    MONGO_MAX_IDLE_TIME_MS = 10000  # 10 seconds
    MONGO_CONNECT_TIMEOUT_MS = 5000  # 5 seconds
    MONGO_SERVER_SELECTION_TIMEOUT_MS = 5000  # 5 seconds
    
    # Payment settings
    PAYMENT_TIMEOUT_SECONDS = 60  # 60 seconds timeout for payments
    BASIC_SUBSCRIPTION_WORDS = 100
    PREMIUM_SUBSCRIPTION_WORDS = 1000
    BASIC_SUBSCRIPTION_AMOUNT = 20
    PREMIUM_SUBSCRIPTION_AMOUNT = 50
