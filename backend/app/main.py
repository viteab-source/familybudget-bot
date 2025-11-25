from fastapi import FastAPI

from .db import Base, engine
from . import models

app = FastAPI(title="FamilyBudget API")


# При старте приложения создаём таблицы (если их ещё нет)
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)


@app.get("/health")
def health_check():
    return {"status": "ok"}
