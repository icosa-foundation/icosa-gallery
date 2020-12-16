from fastapi import FastAPI

app = FastAPI(title="Icosa API", redoc_url=None)

@app.get("/")
async def root():
    return "Icosa API"
