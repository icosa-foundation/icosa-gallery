from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import poly

app = FastAPI(title="Icosa API", redoc_url=None)
app.include_router(poly.router)

origins = ["*"]

app.add_middleware(CORSMiddleware,
    allow_origins=origins,
    allow_headers=["*"]
)

@app.get("/", include_in_schema=False)
async def root():
    return "Icosa API"
