from fastapi import FastAPI

app = FastAPI(title="FamilyBudget API")


@app.get("/health")
def health_check():
    return {"status": "ok"}
