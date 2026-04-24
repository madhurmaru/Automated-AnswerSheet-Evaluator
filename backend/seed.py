from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import User


def run() -> None:
    settings = get_settings()
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == settings.default_admin_username).first()
        if not user:
            db.add(
                User(
                    username=settings.default_admin_username,
                    hashed_password=hash_password(settings.default_admin_password),
                    is_teacher=True,
                )
            )
            db.commit()
        print(f"Seed done. Login: {settings.default_admin_username} / {settings.default_admin_password}")
    finally:
        db.close()


if __name__ == '__main__':
    run()
