from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

# ---- User Model ----
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

# ---- Board Model ----
class Board(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    lists = db.relationship('List', backref='board', cascade="all, delete")

# ---- List Model ----
class List(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    board_id = db.Column(db.Integer, db.ForeignKey('board.id'))
    cards = db.relationship('Card', backref='list', cascade="all, delete")

# ---- Card Model ----
class Card(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200))
    position = db.Column(db.Integer)
    list_id = db.Column(db.Integer, db.ForeignKey('list.id'))
