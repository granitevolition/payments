import time
import json
import logging
import requests
from datetime import datetime
from bson.objectid import ObjectId
import threading
import queue
from config import Config

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Payment processing queue
payment_queue = queue.Queue()
# Transaction status tracking
transaction_status = {}
# Stop event for background worker
stop_event = threading.Event()

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

def initiate_payment_async(mongo_db, username, amount, subscription_type, callback_url):
    """
    Initiate a payment asynchronously
    This function adds the payment to a queue and returns immediately
    Returns a checkout_id for tracking the payment
    """
    try:
        # Generate a unique checkout ID
        checkout_id = f"LIP{int(time.time())}{username[:5]}"
        
        # Create initial transaction record
        transaction_data = {
            'checkout_id': checkout_id,
            'username': username,
            'amount': amount,
            'subscription_type': subscription_type,
            'timestamp': datetime.now(),
            'status': 'queued',
            'reference': 'pending',
            'callback_url': callback_url
        }
        
        # Store in MongoDB first (before adding to queue)
        if mongo_db:
            try:
                # Create transaction record
                mongo_db.transactions.insert_one(transaction_data)
                
                # Create payment record
                payment_data = {
                    'username': username,
                    'amount': amount,
                    'reference': 'N/A',
                    'checkout_id': checkout_id,
                    'subscription_type': subscription_type,
                    'timestamp': datetime.now(),
                    'status': 'queued'
                }
                mongo_db.payments.insert_one(payment_data)
                
                logger.info(f"Created initial transaction record: {checkout_id}")
            except Exception as e:
                logger.error(f"Error creating initial transaction record: {str(e)}")
        
        # Add to processing queue
        payment_queue.put(transaction_data)
        logger.info(f"Added payment to queue: {checkout_id}")
        
        # Initialize status tracking
        transaction_status[checkout_id] = 'queued'
        
        return checkout_id, "Payment queued for processing", True
        
    except Exception as e:
        logger.error(f"Error initiating async payment: {str(e)}")
        return None, f"Payment initialization error: {str(e)}", False

def process_payment_queue_worker(mongo_db):
    """
    Background worker that processes payments from the queue
    This should be run in a separate thread
    """
    logger.info("Starting payment processing background worker")
    
    while not stop_event.is_set():
        try:
            # Get transaction data from queue with a timeout
            # This allows the thread to check the stop_event regularly
            try:
                transaction_data = payment_queue.get(timeout=1)
            except queue.Empty:
                # Queue is empty, continue waiting
                continue
                
            checkout_id = transaction_data['checkout_id']
            username = transaction_data['username']
            amount = transaction_data['amount']
            subscription_type = transaction_data['subscription_type']
            callback_url = transaction_data.get('callback_url', 'https://example.com/callback')
            
            logger.info(f"Processing payment from queue: {checkout_id}")
            transaction_status[checkout_id] = 'processing'
            
            # Update MongoDB status
            if mongo_db:
                try:
                    mongo_db.transactions.update_one(
                        {'checkout_id': checkout_id},
                        {'$set': {'status': 'processing', 'updated_at': datetime.now()}}
                    )
                    mongo_db.payments.update_one(
                        {'checkout_id': checkout_id},
                        {'$set': {'status': 'processing'}}
                    )
                except Exception as e:
                    logger.error(f"Error updating transaction status: {str(e)}")
            
            # Process the actual payment
            success, result = process_payment(mongo_db, username, amount, subscription_type, 
                                             checkout_id, callback_url)
            
            # Update transaction status
            if success:
                transaction_status[checkout_id] = 'completed' if result.get('instant_success', False) else 'pending'
                logger.info(f"Payment processed successfully: {checkout_id}, status: {transaction_status[checkout_id]}")
            else:
                transaction_status[checkout_id] = 'failed'
                logger.error(f"Payment processing failed: {checkout_id}, error: {result.get('error', 'Unknown error')}")
            
            # Mark task as done
            payment_queue.task_done()
            
        except Exception as e:
            logger.error(f"Error in payment processing worker: {str(e)}")
            time.sleep(1)  # Avoid tight loop in case of recurring errors
    
    logger.info("Payment processing background worker stopped")

def process_payment(mongo_db, username, amount, subscription_type, checkout_id, callback_url):
    """
    Process a payment by calling the M-Pesa API
    Returns (success, result_dict)
    """
    try:
        # Get user data from MongoDB
        user = None
        if mongo_db:
            user = mongo_db.users.find_one({'username': username})
            if not user:
                return False, {'error': 'User not found'}
            
            # Format phone for API
            phone = format_phone_for_api(user['phone_number'])
        else:
            # For testing when MongoDB is not available
            phone = "0700000000"  # Placeholder
        
        # Get API key and base URL from config
        api_key = Config.API_KEY
        api_base_url = Config.API_BASE_URL
        
        if not api_key:
            return False, {'error': 'API key not configured'}
        
        # Prepare API request
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'phone': phone,
            'amount': str(amount),
            'callback_url': callback_url
        }
        
        logger.info(f"Sending payment request: {checkout_id}, phone: {phone}, amount: {amount}")
        
        # Send payment request to API
        response = requests.post(
            f"{api_base_url}/request/stk",
            headers=headers,
            json=payload,
            timeout=30  # 30 second timeout
        )
        
        logger.info(f"Payment API response: {checkout_id}, status: {response.status_code}, body: {response.text}")
        
        # Process response
        if response.status_code == 200:
            response_data = response.json()
            
            # Process successful response
            if mongo_db:
                # Start MongoDB transaction
                with mongo_db.client.start_session() as session:
                    session.start_transaction()
                    try:
                        # Check for successful immediate response
                        if response_data.get('message') == 'callback received successfully' and 'data' in response_data:
                            # Payment was immediately successful
                            data = response_data['data']
                            real_checkout_id = data.get('CheckoutRequestID', checkout_id)
                            reference = data.get('refference', 'DIRECT')  # Note: API uses "refference" with two f's
                            
                            # Update checkout_id if the API returned a different one
                            if real_checkout_id != checkout_id:
                                # Create new records with correct ID
                                mongo_db.transactions.update_one(
                                    {'checkout_id': checkout_id},
                                    {'$set': {
                                        'real_checkout_id': real_checkout_id,
                                        'status': 'completed',
                                        'reference': reference,
                                        'updated_at': datetime.now()
                                    }}
                                )
                                
                                mongo_db.payments.update_one(
                                    {'checkout_id': checkout_id},
                                    {'$set': {
                                        'real_checkout_id': real_checkout_id,
                                        'status': 'completed',
                                        'reference': reference
                                    }}
                                )
                            else:
                                # Update existing records
                                mongo_db.transactions.update_one(
                                    {'checkout_id': checkout_id},
                                    {'$set': {
                                        'status': 'completed',
                                        'reference': reference,
                                        'updated_at': datetime.now()
                                    }}
                                )
                                
                                mongo_db.payments.update_one(
                                    {'checkout_id': checkout_id},
                                    {'$set': {
                                        'status': 'completed',
                                        'reference': reference
                                    }}
                                )
                            
                            # Update user's word count
                            words_to_add = Config.BASIC_SUBSCRIPTION_WORDS if subscription_type == 'basic' else Config.PREMIUM_SUBSCRIPTION_WORDS
                            mongo_db.users.update_one(
                                {'username': username},
                                {'$inc': {'words_remaining': words_to_add}}
                            )
                            
                            session.commit_transaction()
                            
                            # Return success with instant success flag
                            return True, {
                                'checkout_id': real_checkout_id,
                                'message': 'Payment completed successfully',
                                'reference': reference,
                                'instant_success': True
                            }
                            
                        elif 'data' in response_data and 'CheckoutRequestID' in response_data['data']:
                            # Payment initiated, waiting for user action and callback
                            real_checkout_id = response_data['data']['CheckoutRequestID']
                            
                            # Update checkout_id if the API returned a different one
                            if real_checkout_id != checkout_id:
                                # Update existing records
                                mongo_db.transactions.update_one(
                                    {'checkout_id': checkout_id},
                                    {'$set': {
                                        'real_checkout_id': real_checkout_id,
                                        'status': 'pending',
                                        'updated_at': datetime.now()
                                    }}
                                )
                                
                                mongo_db.payments.update_one(
                                    {'checkout_id': checkout_id},
                                    {'$set': {
                                        'real_checkout_id': real_checkout_id,
                                        'status': 'pending'
                                    }}
                                )
                            else:
                                # Update existing records
                                mongo_db.transactions.update_one(
                                    {'checkout_id': checkout_id},
                                    {'$set': {
                                        'status': 'pending',
                                        'updated_at': datetime.now()
                                    }}
                                )
                                
                                mongo_db.payments.update_one(
                                    {'checkout_id': checkout_id},
                                    {'$set': {'status': 'pending'}}
                                )
                            
                            session.commit_transaction()
                            
                            # Return success but with pending status
                            return True, {
                                'checkout_id': real_checkout_id,
                                'message': 'Payment initiated, waiting for confirmation',
                                'instant_success': False
                            }
                        else:
                            # Payment failed
                            error_msg = response_data.get('message', 'Unknown payment error')
                            mongo_db.transactions.update_one(
                                {'checkout_id': checkout_id},
                                {'$set': {
                                    'status': 'failed',
                                    'error': error_msg,
                                    'updated_at': datetime.now()
                                }}
                            )
                            
                            mongo_db.payments.update_one(
                                {'checkout_id': checkout_id},
                                {'$set': {
                                    'status': 'failed',
                                    'reference': error_msg
                                }}
                            )
                            
                            session.commit_transaction()
                            
                            return False, {
                                'error': error_msg,
                                'checkout_id': checkout_id
                            }
                    except Exception as e:
                        # Abort transaction on error
                        session.abort_transaction()
                        logger.error(f"Transaction error: {str(e)}")
                        return False, {'error': str(e)}
            else:
                # MongoDB not available, just return the response
                if response_data.get('message') == 'callback received successfully' and 'data' in response_data:
                    return True, {
                        'checkout_id': response_data['data'].get('CheckoutRequestID', checkout_id),
                        'message': 'Payment completed successfully',
                        'reference': response_data['data'].get('refference', 'DIRECT'),
                        'instant_success': True
                    }
                elif 'data' in response_data and 'CheckoutRequestID' in response_data['data']:
                    return True, {
                        'checkout_id': response_data['data']['CheckoutRequestID'],
                        'message': 'Payment initiated, waiting for confirmation',
                        'instant_success': False
                    }
                else:
                    return False, {
                        'error': response_data.get('message', 'Unknown payment error'),
                        'checkout_id': checkout_id
                    }
        else:
            # Payment request failed
            error_msg = f"Payment request failed with status code: {response.status_code}"
            
            if mongo_db:
                mongo_db.transactions.update_one(
                    {'checkout_id': checkout_id},
                    {'$set': {
                        'status': 'failed',
                        'error': error_msg,
                        'updated_at': datetime.now()
                    }}
                )
                
                mongo_db.payments.update_one(
                    {'checkout_id': checkout_id},
                    {'$set': {
                        'status': 'failed',
                        'reference': error_msg
                    }}
                )
            
            return False, {
                'error': error_msg,
                'checkout_id': checkout_id
            }
    
    except Exception as e:
        logger.error(f"Payment processing error: {str(e)}")
        
        # Update MongoDB records if available
        if mongo_db:
            try:
                mongo_db.transactions.update_one(
                    {'checkout_id': checkout_id},
                    {'$set': {
                        'status': 'error',
                        'error': str(e),
                        'updated_at': datetime.now()
                    }}
                )
                
                mongo_db.payments.update_one(
                    {'checkout_id': checkout_id},
                    {'$set': {
                        'status': 'error',
                        'reference': str(e)
                    }}
                )
            except Exception as db_error:
                logger.error(f"Error updating transaction status: {str(db_error)}")
        
        return False, {'error': str(e)}

def process_payment_callback(mongo_db, callback_data):
    """
    Process payment callback from M-Pesa
    Returns success flag and message
    """
    try:
        logger.info(f"Processing payment callback: {callback_data}")
        
        # Extract checkout ID from callback data
        checkout_id = callback_data.get('CheckoutRequestID')
        if not checkout_id:
            logger.error("No checkout ID in callback data")
            return False, "Missing checkout ID"
        
        # Get reference number (for tracking)
        reference = callback_data.get('reference', callback_data.get('refference', 'CB-REF'))
        
        # Get status from callback
        # This will depend on the exact format your payment provider uses
        success = callback_data.get('success', callback_data.get('status') == 'success')
        
        # Check if MongoDB is available
        if not mongo_db:
            logger.error("MongoDB not available for payment callback")
            return False, "Database not available"
        
        # Get transaction record
        transaction = mongo_db.transactions.find_one({'checkout_id': checkout_id})
        if not transaction:
            # Try searching by real_checkout_id field
            transaction = mongo_db.transactions.find_one({'real_checkout_id': checkout_id})
            
        if not transaction:
            logger.error(f"Transaction not found for checkout ID: {checkout_id}")
            return False, "Transaction not found"
        
        # Process callback data
        with mongo_db.client.start_session() as session:
            session.start_transaction()
            try:
                if success:
                    # Payment successful
                    username = transaction['username']
                    subscription_type = transaction['subscription_type']
                    
                    # Update transaction status
                    mongo_db.transactions.update_one(
                        {'_id': transaction['_id']},
                        {'$set': {
                            'status': 'completed',
                            'reference': reference,
                            'updated_at': datetime.now()
                        }}
                    )
                    
                    # Update payment record
                    mongo_db.payments.update_one(
                        {'checkout_id': checkout_id},
                        {'$set': {
                            'status': 'completed',
                            'reference': reference
                        }}
                    )
                    
                    # Update user's word count
                    words_to_add = Config.BASIC_SUBSCRIPTION_WORDS if subscription_type == 'basic' else Config.PREMIUM_SUBSCRIPTION_WORDS
                    mongo_db.users.update_one(
                        {'username': username},
                        {'$inc': {'words_remaining': words_to_add}}
                    )
                    
                    # Update transaction status tracking
                    transaction_id = transaction.get('checkout_id')
                    if transaction_id in transaction_status:
                        transaction_status[transaction_id] = 'completed'
                    
                    logger.info(f"Payment successful for {username}, added {words_to_add} words")
                    session.commit_transaction()
                    return True, "Payment processed successfully"
                else:
                    # Payment failed
                    reason = callback_data.get('reason', 'Unknown failure reason')
                    
                    # Update transaction status
                    mongo_db.transactions.update_one(
                        {'_id': transaction['_id']},
                        {'$set': {
                            'status': 'failed',
                            'error': reason,
                            'updated_at': datetime.now()
                        }}
                    )
                    
                    # Update payment record
                    mongo_db.payments.update_one(
                        {'checkout_id': checkout_id},
                        {'$set': {
                            'status': 'failed',
                            'reference': reason
                        }}
                    )
                    
                    # Update transaction status tracking
                    transaction_id = transaction.get('checkout_id')
                    if transaction_id in transaction_status:
                        transaction_status[transaction_id] = 'failed'
                    
                    logger.warning(f"Payment failed for {transaction['username']}: {reason}")
                    session.commit_transaction()
                    return True, "Payment failure recorded"
            except Exception as e:
                # Rollback transaction on error
                session.abort_transaction()
                logger.error(f"Error processing payment callback: {str(e)}")
                return False, str(e)
    except Exception as e:
        logger.error(f"Error handling payment callback: {str(e)}")
        return False, str(e)

def get_transaction_status(mongo_db, checkout_id, username=None):
    """
    Get the current status of a transaction
    If username is provided, it will validate that the user owns the transaction
    """
    try:
        # Check in-memory status first (for recently queued transactions)
        if checkout_id in transaction_status:
            status = transaction_status[checkout_id]
            # For completed or failed transactions, verify with database
            if status in ['completed', 'failed'] and mongo_db:
                try:
                    # Get from database for complete information
                    transaction = mongo_db.transactions.find_one({'checkout_id': checkout_id})
                    if transaction:
                        # Verify username if provided
                        if username and transaction['username'] != username:
                            return {
                                'status': 'error',
                                'message': 'Unauthorized access to transaction'
                            }
                        
                        return {
                            'status': transaction['status'],
                            'reference': transaction.get('reference', 'N/A'),
                            'timestamp': transaction.get('updated_at', transaction.get('timestamp')).strftime('%Y-%m-%d %H:%M:%S')
                        }
                except Exception as e:
                    logger.error(f"Error getting transaction from database: {str(e)}")
            
            # Return in-memory status if database not available or transaction not yet in database
            return {
                'status': status,
                'reference': 'N/A',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        
        # Not in memory, check database
        if mongo_db:
            transaction = mongo_db.transactions.find_one({'checkout_id': checkout_id})
            if not transaction:
                # Try with real_checkout_id
                transaction = mongo_db.transactions.find_one({'real_checkout_id': checkout_id})
            
            if transaction:
                # Verify username if provided
                if username and transaction['username'] != username:
                    return {
                        'status': 'error',
                        'message': 'Unauthorized access to transaction'
                    }
                
                return {
                    'status': transaction['status'],
                    'reference': transaction.get('reference', 'N/A'),
                    'timestamp': transaction.get('updated_at', transaction.get('timestamp')).strftime('%Y-%m-%d %H:%M:%S')
                }
        
        # Transaction not found
        return {
            'status': 'not_found',
            'message': 'Transaction not found',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
    except Exception as e:
        logger.error(f"Error checking transaction status: {str(e)}")
        return {
            'status': 'error',
            'message': f'Error checking status: {str(e)}',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }

def start_payment_processor(mongo_db):
    """Start the payment processor background thread"""
    global stop_event
    
    # Reset stop event
    stop_event = threading.Event()
    
    # Start background worker thread
    worker_thread = threading.Thread(
        target=process_payment_queue_worker,
        args=(mongo_db,),
        daemon=True
    )
    worker_thread.start()
    logger.info("Payment processor background thread started")
    
    return worker_thread

def stop_payment_processor():
    """Stop the payment processor background thread"""
    global stop_event
    
    # Set stop event to signal worker to exit
    stop_event.set()
    logger.info("Payment processor signaled to stop")
