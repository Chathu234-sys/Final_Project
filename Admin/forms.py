from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, FileField
from wtforms.validators import DataRequired, Email, Length
from flask_wtf.file import FileAllowed

class AdminLoginForm(FlaskForm):
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class PolishForm(FlaskForm):
    name = StringField('Polish Name', validators=[DataRequired(), Length(min=2, max=100)])
    brand = StringField('Brand', validators=[DataRequired(), Length(min=2, max=100)])
    hex = StringField('Hex Code', validators=[DataRequired(), Length(min=4, max=7)])
    image = FileField('Polish Image', validators=[FileAllowed(['jpg', 'jpeg', 'png'], 'Images only!')])
    submit = SubmitField('Save')
