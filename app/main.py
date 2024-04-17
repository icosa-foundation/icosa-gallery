from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database.database_connector import database
from app.routers import assets, login, poly, users

app = FastAPI(title="Icosa API", redoc_url=None)
app.include_router(login.router)
app.include_router(users.router)
app.include_router(assets.router)
app.include_router(poly.router)

origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_headers=["*"],
    allow_methods=["*"],
)


# region database connection
@app.on_event("startup")
async def startup():
    await database.connect()
    print("Connected to database.")


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()
    print("Disconnected from database.")


# endregion


@app.get("/", include_in_schema=False)
async def root():
    return "Icosa API"
