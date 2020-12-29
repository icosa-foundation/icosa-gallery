from fastapi import FastAPI
from .poly import poly

app = FastAPI(title="Icosa API", redoc_url=None)
app.include_router(poly.router)

@app.get("/")
async def root():
    return "Icosa API"
