import os
import json
import logging
from datetime import datetime, timedelta
import pymongo
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from bson.objectid import ObjectId

from config import Config
from forms import RegistrationForm, LoginForm, UseWordsForm
from utils import format_phone_for_api

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Create MongoDB client directly
# Ensure MONGO_URI is set correctly
if not app.config.get('MONGO_URI'):
    logger.error("MONGO_URI is not set in config!")
else:
    logger.info(f"MONGO_URI is set to: {app.config.get('MONGO_URI')}")

# Initialize MongoDB and Flask extensions
mongo = PyMongo(app)
bcrypt = Bcrypt(app)

# Check MongoDB connection
try:
    # Force a command to check the connection
    mongo.db.command('ping')
    logger.info("MongoDB connection successful!")
    
    # Create indexes for better performance
    mongo.db.users.create_index([('username', 1)], unique=True)
    mongo.db.payments.create_index([('checkout_id', 1)], unique=True)
    mongo.db.transactions.create_index([('checkout_id', 1)], unique=True)
    logger.info("MongoDB indexes created successfully")
except Exception as e:
    logger.error(f"MongoDB connection error: {str(e)}")

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# Import models after initializing mongo
from models import User, Payment, Transaction

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
        user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
        if not user_data:
            return None
        return UserLogin(user_data)
    except Exception as e:
        logger.error(f"Error loading user: {str(e)}")
        return None

# ------------------- Helper functions -------------------

def create_user(username, password, phone_number):
    """Create a new user"""
    try:
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        user = {
            'username': username,
            'password': hashed_password,
            'phone_number': phone_number,
            'words_remaining': 0,
            'created_at': datetime.now(),
            'last_login': datetime.now()
        }
        result = mongo.db.users.insert_one(user)
        user['_id'] = result.inserted_id
        return user
    except Exception as e:
        logger.error(f"Error creating user: {str(e)}")
        raise

def get_user_by_username(username):
    """Get a user by username"""
    try:
        return mongo.db.users.find_one({'username': username})
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
        mongo.db.users.update_one(
            {'username': username},
            {'$set': {'last_login': datetime.now()}}
        )
    except Exception as e:
        logger.error(f"Error updating last login: {str(e)}")

def update_word_count(username, words_to_add):
    """Update word count for a user"""
    try:
        user = get_user_by_username(username)
        if not user:
            return None
        
        current_words = user.get('words_remaining', 0)
        new_word_count = current_words + words_to_add
        
        mongo.db.users.update_one(
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
        user = get_user_by_username(username)
        if not user:
            return False, 0
        
        current_words = user.get('words_remaining', 0)
        
        if current_words < words_to_use:
            return False, current_words
        
        new_word_count = current_words - words_to_use
        
        mongo.db.users.update_one(
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
        return list(mongo.db.payments.find({'username': username}).sort('timestamp', -1))
    except Exception as e:
        logger.error(f"Error getting user payments: {str(e)}")
        return []

def create_payment(username, amount, subscription_type, status='pending', reference='N/A', checkout_id='N/A'):
    """Create a new payment record"""
    try:
        payment = {
            'username': username,
            'amount': amount,
            'reference': reference,
            'checkout_id': checkout_id,
            'subscription_type': subscription_type,
            'timestamp': datetime.now(),
            'status': status
        }
        result = mongo.db.payments.insert_one(payment)
        payment['_id'] = result.inserted_id
        return payment
    except Exception as e:
        logger.error(f"Error creating payment: {str(e)}")
        return None

def update_payment_status(checkout_id, status, reference=None):
    """Update payment status"""
    try:
        update_data = {'status': status}
        if reference:
            update_data['reference'] = reference
        
        mongo.db.payments.update_one(
            {'checkout_id': checkout_id},
            {'$set': update_data}
        )
    except Exception as e:
        logger.error(f"Error updating payment status: {str(e)}")

def create_transaction(checkout_id, data):
    """Create a new transaction record"""
    try:
        transaction = {
            'checkout_id': checkout_id,
            **data,
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
        result = mongo.db.transactions.insert_one(transaction)
        transaction['_id'] = result.inserted_id
        return transaction
    except Exception as e:
        logger.error(f"Error creating transaction: {str(e)}")
        return None

def get_transaction(checkout_id):
    """Get a transaction by checkout ID"""
    try:
        return mongo.db.transactions.find_one({'checkout_id': checkout_id})
    except Exception as e:
        logger.error(f"Error in get_transaction: {str(e)}")
        return None

def update_transaction_status(checkout_id, status, reference=None):
    """Update transaction status"""
    try:
        update_data = {
            'status': status,
            'updated_at': datetime.now()
        }
        if reference:
            update_data['reference'] = reference
        
        mongo.db.transactions.update_one(
            {'checkout_id': checkout_id},
            {'$set': update_data}
        )
    except Exception as e:
        logger.error(f"Error updating transaction status: {str(e)}")

# ------------------- Routes -------------------

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
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
    
    form = LoginForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        
        # Check if user exists and password is correct
        if check_password(username, password):
            user_data = get_user_by_username(username)
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
        # Build callback URL
        host = request.host_url.rstrip('/')
        callback_url = f"{host}/payment-callback"
        
        # Create a dummy successful payment for now (to be replaced with real payment processing)
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
