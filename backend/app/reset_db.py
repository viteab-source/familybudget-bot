# backend/app/reset_db.py

from .db import Base, engine
from . import models  # важно: чтобы все модели были импортированы


def reset_db():
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("Done.")


if __name__ == "__main__":
    reset_db()
