import os
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

DEFAULT_FTP = 250
DEFAULT_WEIGHT = 70.0


class UserProfile(db.Model):
    __tablename__ = 'user_profile'
    id = db.Column(db.Integer, primary_key=True)
    ftp_watts = db.Column(db.Integer, nullable=False, default=DEFAULT_FTP)
    weight_kg = db.Column(db.Float, nullable=False, default=DEFAULT_WEIGHT)

    def to_dict(self):
        return {'ftp_watts': self.ftp_watts, 'weight_kg': self.weight_kg}


def get_profile(app) -> UserProfile:
    with app.app_context():
        profile = UserProfile.query.first()
        if not profile:
            profile = UserProfile(ftp_watts=DEFAULT_FTP, weight_kg=DEFAULT_WEIGHT)
            db.session.add(profile)
            db.session.commit()
        return profile


def init_db(app):
    db_path = os.path.join(os.path.dirname(__file__), 'velodata.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
        if not UserProfile.query.first():
            db.session.add(UserProfile(ftp_watts=DEFAULT_FTP, weight_kg=DEFAULT_WEIGHT))
            db.session.commit()
