from datetime import datetime

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from werkzeug.security import check_password_hash, generate_password_hash


class Base(DeclarativeBase):
    pass


db = SQLAlchemy(model_class=Base)

book_genres = db.Table(
    "book_genres",
    db.Column(
        "book_id",
        db.Integer,
        db.ForeignKey("books.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    db.Column(
        "genre_id",
        db.Integer,
        db.ForeignKey("genres.id", ondelete="CASCADE"),
        primary_key=True,
    ),
)


class Role(db.Model):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(50), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(db.Text, nullable=False)
    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(db.Model, UserMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    login: Mapped[str] = mapped_column(db.String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(db.String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(db.String(100), nullable=False)
    first_name: Mapped[str] = mapped_column(db.String(100), nullable=False)
    middle_name: Mapped[str | None] = mapped_column(db.String(100))
    role_id: Mapped[int] = mapped_column(
        db.ForeignKey("roles.id"), nullable=False
    )
    role: Mapped[Role] = relationship(back_populates="users")
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    views: Mapped[list["BookView"]] = relationship(back_populates="user")

    def set_password(self, value):
        self.password_hash = generate_password_hash(value)

    def check_password(self, value):
        return check_password_hash(self.password_hash, value)

    @property
    def full_name(self):
        return " ".join(
            part for part in (self.last_name, self.first_name, self.middle_name) if part
        )

    @property
    def role_name(self):
        return self.role.name


class Genre(db.Model):
    __tablename__ = "genres"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(db.String(100), unique=True, nullable=False)


class Book(db.Model):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(db.String(255), nullable=False)
    short_description: Mapped[str] = mapped_column(db.Text, nullable=False)
    year: Mapped[int] = mapped_column(nullable=False)
    publisher: Mapped[str] = mapped_column(db.String(255), nullable=False)
    author: Mapped[str] = mapped_column(db.String(255), nullable=False)
    pages: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    genres: Mapped[list[Genre]] = relationship(secondary=book_genres, lazy="selectin")
    cover: Mapped["Cover"] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
        uselist=False,
        passive_deletes=True,
    )
    reviews: Mapped[list["Review"]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    views: Mapped[list["BookView"]] = relationship(
        back_populates="book",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def average_rating(self):
        if not self.reviews:
            return 0
        return sum(review.rating for review in self.reviews) / len(self.reviews)


class Cover(db.Model):
    __tablename__ = "covers"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(db.String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(db.String(100), nullable=False)
    md5_hash: Mapped[str] = mapped_column(db.String(32), nullable=False, index=True)
    book_id: Mapped[int] = mapped_column(
        db.ForeignKey("books.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    book: Mapped[Book] = relationship(back_populates="cover")


class Review(db.Model):
    __tablename__ = "reviews"
    __table_args__ = (
        UniqueConstraint("book_id", "user_id", name="uq_review_book_user"),
        CheckConstraint("rating >= 0 AND rating <= 5", name="ck_review_rating"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(
        db.ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        db.ForeignKey("users.id"), nullable=False
    )
    rating: Mapped[int] = mapped_column(nullable=False)
    text: Mapped[str] = mapped_column(db.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False
    )
    book: Mapped[Book] = relationship(back_populates="reviews")
    user: Mapped[User] = relationship(back_populates="reviews")


class BookView(db.Model):
    __tablename__ = "book_views"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(
        db.ForeignKey("books.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int | None] = mapped_column(db.ForeignKey("users.id"))
    visitor_key: Mapped[str] = mapped_column(db.String(64), nullable=False, index=True)
    viewed_at: Mapped[datetime] = mapped_column(
        default=datetime.utcnow, nullable=False, index=True
    )
    book: Mapped[Book] = relationship(back_populates="views")
    user: Mapped[User | None] = relationship(back_populates="views")
