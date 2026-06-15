import hashlib
from datetime import datetime, timedelta
from pathlib import Path

from app import create_app
from app.models import Book, BookView, Cover, Genre, Review, Role, User, db

app = create_app()


def create_cover(book, color, _label):
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="600" height="900">
<rect width="600" height="900" fill="{color}"/>
<rect x="45" y="45" width="510" height="810" fill="none" stroke="white" stroke-width="4"/>
<text x="300" y="405" text-anchor="middle" fill="white" font-family="Arial" font-size="58">КНИГА</text>
<text x="300" y="465" text-anchor="middle" fill="white" font-family="Arial" font-size="22">Электронная библиотека</text>
</svg>"""
    content = svg.encode("utf-8")
    digest = hashlib.md5(content).hexdigest()
    filename = f"{digest}.svg"
    path = Path(app.config["UPLOAD_FOLDER"]) / filename
    path.write_bytes(content)
    db.session.add(
        Cover(
            filename=filename,
            mime_type="image/svg+xml",
            md5_hash=digest,
            book=book,
        )
    )


def get_or_create_user(login, password, last_name, first_name, role):
    user = db.session.scalar(db.select(User).filter_by(login=login))
    if not user:
        user = User(
            login=login,
            last_name=last_name,
            first_name=first_name,
            role=role,
        )
        user.set_password(password)
        db.session.add(user)
        db.session.flush()
    return user


with app.app_context():
    db.create_all()

    role_data = {
        "admin": "Суперпользователь с полным доступом",
        "moderator": "Редактирование книг и работа с рецензиями",
        "user": "Чтение книг и создание рецензий",
    }
    roles = {}
    for name, description in role_data.items():
        role = db.session.scalar(db.select(Role).filter_by(name=name))
        if not role:
            role = Role(name=name, description=description)
            db.session.add(role)
        roles[name] = role
    db.session.flush()

    admin = get_or_create_user(
        "admin", "Admin123", "Иванов", "Иван", roles["admin"]
    )
    moderator = get_or_create_user(
        "moderator", "Moderator123", "Петрова", "Мария", roles["moderator"]
    )
    reader = get_or_create_user(
        "user", "User12345", "Сидоров", "Алексей", roles["user"]
    )

    genre_names = ["Роман", "Фантастика", "Детектив", "Научная литература", "История"]
    genres = {}
    for name in genre_names:
        genre = db.session.scalar(db.select(Genre).filter_by(name=name))
        if not genre:
            genre = Genre(name=name)
            db.session.add(genre)
        genres[name] = genre
    db.session.flush()

    book_specs = [
        (
            "Мастер и Маргарита",
            "Михаил Булгаков",
            1967,
            "Азбука",
            480,
            ["Роман", "Фантастика"],
            "# Мастер и Маргарита\n\nРоман о любви, свободе и ответственности.",
            "#4b5563",
        ),
        (
            "Пикник на обочине",
            "Аркадий и Борис Стругацкие",
            1972,
            "АСТ",
            256,
            ["Фантастика"],
            "Научно-фантастическая повесть о загадочной **Зоне**.",
            "#166534",
        ),
        (
            "Десять негритят",
            "Агата Кристи",
            1939,
            "Эксмо",
            288,
            ["Детектив"],
            "Классический детектив о десяти гостях на изолированном острове.",
            "#991b1b",
        ),
        (
            "Краткая история времени",
            "Стивен Хокинг",
            1988,
            "Амфора",
            232,
            ["Научная литература"],
            "Популярное введение в космологию и устройство Вселенной.",
            "#1d4ed8",
        ),
        (
            "История государства Российского",
            "Николай Карамзин",
            1818,
            "Наука",
            960,
            ["История"],
            "Фундаментальный труд по истории России.",
            "#854d0e",
        ),
    ]

    books = []
    for title, author, year, publisher, pages, book_genres, description, color in book_specs:
        book = db.session.scalar(db.select(Book).filter_by(title=title))
        if not book:
            book = Book(
                title=title,
                author=author,
                year=year,
                publisher=publisher,
                pages=pages,
                short_description=description,
                genres=[genres[name] for name in book_genres],
            )
            db.session.add(book)
            db.session.flush()
            create_cover(book, color, title)
        books.append(book)
    db.session.flush()

    if not db.session.scalar(
        db.select(Review).filter_by(book_id=books[0].id, user_id=reader.id)
    ):
        db.session.add(
            Review(
                book=books[0],
                user=reader,
                rating=5,
                text="Отличный роман. Особенно понравилась **московская линия**.",
            )
        )

    if not db.session.scalar(db.select(BookView.id).limit(1)):
        now = datetime.utcnow()
        for index, book in enumerate(books):
            for offset in range(5 - index):
                db.session.add(
                    BookView(
                        book=book,
                        user=reader,
                        visitor_key=f"user:{reader.id}",
                        viewed_at=now - timedelta(days=offset + index),
                    )
                )
            db.session.add(
                BookView(
                    book=book,
                    user=admin,
                    visitor_key=f"user:{admin.id}",
                    viewed_at=now - timedelta(days=index),
                )
            )

    db.session.commit()
    print("Демонстрационные данные созданы.")
