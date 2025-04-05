from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, IntegerField, SubmitField
from wtforms.validators import DataRequired, Length, EqualTo, ValidationError, Regexp
from models import User

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
        user = User.get_by_username(username.data)
        if user:
            raise ValidationError('Username already exists. Please choose a different one.')


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
        if words_to_use.data <= 0:
            raise ValidationError('Please enter a positive number of words to use.')
