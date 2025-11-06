class Config:
    SECRET_KEY = 'supersecretkey'
    SQLALCHEMY_DATABASE_URI = 'postgresql+psycopg2://postgres:root123@localhost/postgres'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
