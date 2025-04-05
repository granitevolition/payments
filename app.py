import os
import json
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
import pymongo
from flask_bcrypt import Bcrypt
from config import Config

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
    # Create MongoDB client with explicit timeout
    mongo_uri = app.config.get('MONGO_URI')
    logger.info(f"Connecting to MongoDB: {mongo_uri}")
    
    # Create a direct connection to MongoDB
    mongo_client = pymongo.MongoClient(
        mongo_uri,
        serverSelectionTimeoutMS=5000,  # 5 second timeout for server selection
        connectTimeoutMS=5000,          # 5 second timeout for connection
        socketTimeoutMS=30000           # 30 second timeout for socket operations
    )
    
    # Test the connection
    mongo_client.admin.command('ping')
    logger.info("MongoDB connection successful!")
    
    # Get the database
    mongo_db = mongo_client.get_database()
    logger.info(f"Connected to database: {mongo_db.name}")
    
    # Create indexes for better performance
    mongo_db.users.create_index([('username', 1)], unique=True)
    mongo_db.payments.create_index([('checkout_id', 1)])
    mongo_db.transactions.create_index([('checkout_id', 1)])
    logger.info("MongoDB indexes created successfully")
    
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

def create_payment(username, amount, subscription_type, status='pending', reference='N/A', checkout_id='N/A'):
    """Create a new payment record"""
    try:
        if mongo_db is None:
            logger.error("MongoDB not available when creating payment")
            return None
            
        payment = {
            'username': username,
            'amount': amount,
            'reference': reference,
            'checkout_id': checkout_id,
            'subscription_type': subscription_type,
            'timestamp': datetime.now(),
            'status': status
        }
        result = mongo_db.payments.insert_one(payment)
        payment['_id'] = result.inserted_id
        return payment
    except Exception as e:
        logger.error(f"Error creating payment: {str(e)}")
        return None

def update_payment_status(checkout_id, status, reference=None):
    """Update payment status"""
    try:
        if mongo_db is None:
            logger.error("MongoDB not available when updating payment status")
            return
            
        update_data = {'status': status}
        if reference:
            update_data['reference'] = reference
        
        mongo_db.payments.update_one(
            {'checkout_id': checkout_id},
            {'$set': update_data}
        )
    except Exception as e:
        logger.error(f"Error updating payment status: {str(e)}")

def create_transaction(checkout_id, data):
    """Create a new transaction record"""
    try:
        if mongo_db is None:
            logger.error("MongoDB not available when creating transaction")
            return None
            
        transaction = {
            'checkout_id': checkout_id,
            **data,
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
        result = mongo_db.transactions.insert_one(transaction)
        transaction['_id'] = result.inserted_id
        return transaction
    except Exception as e:
        logger.error(f"Error creating transaction: {str(e)}")
        return None

def get_transaction(checkout_id):
    """Get a transaction by checkout ID"""
    try:
        if mongo_db is None:
            logger.error("MongoDB not available when getting transaction")
            return None
            
        return mongo_db.transactions.find_one({'checkout_id': checkout_id})
    except Exception as e:
        logger.error(f"Error in get_transaction: {str(e)}")
        return None

def update_transaction_status(checkout_id, status, reference=None):
    """Update transaction status"""
    try:
        if mongo_db is None:
            logger.error("MongoDB not available when updating transaction status")
            return
            
        update_data = {
            'status': status,
            'updated_at': datetime.now()
        }
        if reference:
            update_data['reference'] = reference
        
        mongo_db.transactions.update_one(
            {'checkout_id': checkout_id},
            {'$set': update_data}
        )
    except Exception as e:
        logger.error(f"Error updating transaction status: {str(e)}")

# Helper for formatting phone numbers
def format_phone_for_api(phone):
    """Format phone number to 07XXXXXXXX format required by API"""
    # Ensure phone is a string
    phone = str(phone)

    # Remove any spaces, quotes or special characters
    phone = ''.join(c for c in phone if c.isdigit())

    # If it starts with 254, convert to local format
    if phone.startswith('254'):
        phone = '0' + phone[3:]

    # Make sure it starts with 0
    if not phone.startswith('0'):
        phone = '0' + phone

    # Ensure it's exactly 10 digits (07XXXXXXXX)
    if len(phone) > 10:
        phone = phone[:10]
    elif len(phone) < 10:
        logger.warning(f"Warning: Phone number {phone} is shorter than expected")

    logger.info(f"Original phone: {phone} -> Formatted for API: {phone}")
    return phone

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

@app.route('/use-words', methods=['GET', 'POST'])
@login_required
def use_words():
    from forms import UseWordsForm
    form = UseWordsForm()
    
    if form.validate_on_submit():
        words_to_use = form.words_to_use.data
        
        # Attempt to consume words
        success, remaining = consume_words(current_user.username, words_to_use)
        
        if success:
            flash(f'Successfully used {words_to_use} words. You now have {remaining} words remaining.', 'success')
            # Update current_user's words_remaining attribute
            current_user.user_data['words_remaining'] = remaining
            current_user.words_remaining = remaining
        else:
            flash(f'Not enough words! You have {remaining} words remaining.', 'danger')
        
        return redirect(url_for('dashboard'))
    
    return render_template('use_words.html', form=form)

@app.route('/process-payment/<int:amount>/<subscription_type>')
@login_required
def process_payment(amount, subscription_type):
    try:
        # For demo purposes, create a simple successful payment
        checkout_id = f"demo_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Record the payment
        payment = create_payment(
            current_user.username,
            amount,
            subscription_type,
            'completed',
            'DEMO_PAYMENT',
            checkout_id
        )
        
        # Create transaction record
        transaction_data = {
            'checkout_id': checkout_id,
            'username': current_user.username,
            'amount': amount,
            'phone': current_user.phone_number,
            'subscription_type': subscription_type,
            'status': 'completed',
            'reference': 'DEMO_PAYMENT'
        }
        create_transaction(checkout_id, transaction_data)
        
        # Update word count
        words_to_add = 100 if subscription_type == 'basic' else 1000
        new_word_count = update_word_count(current_user.username, words_to_add)
        
        # Show success message
        flash(f'Payment processed successfully! {words_to_add} words have been added to your account.', 'success')
        return redirect(url_for('dashboard'))
    
    except Exception as e:
        logger.error(f"Error processing payment: {str(e)}")
        flash(f'Error processing payment: {str(e)}', 'danger')
        return redirect(url_for('subscription'))

@app.route('/payment-callback', methods=['POST'])
def payment_callback():
    # Get callback data
    try:
        callback_data = request.json
        logger.info(f"Received payment callback: {callback_data}")
        
        # Get checkout ID from callback data
        checkout_id = callback_data.get('CheckoutRequestID')
        if not checkout_id:
            logger.error("No checkout ID in callback data")
            return jsonify({'status': 'error', 'message': 'No checkout ID provided'}), 400

        # Get transaction
        transaction = get_transaction(checkout_id)
        if not transaction:
            logger.error(f"Transaction not found for checkout ID: {checkout_id}")
            return jsonify({'status': 'error', 'message': 'Transaction not found'}), 400

        # Update transaction status
        reference = callback_data.get('reference', 'N/A')
        update_transaction_status(checkout_id, 'completed', reference)

        # Update payment record
        update_payment_status(checkout_id, 'completed', reference)

        # Update word count
        username = transaction['username']
        subscription_type = transaction['subscription_type']
        words_to_add = 100 if subscription_type == 'basic' else 1000
        update_word_count(username, words_to_add)
        
        return jsonify({'status': 'success'}), 200
    except Exception as e:
        logger.error(f"Error processing callback: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/check-payment-status/<checkout_id>')
@login_required
def check_payment_status(checkout_id):
    # Check transaction status
    transaction = get_transaction(checkout_id)
    
    if not transaction:
        return jsonify({
            'status': 'error',
            'message': 'Transaction not found'
        })
    
    # If transaction is completed
    if transaction['status'] == 'completed':
        return jsonify({
            'status': 'completed',
            'message': 'Payment completed successfully!'
        })
    
    # If transaction is cancelled or failed
    if transaction['status'] in ['cancelled', 'failed']:
        return jsonify({
            'status': transaction['status'],
            'message': f'Payment {transaction["status"]}'
        })
    
    # If transaction is still pending
    return jsonify({
        'status': 'pending',
        'message': 'Waiting for payment...'
    })

@app.route('/cancel-payment/<checkout_id>')
@login_required
def cancel_payment(checkout_id):
    # Update transaction status
    update_transaction_status(checkout_id, 'cancelled')
    
    # Update payment status
    update_payment_status(checkout_id, 'cancelled')
    
    flash('Payment has been cancelled.', 'warning')
    return redirect(url_for('subscription'))

@app.route('/payment-success/<checkout_id>')
@login_required
def payment_success(checkout_id):
    # Get transaction
    transaction = get_transaction(checkout_id)
    
    if not transaction or transaction['status'] != 'completed':
        flash('Invalid or incomplete transaction.', 'danger')
        return redirect(url_for('dashboard'))
    
    # Show success message
    subscription_type = transaction['subscription_type']
    amount = transaction['amount']
    words_added = 100 if subscription_type == 'basic' else 1000
    
    flash(f'Payment of ${amount} for {subscription_type} subscription was successful! {words_added} words have been added to your account.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/payment-failed/<checkout_id>')
@login_required
def payment_failed(checkout_id):
    # Get transaction
    transaction = get_transaction(checkout_id)
    
    if not transaction:
        flash('Transaction not found.', 'danger')
    else:
        flash(f'Payment failed or was cancelled.', 'danger')
    
    return redirect(url_for('subscription'))

@app.route('/payment-timeout/<checkout_id>')
@login_required
def payment_timeout(checkout_id):
    # Update transaction status if it's still pending
    transaction = get_transaction(checkout_id)
    
    if transaction and transaction['status'] == 'pending':
        update_transaction_status(checkout_id, 'timeout')
        update_payment_status(checkout_id, 'timeout')
    
    flash('Payment process timed out. If you completed the payment, it may still process. Please check your dashboard later.', 'warning')
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

# Error handlers
@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', error_code=404, error_message='Page not found'), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template('error.html', error_code=500, error_message='Internal server error'), 500

# Run the app
if __name__ == '__main__':
    # Start the Flask application
    app.run(debug=Config.DEBUG, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
