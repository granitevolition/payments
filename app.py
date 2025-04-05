import os
import json
import logging
from datetime import datetime, timedelta
from flask import Flask, render_template, redirect, url_for, request, flash, jsonify, session
from flask_login import LoginManager, login_user, logout_user, login_required, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId

from config import Config
from models import mongo, bcrypt, User, Payment, Transaction
from forms import RegistrationForm, LoginForm, UseWordsForm
from utils import initiate_payment, process_payment_callback, format_phone_for_api

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(Config)

# Ensure MONGO_URI is set correctly
if not app.config.get('MONGO_URI'):
    logger.error("MONGO_URI is not set in config!")
else:
    logger.info(f"MONGO_URI is set to: {app.config.get('MONGO_URI')}")

# Initialize MongoDB with explicit URI
app.config['MONGO_URI'] = Config.MONGO_URI
mongo.init_app(app)

# Initialize Bcrypt
bcrypt.init_app(app)

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
    user_data = User.get_by_id(ObjectId(user_id))
    if not user_data:
        return None
    return UserLogin(user_data)

# Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    form = RegistrationForm()
    
    if form.validate_on_submit():
        username = form.username.data
        password = form.password.data
        phone_number = form.phone_number.data
        
        # Create user
        user = User.create(username, password, phone_number)
        flash(f'Account created for {username}! You can now log in.', 'success')
        return redirect(url_for('login'))
    
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
        if User.check_password(username, password):
            user_data = User.get_by_username(username)
            User.update_last_login(username)
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
    payments = Payment.get_user_payments(current_user.username)
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
        success, remaining = User.consume_words(current_user.username, words_to_use)
        
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
    # Build callback URL
    host = request.host_url.rstrip('/')
    callback_url = f"{host}/payment-callback"
    
    # Initiate payment
    checkout_id, message = initiate_payment(current_user.username, amount, subscription_type, callback_url)
    
    if checkout_id:
        # If payment was immediately completed
        if "completed successfully" in message:
            flash(f'Payment processed successfully!', 'success')
            return redirect(url_for('dashboard'))
        
        # If payment was initiated and needs user action
        user = User.get_by_username(current_user.username)
        return render_template(
            'payment_processing.html',
            checkout_id=checkout_id,
            amount=amount,
            phone_number=user['phone_number']
        )
    else:
        # If payment initiation failed
        flash(f'Payment failed: {message}', 'danger')
        return redirect(url_for('subscription'))

@app.route('/payment-callback', methods=['POST'])
def payment_callback():
    # Get callback data
    try:
        callback_data = request.json
        logger.info(f"Received payment callback: {callback_data}")
        
        # Process callback
        if process_payment_callback(callback_data):
            return jsonify({'status': 'success'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Failed to process callback'}), 400
    except Exception as e:
        logger.error(f"Error processing callback: {str(e)}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/check-payment-status/<checkout_id>')
@login_required
def check_payment_status(checkout_id):
    # Check transaction status
    transaction = Transaction.get(checkout_id)
    
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
    Transaction.update_status(checkout_id, 'cancelled')
    
    # Update payment status
    Payment.update_status(checkout_id, 'cancelled')
    
    flash('Payment has been cancelled.', 'warning')
    return redirect(url_for('subscription'))

@app.route('/payment-success/<checkout_id>')
@login_required
def payment_success(checkout_id):
    # Get transaction
    transaction = Transaction.get(checkout_id)
    
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
    transaction = Transaction.get(checkout_id)
    
    if not transaction:
        flash('Transaction not found.', 'danger')
    else:
        flash(f'Payment failed or was cancelled.', 'danger')
    
    return redirect(url_for('subscription'))

@app.route('/payment-timeout/<checkout_id>')
@login_required
def payment_timeout(checkout_id):
    # Update transaction status if it's still pending
    transaction = Transaction.get(checkout_id)
    
    if transaction and transaction['status'] == 'pending':
        Transaction.update_status(checkout_id, 'timeout')
        Payment.update_status(checkout_id, 'timeout')
    
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
    # Create database collections if they don't exist
    with app.app_context():
        # Ensure indexes for performance
        try:
            mongo.db.users.create_index([('username', 1)], unique=True)
            mongo.db.payments.create_index([('checkout_id', 1)], unique=True)
            mongo.db.transactions.create_index([('checkout_id', 1)], unique=True)
            logger.info("MongoDB indexes created successfully")
        except Exception as e:
            logger.error(f"Error creating MongoDB indexes: {str(e)}")
    
    # Start the Flask application
    app.run(debug=Config.DEBUG, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
