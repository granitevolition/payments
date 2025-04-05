from datetime import datetime
from flask_pymongo import PyMongo
from flask_bcrypt import Bcrypt
from bson import ObjectId

mongo = PyMongo()
bcrypt = Bcrypt()

class User:
    """User model to interact with users collection in MongoDB"""
    
    @staticmethod
    def create(username, password, phone_number):
        """Create a new user"""
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
    
    @staticmethod
    def get_by_username(username):
        """Get a user by username"""
        return mongo.db.users.find_one({'username': username})
    
    @staticmethod
    def get_by_id(user_id):
        """Get a user by ID"""
        return mongo.db.users.find_one({'_id': ObjectId(user_id)})
    
    @staticmethod
    def update_word_count(username, words_to_add):
        """Update word count for a user"""
        user = mongo.db.users.find_one({'username': username})
        if not user:
            return None
        
        current_words = user.get('words_remaining', 0)
        new_word_count = current_words + words_to_add
        
        mongo.db.users.update_one(
            {'username': username},
            {'$set': {'words_remaining': new_word_count}}
        )
        
        return new_word_count
    
    @staticmethod
    def consume_words(username, words_to_use):
        """Consume words from a user's account"""
        user = mongo.db.users.find_one({'username': username})
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
    
    @staticmethod
    def check_password(username, password):
        """Check if password is correct for user"""
        user = User.get_by_username(username)
        if not user:
            return False
        
        return bcrypt.check_password_hash(user['password'], password)
    
    @staticmethod
    def update_last_login(username):
        """Update last login time for user"""
        mongo.db.users.update_one(
            {'username': username},
            {'$set': {'last_login': datetime.now()}}
        )


class Payment:
    """Payment model to interact with payments collection in MongoDB"""
    
    @staticmethod
    def create(username, amount, subscription_type, status='pending', reference='N/A', checkout_id='N/A'):
        """Create a new payment record"""
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
    
    @staticmethod
    def get_by_checkout_id(checkout_id):
        """Get a payment by checkout ID"""
        return mongo.db.payments.find_one({'checkout_id': checkout_id})
    
    @staticmethod
    def update_status(checkout_id, status, reference=None):
        """Update payment status"""
        update_data = {'status': status}
        if reference:
            update_data['reference'] = reference
        
        mongo.db.payments.update_one(
            {'checkout_id': checkout_id},
            {'$set': update_data}
        )
    
    @staticmethod
    def get_user_payments(username):
        """Get all payments for a user"""
        return list(mongo.db.payments.find({'username': username}).sort('timestamp', -1))


class Transaction:
    """Transaction model to interact with transactions collection in MongoDB"""
    
    @staticmethod
    def create(checkout_id, data):
        """Create a new transaction record"""
        transaction = {
            'checkout_id': checkout_id,
            **data,
            'created_at': datetime.now(),
            'updated_at': datetime.now()
        }
        result = mongo.db.transactions.insert_one(transaction)
        transaction['_id'] = result.inserted_id
        return transaction
    
    @staticmethod
    def get(checkout_id):
        """Get a transaction by checkout ID"""
        return mongo.db.transactions.find_one({'checkout_id': checkout_id})
    
    @staticmethod
    def update_status(checkout_id, status, reference=None):
        """Update transaction status"""
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
