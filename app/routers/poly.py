from fastapi import APIRouter, HTTPException
import requests
import json

with open("config.json") as config_file:
    data = json.load(config_file)
    print(data["poly_api_key"])

router = APIRouter(
    prefix="/poly",
    tags=["Poly"]
    )

@router.get("/assets")
async def get_poly_assets_list():
    r = requests.get(f'https://poly.googleapis.com/v1/assets?key={data["poly_api_key"]}')
    print(r.status_code)
    if (r.status_code == 200):
        return r.json()
    else:
        raise HTTPException(status_code=404, detail="Item not found")

@router.get("/assets/{asset}")
async def get_poly_asset(asset : str):
    r = requests.get(f'https://poly.googleapis.com/v1/assets/{asset}?key={data["poly_api_key"]}')
    print(r.status_code)
    if (r.status_code == 200):
        return r.json()
    else:
        raise HTTPException(status_code=404, detail="Item not found")