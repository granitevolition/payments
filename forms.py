from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Regexp
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Import function to check if user exists - but handle import errors
def check_username_exists(username):
    """Check if a username already exists in the database"""
    try:
        # Import function dynamically to avoid circular imports
        from app import get_user_by_username
        return get_user_by_username(username) is not None
    except ImportError as e:
        logger.error(f"Error importing get_user_by_username: {str(e)}")
        # Return False as a fallback if import fails
        return False
    except Exception as e:
        logger.error(f"Error checking if username exists: {str(e)}")
        # Return False as a fallback if any other error occurs
        return False

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(),
        Length(min=3, max=20)
    ])
    
    password = PasswordField('Password', validators=[
        DataRequired(),
        Length(min=4, max=20)
    ])
    
    confirm_password = PasswordField('Confirm Password', validators=[
        DataRequired(),
        EqualTo('password', message='Passwords must match')
    ])
    
    phone_number = StringField('Phone Number', validators=[
        DataRequired(),
        Regexp(r'^0[7][0-9]{8}$', message='Phone number must be in format 07XXXXXXXX')
    ])
    
    submit = SubmitField('Register')
    
    def validate_username(self, username):
        """Validate that the username is not already in use"""
        try:
            if check_username_exists(username.data):
                raise ValidationError('Username already exists. Please choose a different one.')
        except Exception as e:
            # Log the error but don't raise it - this allows form submission to proceed
            # and we'll catch database errors at the view level
            logger.error(f"Error during username validation: {str(e)}")

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[
        DataRequired(),
        Length(min=3, max=20)
    ])
    
    password = PasswordField('Password', validators=[
        DataRequired()
    ])
    
    submit = SubmitField('Login')

class UseWordsForm(FlaskForm):
    words_to_use = IntegerField('Words to Use', validators=[
        DataRequired()
    ])
    
    submit = SubmitField('Use Words')
    
    def validate_words_to_use(self, words_to_use):
        """Validate that the number of words to use is positive"""
        if words_to_use.data <= 0:
            raise ValidationError('Please enter a positive number of words to use.')
