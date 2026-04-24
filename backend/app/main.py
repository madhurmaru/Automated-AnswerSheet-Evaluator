from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.core.db import Base, engine, SessionLocal
from app.core.security import hash_password
from app.models import User

settings = get_settings()
app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
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
    finally:
        db.close()


@app.get("/")
def root():
    return {"status": "ok", "app": settings.app_name}


app.include_router(router, prefix=settings.api_prefix)
