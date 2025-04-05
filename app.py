import os
import json
import logging
import time
import requests
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
    
    # Define a database name to use
    DB_NAME = "lipia_payments"
    
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
    
    # Get the database - specify the database name explicitly
    mongo_db = mongo_client[DB_NAME]
    logger.info(f"Connected to database: {DB_NAME}")
    
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
        return True
    except Exception as e:
        logger.error(f"Error updating transaction status: {str(e)}")
        return False

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

# Payment processing function
def initiate_mpesa_payment(username, amount, subscription_type):
    """
    Initiate an M-PESA payment request
    Returns (checkout_id, status_message, success_flag)
    """
    try:
        # Get user data
        user = get_user_by_username(username)
        if not user:
            logger.error(f"User {username} not found for payment")
            return None, "User not found", False
        
        # Format phone number for API
        phone = format_phone_for_api(user['phone_number'])
        
        # Get API key and base URL
        api_key = app.config.get('API_KEY')
        api_base_url = app.config.get('API_BASE_URL')
        
        # Check if API key is set
        if not api_key:
            logger.error("API key not set for payment")
            return None, "API key not configured", False
            
        # Build callback URL - use the public URL from config or fallback to the request host
        callback_url = app.config.get('CALLBACK_URL')
        if not callback_url:
            # Use request hostname if available
            if request:
                host = request.host_url.rstrip('/')
                callback_url = f"{host}/payment-callback"
            else:
                callback_url = "https://example.com/payment-callback"  # Fallback
        
        # Prepare API request
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        # Add checkout_request_id to ensure idempotency
        checkout_request_id = f"LIP{int(time.time())}{username[:5]}"
        
        payload = {
            'phone': phone,
            'amount': str(amount),
            'callback_url': callback_url
        }
        
        logger.info(f"Initiating payment: {phone}, ${amount}, {subscription_type}, {checkout_request_id}")
        
        # Start MongoDB transaction
        with mongo_client.start_session() as session:
            # Record pending transaction
            transaction_data = {
                'checkout_id': checkout_request_id,
                'username': username,
                'amount': amount,
                'phone': phone,
                'subscription_type': subscription_type,
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'status': 'pending'
            }
            
            # Create transaction and payment records
            session.start_transaction()
            try:
                # Create payment record
                create_payment(
                    username,
                    amount,
                    subscription_type,
                    'pending',
                    'N/A',
                    checkout_request_id,
                )
                
                # Create transaction record
                create_transaction(checkout_request_id, transaction_data)
                
                # Send payment request to API
                response = requests.post(
                    f"{api_base_url}/request/stk",
                    headers=headers,
                    json=payload,
                    timeout=30  # Timeout after 30 seconds
                )
                
                logger.info(f"Payment API response: {response.status_code}: {response.text}")
                
                # Process response
                if response.status_code == 200:
                    response_data = response.json()
                    
                    # Check for successful immediate response
                    if response_data.get('message') == 'callback received successfully' and 'data' in response_data:
                        # Payment was immediately successful
                        data = response_data['data']
                        real_checkout_id = data.get('CheckoutRequestID', checkout_request_id)
                        reference = data.get('refference', 'DIRECT')  # Note: API uses "refference" with two f's
                        
                        # Update checkout_id if the API returned a different one
                        if real_checkout_id != checkout_request_id:
                            # Update our records to use the API's checkout ID
                            update_transaction_status(checkout_request_id, 'completed', reference)
                            update_payment_status(checkout_request_id, 'completed', reference)
                            
                            # Add words to user's account
                            words_to_add = 100 if subscription_type == 'basic' else 1000
                            update_word_count(username, words_to_add)
                            
                            session.commit_transaction()
                            return real_checkout_id, "Payment completed successfully", True
                        
                    elif 'data' in response_data and 'CheckoutRequestID' in response_data['data']:
                        # Payment initiated, waiting for user action and callback
                        real_checkout_id = response_data['data']['CheckoutRequestID']
                        
                        # Update checkout_id if the API returned a different one
                        if real_checkout_id != checkout_request_id:
                            # Update our transaction and payment records with the new ID
                            transaction_data['checkout_id'] = real_checkout_id
                            create_transaction(real_checkout_id, transaction_data)
                            
                            # Create a new payment record with the correct ID
                            create_payment(
                                username,
                                amount,
                                subscription_type,
                                'pending',
                                'N/A',
                                real_checkout_id
                            )
                            
                            # Mark the original records as replaced
                            update_transaction_status(checkout_request_id, 'replaced', f"replaced by {real_checkout_id}")
                            update_payment_status(checkout_request_id, 'replaced', f"replaced by {real_checkout_id}")
                            
                        session.commit_transaction()
                        return real_checkout_id, "Payment initiated, waiting for confirmation", True
                    else:
                        # Payment failed
                        error_msg = response_data.get('message', 'Unknown payment error')
                        update_transaction_status(checkout_request_id, 'failed', error_msg)
                        update_payment_status(checkout_request_id, 'failed', error_msg)
                        session.commit_transaction()
                        return checkout_request_id, f"Payment failed: {error_msg}", False
                else:
                    # Payment request failed
                    error_msg = f"Payment request failed with status code: {response.status_code}"
                    update_transaction_status(checkout_request_id, 'failed', error_msg)
                    update_payment_status(checkout_request_id, 'failed', error_msg)
                    session.commit_transaction()
                    return checkout_request_id, error_msg, False
                    
            except Exception as e:
                # Abort transaction and roll back changes
                session.abort_transaction()
                logger.error(f"Payment transaction error: {str(e)}")
                return checkout_request_id, f"Payment error: {str(e)}", False
    
    except requests.exceptions.Timeout:
        logger.error("Payment API timeout")
        return None, "Payment request timed out. Please try again.", False
        
    except Exception as e:
        logger.error(f"Payment initialization error: {str(e)}")
        return None, f"Payment error: {str(e)}", False

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
    # Use the real payment API
    checkout_id, message, success = initiate_mpesa_payment(
        current_user.username, 
        amount, 
        subscription_type
    )
    
    if success:
        # If payment was immediately successful
        if "completed successfully" in message:
            # Show success message
            words_to_add = 100 if subscription_type == 'basic' else 1000
            flash(f'Payment processed successfully! {words_to_add} words have been added to your account.', 'success')
            return redirect(url_for('dashboard'))
        else:
            # Payment is pending, show payment processing page
            return render_template(
                'payment_processing.html',
                checkout_id=checkout_id,
                amount=amount,
                phone_number=current_user.phone_number,
                subscription_type=subscription_type
            )
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
        
        # Extract checkout ID from callback data
        checkout_id = callback_data.get('CheckoutRequestID')
        if not checkout_id:
            logger.error("No checkout ID in callback data")
            return jsonify({'status': 'error', 'message': 'Missing checkout ID'}), 400
            
        # Get transaction
        transaction = get_transaction(checkout_id)
        if not transaction:
            logger.error(f"Transaction not found for checkout ID: {checkout_id}")
            return jsonify({'status': 'error', 'message': 'Transaction not found'}), 404
            
        # Extract reference number (for tracking)
        reference = callback_data.get('reference', callback_data.get('refference', 'CB-REF'))
        
        # Get status from callback
        # This will depend on the exact format your payment provider uses
        success = callback_data.get('success', callback_data.get('status') == 'success')
        
        # Start MongoDB transaction for atomicity
        with mongo_client.start_session() as session:
            session.start_transaction()
            try:
                if success:
                    # Payment successful
                    # Update transaction status
                    update_transaction_status(checkout_id, 'completed', reference)
                    
                    # Update payment record
                    update_payment_status(checkout_id, 'completed', reference)
                    
                    # Get transaction details for processing
                    username = transaction['username']
                    subscription_type = transaction['subscription_type']
                    
                    # Update user's word count
                    words_to_add = 100 if subscription_type == 'basic' else 1000
                    update_word_count(username, words_to_add)
                    
                    logger.info(f"Payment successful for {username}, added {words_to_add} words")
                    session.commit_transaction()
                    return jsonify({'status': 'success'}), 200
                else:
                    # Payment failed
                    reason = callback_data.get('reason', 'Unknown failure reason')
                    
                    # Update transaction status
                    update_transaction_status(checkout_id, 'failed', reason)
                    
                    # Update payment record
                    update_payment_status(checkout_id, 'failed', reason)
                    
                    logger.warning(f"Payment failed for {transaction['username']}: {reason}")
                    session.commit_transaction()
                    return jsonify({'status': 'success'}), 200
            except Exception as e:
                # Rollback transaction on error
                session.abort_transaction()
                logger.error(f"Error processing payment callback: {str(e)}")
                return jsonify({'status': 'error', 'message': str(e)}), 500
    except Exception as e:
        logger.error(f"Error handling payment callback: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/check-payment-status/<checkout_id>')
@login_required
def check_payment_status(checkout_id):
    """
    Check payment status endpoint for AJAX polling
    This endpoint is called by the frontend to check payment status
    """
    try:
        # Get transaction
        transaction = get_transaction(checkout_id)
        
        if not transaction:
            return jsonify({
                'status': 'error',
                'message': 'Transaction not found'
            })
        
        # Check if user is authorized to view this transaction
        if transaction['username'] != current_user.username:
            return jsonify({
                'status': 'error',
                'message': 'Unauthorized'
            }), 403
        
        # Return transaction status
        return jsonify({
            'status': transaction['status'],
            'message': get_status_message(transaction['status']),
            'reference': transaction.get('reference', 'N/A'),
            'timestamp': transaction.get('updated_at', datetime.now()).strftime('%Y-%m-%d %H:%M:%S')
        })
    except Exception as e:
        logger.error(f"Error checking payment status: {str(e)}")
        return jsonify({
            'status': 'error',
            'message': f'Error checking payment status: {str(e)}'
        })

def get_status_message(status):
    """Get user-friendly status message"""
    status_messages = {
        'pending': 'Waiting for payment confirmation...',
        'completed': 'Payment completed successfully!',
        'failed': 'Payment failed.',
        'cancelled': 'Payment was cancelled.',
        'timeout': 'Payment request timed out.',
        'replaced': 'Payment request was replaced.',
        'error': 'An error occurred during payment processing.'
    }
    return status_messages.get(status, f'Unknown status: {status}')

@app.route('/cancel-payment/<checkout_id>')
@login_required
def cancel_payment(checkout_id):
    """Cancel a pending payment"""
    try:
        # Get transaction
        transaction = get_transaction(checkout_id)
        
        if not transaction:
            flash('Transaction not found.', 'danger')
            return redirect(url_for('dashboard'))
        
        # Check if user is authorized to cancel this transaction
        if transaction['username'] != current_user.username:
            flash('You are not authorized to cancel this payment.', 'danger')
            return redirect(url_for('dashboard'))
        
        # Check if transaction can be cancelled
        if transaction['status'] not in ['pending']:
            flash(f'Cannot cancel payment with status: {transaction["status"]}', 'warning')
            return redirect(url_for('dashboard'))
        
        # Update transaction status
        update_transaction_status(checkout_id, 'cancelled', 'Cancelled by user')
        
        # Update payment status
        update_payment_status(checkout_id, 'cancelled', 'Cancelled by user')
        
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
        # Get transaction
        transaction = get_transaction(checkout_id)
        
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
        payment = mongo_db.payments.find_one({'checkout_id': checkout_id})
        
        if not payment:
            flash('Payment record not found.', 'warning')
            return redirect(url_for('dashboard'))
        
        # Show success message
        subscription_type = transaction['subscription_type']
        amount = transaction['amount']
        words_added = 100 if subscription_type == 'basic' else 1000
        
        return render_template(
            'payment_success.html',
            transaction=transaction,
            payment=payment,
            words_added=words_added
        )
    except Exception as e:
        logger.error(f"Error showing payment success: {str(e)}")
        flash(f'Error showing payment success: {str(e)}', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/payment-failed/<checkout_id>')
@login_required
def payment_failed(checkout_id):
    """Show payment failed page"""
    try:
        # Get transaction
        transaction = get_transaction(checkout_id)
        
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
        
        # Show failure message
        return render_template(
            'payment_failed.html',
            transaction=transaction,
            reason=transaction.get('reference', 'Unknown reason')
        )
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
