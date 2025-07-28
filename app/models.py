# app/models.py
from flask_sqlalchemy import SQLAlchemy

# Initialize db WITHOUT passing the app instance yet
db = SQLAlchemy()

class User(db.Model):
    # ... (rest of your User model code) ...
    id = db.Column(db.Integer, primary_key=True)
    firebase_uid = db.Column(db.String(128), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    food_preferences = db.Column(db.String(255), nullable=True)
    search_radius = db.Column(db.Integer, default=10)
    reviews = db.relationship('Review', backref='user', lazy=True)
    bookmarks = db.relationship('Bookmark', backref='user', lazy=True)

    def __repr__(self):
        return f'<User {self.phone} (UID: {self.firebase_uid})>'

class Vendor(db.Model):
    # ... (rest of your Vendor model code) ...
    id = db.Column(db.Integer, primary_key=True)
    firebase_uid = db.Column(db.String(128), unique=True, nullable=False)
    phone = db.Column(db.String(20), unique=True, nullable=False)
    shop_name = db.Column(db.String(100), nullable=True)
    description = db.Column(db.Text, nullable=True)
    food_type = db.Column(db.String(255), nullable=True)
    menu_picture = db.Column(db.LargeBinary, nullable=True)
    working_hours_start = db.Column(db.String(5), nullable=True)
    working_hours_end = db.Column(db.String(5), nullable=True)
    current_latitude = db.Column(db.Float, nullable=True)
    current_longitude = db.Column(db.Float, nullable=True)
    is_online = db.Column(db.Boolean, default=False)
    reviews = db.relationship('Review', backref='vendor', lazy=True)
    bookmarks = db.relationship('Bookmark', backref='vendor', lazy=True)

    def __repr__(self):
        return f'<Vendor {self.shop_name} (UID: {self.firebase_uid})>'

# ... (Review and Bookmark models remain the same) ...
from datetime import datetime

class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    comment = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Review by User {self.user_id} for Vendor {self.vendor_id} - Rating: {self.rating}>'

class Bookmark(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    vendor_id = db.Column(db.Integer, db.ForeignKey('vendor.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('user_id', 'vendor_id', name='_user_vendor_uc'),)

    def __repr__(self):
        return f'<Bookmark User {self.user_id} -> Vendor {self.vendor_id}>'