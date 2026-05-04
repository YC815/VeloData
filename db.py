import os
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

DEFAULT_FTP = 250
DEFAULT_WEIGHT = 70.0
DEFAULT_BIKE_WEIGHT = 8.0
EXPORT_CACHE_TTL_MINUTES = 60
ACTIVITIES_CACHE_TTL_MINUTES = 120


class UserProfile(db.Model):
    __tablename__ = 'user_profile'
    id = db.Column(db.Integer, primary_key=True)
    ftp_watts = db.Column(db.Integer, nullable=False, default=DEFAULT_FTP)
    weight_kg = db.Column(db.Float, nullable=False, default=DEFAULT_WEIGHT)
    bike_weight_kg = db.Column(db.Float, nullable=False, default=DEFAULT_BIKE_WEIGHT)
    timezone = db.Column(db.String(64), nullable=False, default='Asia/Taipei')
    export_cache = db.Column(db.Text, nullable=True)
    export_cache_at = db.Column(db.DateTime, nullable=True)
    ftp_suggest_cache = db.Column(db.Text, nullable=True)
    ftp_suggest_at = db.Column(db.DateTime, nullable=True)
    activities_cache = db.Column(db.Text, nullable=True)
    activities_cache_at = db.Column(db.DateTime, nullable=True)
    strava_refresh_token = db.Column(db.String(256), nullable=True)

    def is_activities_cache_valid(self):
        if not self.activities_cache or not self.activities_cache_at:
            return False
        age_minutes = (datetime.utcnow() - self.activities_cache_at).total_seconds() / 60
        return age_minutes < ACTIVITIES_CACHE_TTL_MINUTES

    def is_export_cache_valid(self):
        if not self.export_cache or not self.export_cache_at:
            return False
        age_minutes = (datetime.utcnow() - self.export_cache_at).total_seconds() / 60
        return age_minutes < EXPORT_CACHE_TTL_MINUTES

    def to_dict(self):
        return {
            'ftp_watts': self.ftp_watts,
            'weight_kg': self.weight_kg,
            'bike_weight_kg': self.bike_weight_kg,
            'timezone': self.timezone,
        }


class RaceEvent(db.Model):
    __tablename__ = 'race_event'
    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(128), nullable=False)
    event_date = db.Column(db.Date, nullable=False)
    priority   = db.Column(db.String(1), nullable=False, default='C')
    distance_km  = db.Column(db.Float, nullable=True)
    elevation_m  = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        today = date.today()
        days_until = (self.event_date - today).days
        return {
            'id': self.id,
            'name': self.name,
            'date': self.event_date.isoformat(),
            'date_display': self.event_date.strftime('%-m/%-d'),
            'priority': self.priority,
            'distance_km': self.distance_km,
            'elevation_m': self.elevation_m,
            'days_until': days_until,
        }


def get_profile(app) -> UserProfile:
    with app.app_context():
        profile = UserProfile.query.first()
        if not profile:
            profile = UserProfile(ftp_watts=DEFAULT_FTP, weight_kg=DEFAULT_WEIGHT)
            db.session.add(profile)
            db.session.commit()
        return profile


def _migrate_add_column_if_missing(engine, table, column, col_type):
    """SQLite 不支援 IF NOT EXISTS on ALTER TABLE，需手動檢查欄位是否存在。"""
    from sqlalchemy import text
    with engine.connect() as conn:
        result = conn.execute(text(f"PRAGMA table_info({table})"))
        existing = {row[1] for row in result}
        if column not in existing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
            conn.commit()


def init_db(app):
    db_path = os.path.join(os.path.dirname(__file__), 'velodata.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        db.create_all()
        engine = db.engine
        _migrate_add_column_if_missing(engine, 'user_profile', 'export_cache', 'TEXT')
        _migrate_add_column_if_missing(engine, 'user_profile', 'export_cache_at', 'DATETIME')
        _migrate_add_column_if_missing(engine, 'user_profile', 'bike_weight_kg', 'FLOAT DEFAULT 8.0')
        _migrate_add_column_if_missing(engine, 'user_profile', 'ftp_suggest_cache', 'TEXT')
        _migrate_add_column_if_missing(engine, 'user_profile', 'ftp_suggest_at', 'DATETIME')
        _migrate_add_column_if_missing(engine, 'user_profile', 'activities_cache', 'TEXT')
        _migrate_add_column_if_missing(engine, 'user_profile', 'activities_cache_at', 'DATETIME')
        _migrate_add_column_if_missing(engine, 'user_profile', 'strava_refresh_token', 'VARCHAR(256)')
        if not UserProfile.query.first():
            db.session.add(UserProfile(ftp_watts=DEFAULT_FTP, weight_kg=DEFAULT_WEIGHT))
            db.session.commit()