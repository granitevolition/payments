import os
import json
import logging
import time
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
import pymongo
from flask_bcrypt import Bcrypt
from config import Config
import payment_processor  # Import our payment processor module

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Create MongoDB connection directly
mongo_client = None
mongo_db = None

try:
    # Create MongoDB client with explicit timeout and options
    mongo_uri = app.config.get('MONGO_URI')
    logger.info(f"Connecting to MongoDB: {mongo_uri}")
    
    # Create a direct connection to MongoDB with optimized parameters from config
    mongo_client = pymongo.MongoClient(
        mongo_uri,
        maxPoolSize=Config.MONGO_MAX_POOL_SIZE,
        minPoolSize=Config.MONGO_MIN_POOL_SIZE,
        maxIdleTimeMS=Config.MONGO_MAX_IDLE_TIME_MS,
        serverSelectionTimeoutMS=Config.MONGO_SERVER_SELECTION_TIMEOUT_MS,
        connectTimeoutMS=Config.MONGO_CONNECT_TIMEOUT_MS,
        retryWrites=True
    )
    
    # Test the connection
    mongo_client.admin.command('ping')
    logger.info("MongoDB connection successful!")
    
    # Get the database - specify the database name explicitly
    mongo_db = mongo_client[Config.MONGO_DB_NAME]
    logger.info(f"Connected to database: {Config.MONGO_DB_NAME}")
    
    # Create indexes for better performance
    mongo_db.users.create_index([('username', 1)], unique=True)
    mongo_db.payments.create_index([('checkout_id', 1)])
    mongo_db.transactions.create_index([('checkout_id', 1)])
    mongo_db.transactions.create_index([('real_checkout_id', 1)])
    mongo_db.transactions.create_index([('username', 1)])
    logger.info("MongoDB indexes created successfully")
    
    # Start payment processor background thread
    payment_worker_thread = payment_processor.start_payment_processor(mongo_db)
    logger.info("Payment processor started")
    
except Exception as e:
    logger.error(f"MongoDB connection error: {str(e)}")
    # Don't exit, let the application continue but with limited functionality

# Initialize Bcrypt for password hashing
bcrypt = Bcrypt(app)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# User model for Flask-Login
class UserLogin(UserMixin):
    def __init__(self, user_data):
        self.user_data = user_data
        self.id = str(user_data['_id'])
        self.username = user_data['username']
        self.phone_number = user_data['phone_number']
        self.words_remaining = user_data['words_remaining']
        self.last_login = user_data.get('last_login', datetime.now())

@login_manager.user_loader
def load_user(user_id):
    try:
        if mongo_db is None:
            logger.error("MongoDB not available when loading user")
            return None
            
        user_data = mongo_db.users.find_one({'_id': ObjectId(user_id)})
        if not user_data:
            return None
        return UserLogin(user_data)
    except Exception as e:
        logger.error(f"Error loading user: {str(e)}")
        return None

# Database operations with error handling
def create_user(username, password, phone_number):
    """Create a new user"""
    try:
        if mongo_db is None:
            logger.error("MongoDB not available when creating user")
            raise Exception("Database connection not available")
            
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        user = {
            'username': username,
            'password': hashed_password,
            'phone_number': phone_number,
            'words_remaining': 0,
            'created_at': datetime.now(),
            'last_login': datetime.now()
        }
        result = mongo_db.users.insert_one(user)
        user['_id'] = result.inserted_id
        return user
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise

def get_user_by_username(username):
    """Get a user by username"""
    try:
        if mongo_db is None:
            logger.error("MongoDB not available when getting user")
            return None
            
        return mongo_db.users.find_one({'username': username})
    except Exception as e:
        logger.error(f"Error in get_user_by_username: {str(e)}")
        return None

def check_password(username, password):
    """Check if password is correct for user"""
    user = get_user_by_username(username)
    if not user:
        return False
    
    return bcrypt.check_password_hash(user['password'], password)

def update_last_login(username):
    """Update last login time for user"""
    try:
        if mongo_db is None:
            logger.error("MongoDB not available when updating last login")
            return
            
        mongo_db.users.update_one(
            {'username': username},
            {'$set': {'last_login': datetime.now()}}
        )
    except Exception as e:
        logger.error(f"Error updating last login: {str(e)}")

def update_word_count(username, words_to_add):
    """Update word count for a user"""
    try:
        if mongo_db is None:
            logger.error("MongoDB not available when updating word count")
            return None
            
        user = get_user_by_username(username)
        if not user:
            return None
        
        current_words = user.get('words_remaining', 0)
        new_word_count = current_words + words_to_add
        
        mongo_db.users.update_one(
            {'username': username},
            {'$set': {'words_remaining': new_word_count}}
        )
        
        return new_word_count
    except Exception as e:
        logger.error(f"Error updating word count: {str(e)}")
        return None

def consume_words(username, words_to_use):
    """Consume words from a user's account"""
    try:
        if mongo_db is None:
            logger.error("MongoDB not available when consuming words")
            return False, 0
            
        user = get_user_by_username(username)
        if not user:
            return False, 0
        
        current_words = user.get('words_remaining', 0)
        
        if current_words < words_to_use:
            return False, current_words
        
        new_word_count = current_words - words_to_use
        
        mongo_db.users.update_one(
            {'username': username},
            {'$set': {'words_remaining': new_word_count}}
        )
        
        return True, new_word_count
    except Exception as e:
        logger.error(f"Error consuming words: {str(e)}")
        return False, 0

def get_user_payments(username):
    """Get all payments for a user"""
    try:
        if mongo_db is None:
            logger.error("MongoDB not available when getting payments")
            return []
            
        return list(mongo_db.payments.find({'username': username}).sort('timestamp', -1))
    except Exception as e:
        logger.error(f"Error getting user payments: {str(e)}")
        return []

def get_callback_url():
    """Build the callback URL for payment notifications"""
    # Use the explicitly configured callback URL if present
    callback_url = app.config.get('CALLBACK_URL')
    if callback_url:
        return f"{callback_url.rstrip('/')}/payment-callback"
    
    # Otherwise try to build it from the request
    if request:
        host = request.host_url.rstrip('/')
        return f"{host}/payment-callback"
    
    # Fallback
    return "https://example.com/payment-callback"

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    from forms import RegistrationForm
    form = RegistrationForm()
    
    if form.validate_on_submit():
        try:
            username = form.username.data
            password = form.password.data
            phone_number = form.phone_number.data
            
            # Create user
            user = create_user(username, password, phone_number)
            flash(f'Account created for {username}! You can now log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Error during registration: {str(e)}', 'danger')
    
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    from forms import LoginForm
    form = LoginForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        # Check if user exists and password is correct
        if check_password(username, password):
            user_data = get_user_by_username(username)
            if not user_data:
                flash('Error fetching user data. Please try again.', 'danger')
                return render_template('login.html', form=form)
                
            update_last_login(username)
            user = UserLogin(user_data)
            login_user(user)
            
            next_page = request.args.get('next')
            flash('Login successful!', 'success')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Login unsuccessful. Please check username and password.', 'danger')
    
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    # Get user's payment history
    payments = get_user_payments(current_user.username)
    return render_template('dashboard.html', payments=payments)

@app.route('/subscription')
@login_required
def subscription():
    return render_template('subscription.html')

@app.route('/process-payment/<int:amount>/<subscription_type>')
@login_required
def process_payment(amount, subscription_type):
    """Process payment asynchronously and notify the user"""
    # Get callback URL
    callback_url = get_callback_url()
    logger.info(f"Using callback URL: {callback_url}")
    
    # Initiate payment asynchronously
    checkout_id, message, success = payment_processor.initiate_payment_async(
        mongo_db,
        current_user.username,
        amount,
        subscription_type,
        callback_url
    )
    
    if success:
        # Show an informative flash message instead of a separate payment page
        flash(f'Payment request sent! Please check your phone ({current_user.phone_number}) and confirm the M-Pesa payment of {Config.CURRENCY} {amount}. This may take a few moments to process.', 'info')
        
        # Store the checkout ID in session for tracking
        session['active_payment_id'] = checkout_id
        session['payment_timestamp'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Just redirect to dashboard where status will be checked via JavaScript
        return redirect(url_for('dashboard'))
    else:
        # Payment failed or error occurred
        flash(f'Payment processing failed: {message}', 'danger')
        return redirect(url_for('subscription'))

@app.route('/payment-callback', methods=['POST'])
def payment_callback():
    """
    Handle payment callbacks from M-PESA API
    This endpoint will be called by the payment provider when payment status changes
    """
    try:
        # Get and log the callback data
        callback_data = request.json
        logger.info(f"Received payment callback: {callback_data}")
        
        # Process the callback
        success, message = payment_processor.process_payment_callback(mongo_db, callback_data)
        
        # Return appropriate response
        if success:
            return jsonify({'status': 'success', 'message': message}), 200
        else:
            return jsonify({'status': 'error', 'message': message}), 400
    except Exception as e:
        logger.error(f"Error handling payment callback: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/check-payment-status/<checkout_id>')
def check_payment_status(checkout_id):
    """
    Check payment status endpoint for AJAX polling
    This endpoint is called by the frontend to check payment status
    """
    try:
        # Get current user's username if authenticated
        username = current_user.username if current_user.is_authenticated else None
        
        # Check transaction status
        status_data = payment_processor.get_transaction_status(mongo_db, checkout_id, username)
        
        # Return status data
        return jsonify(status_data)
    except Exception as e:
        logger.error(f"Error checking payment status: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error checking payment status: {str(e)}'
        })

@app.route('/cancel-payment/<checkout_id>')
@login_required
def cancel_payment(checkout_id):
    """Cancel a pending payment"""
    try:
        # Get transaction
        transaction = mongo_db.transactions.find_one({'checkout_id': checkout_id})
        
        if not transaction:
            # Try with real_checkout_id
            transaction = mongo_db.transactions.find_one({'real_checkout_id': checkout_id})
            
        if not transaction:
            flash('Transaction not found.', 'danger')
            return redirect(url_for('dashboard'))
        
        # Check if user is authorized to cancel this transaction
        if transaction['username'] != current_user.username:
            flash('You are not authorized to cancel this payment.', 'danger')
            return redirect(url_for('dashboard'))
        
        # Check if transaction can be cancelled
        if transaction['status'] not in ['queued', 'pending', 'processing']:
            flash(f'Cannot cancel payment with status: {transaction["status"]}', 'warning')
            return redirect(url_for('dashboard'))
        
        # Update transaction status
        mongo_db.transactions.update_one(
            {'_id': transaction['_id']},
            {'$set': {
                'status': 'cancelled',
                'error': 'Cancelled by user',
                'updated_at': datetime.now()
            }}
        )
        
        # Update payment status
        mongo_db.payments.update_one(
            {'checkout_id': checkout_id},
            {'$set': {
                'status': 'cancelled',
                'reference': 'Cancelled by user'
            }}
        )
        
        # Update in-memory tracking
        if checkout_id in payment_processor.transaction_status:
            payment_processor.transaction_status[checkout_id] = 'cancelled'
            
        # Clear session tracking
        if 'active_payment_id' in session and session['active_payment_id'] == checkout_id:
            session.pop('active_payment_id', None)
            session.pop('payment_timestamp', None)
            
        flash('Payment has been cancelled.', 'info')
        return redirect(url_for('dashboard'))
    except Exception as e:
        logger.error(f"Error cancelling payment: {str(e)}")
        flash(f'Error cancelling payment: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/payment-success/<checkout_id>')
@login_required
def payment_success(checkout_id):
    """Show payment success page"""
    try:
        # Get transaction - try both checkout_id and real_checkout_id
        transaction = mongo_db.transactions.find_one({'checkout_id': checkout_id})
        if not transaction:
            transaction = mongo_db.transactions.find_one({'real_checkout_id': checkout_id})
            
        if not transaction:
            flash('Transaction not found.', 'danger')
            return redirect(url_for('dashboard'))
        
        # Check if user is authorized to view this transaction
        if transaction['username'] != current_user.username:
            flash('You are not authorized to view this payment.', 'danger')
            return redirect(url_for('dashboard'))
        
        # Check if transaction is successful
        if transaction['status'] != 'completed':
            flash(f'Payment is not completed. Current status: {transaction["status"]}', 'warning')
            return redirect(url_for('dashboard'))
        
        # Get payment details
        payment = None
        if 'real_checkout_id' in transaction and transaction['real_checkout_id']:
            # Try first with real_checkout_id
            payment = mongo_db.payments.find_one({'checkout_id': transaction['real_checkout_id']})
            
        if not payment:
            # Fallback to original checkout_id
            payment = mongo_db.payments.find_one({'checkout_id': checkout_id})
        
        if not payment:
            flash('Payment record not found.', 'warning')
            return redirect(url_for('dashboard'))
        
        # Clear session tracking
        if 'active_payment_id' in session:
            session.pop('active_payment_id', None)
            session.pop('payment_timestamp', None)
        
        # Show success message directly on dashboard
        subscription_type = transaction['subscription_type']
        amount = transaction['amount']
        words_added = Config.BASIC_SUBSCRIPTION_WORDS if subscription_type == 'basic' else Config.PREMIUM_SUBSCRIPTION_WORDS
        
        flash(f'Payment of {Config.CURRENCY} {amount} was successful! {words_added} words have been added to your account.', 'success')
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        logger.error(f"Error showing payment success: {str(e)}")
        flash(f'Error showing payment success: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/payment-failed/<checkout_id>')
@login_required
def payment_failed(checkout_id):
    """Show payment failed information"""
    try:
        # Get transaction - try both checkout_id and real_checkout_id
        transaction = mongo_db.transactions.find_one({'checkout_id': checkout_id})
        if not transaction:
            transaction = mongo_db.transactions.find_one({'real_checkout_id': checkout_id})
            
        if not transaction:
            flash('Transaction not found.', 'danger')
            return redirect(url_for('dashboard'))
        
        # Check if user is authorized to view this transaction
        if transaction['username'] != current_user.username:
            flash('You are not authorized to view this payment.', 'danger')
            return redirect(url_for('dashboard'))
        
        # Check if transaction has failed
        if transaction['status'] not in ['failed', 'timeout', 'cancelled', 'error']:
            flash(f'Payment has not failed. Current status: {transaction["status"]}', 'warning')
            return redirect(url_for('dashboard'))
        
        # Clear session tracking
        if 'active_payment_id' in session:
            session.pop('active_payment_id', None)
            session.pop('payment_timestamp', None)
        
        # Show failure message directly on dashboard
        reason = transaction.get('error', 'Unknown reason')
        flash(f'Payment failed: {reason}. Please try again or contact support if the issue persists.', 'danger')
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        logger.error(f"Error showing payment failure: {str(e)}")
        flash(f'Error showing payment failure: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

# Add a route to test MongoDB connection
@app.route('/test-db')
def test_db():
    try:
        if mongo_db is None:
            return jsonify({
                'status': 'error',
                'message': 'MongoDB connection not established'
            })
            
        # Test the connection by performing a simple operation
        mongo_db.command('ping')
        
        # Get some basic stats about the database
        db_stats = mongo_db.command('dbStats')
        
        return jsonify({
            'status': 'success',
            'message': 'MongoDB connection is working',
            'database': mongo_db.name,
            'collections': db_stats.get('collections', 0),
            'documents': db_stats.get('objects', 0)
        })
    except Exception as e:
        logger.error(f"Error testing database: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'MongoDB connection error: {str(e)}'
        })

# Add a route to test payment API
@app.route('/test-payment-api')
@login_required
def test_payment_api():
    try:
        # Get callback URL
        callback_url = get_callback_url()
        
        # Log test information
        logger.info(f"Testing payment API with callback URL: {callback_url}")
        logger.info(f"API Key: {app.config.get('API_KEY')}")
        logger.info(f"API Base URL: {app.config.get('API_BASE_URL')}")
        
        # Get user phone number
        user = get_user_by_username(current_user.username)
        phone = user['phone_number'] if user else "NA"
        
        # Format phone for display
        formatted_phone = payment_processor.format_phone_for_api(phone)
        
        return jsonify({
            'status': 'success',
            'message': 'Payment API test page',
            'api_key': app.config.get('API_KEY'),
            'api_base_url': app.config.get('API_BASE_URL'),
            'callback_url': callback_url,
            'phone': phone,
            'formatted_phone': formatted_phone
        })
    except Exception as e:
        logger.error(f"Error testing payment API: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error testing payment API: {str(e)}'
        })

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error_code=404, error_message='Page not found'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error_code=500, error_message='Internal server error'), 500

# Configuration for production
if __name__ == '__main__':
    try:
        # Get appropriate port
        port = int(os.environ.get('PORT', 5000))
        
        # Start the Flask application
        app.run(debug=Config.DEBUG, host='0.0.0.0', port=port)
    except KeyboardInterrupt:
        # Stop payment processor on shutdown
        if 'payment_worker_thread' in locals():
            logger.info("Stopping payment processor...")
            payment_processor.stop_payment_processor()
            logger.info("Payment processor stopped")
    except Exception as e:
        logger.error(f"Error starting application: {str(e)}")
