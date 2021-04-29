from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List
import requests
import json
import secrets

from app.database.database_connector import database
from app.database.database_schema import assets

from app.utilities.schema_models import PolyAsset, PolyList, _DBAsset, FullUser
from app.utilities.authentication import get_current_user
from app.utilities.snowflake import generate_snowflake
from app.storage.storage import upload_url_gcs

with open("config.json") as config_file:
    data = json.load(config_file)

router = APIRouter(
    prefix="/poly",
    tags=["Poly"]
    )

@router.get("/assets", response_model=PolyList)
async def get_poly_assets_list(results: int = 20, page: int = 0, curated: bool = False):
    pageNext: str
    r = requests.get(f'https://poly.googleapis.com/v1/assets?key={data["poly_api_key"]}&curated={curated}&pageSize={results}')
    if (r.status_code == 200):
        pageNext = r.json()["nextPageToken"]
    for pagecount in range(page):
        r = requests.get(f'https://poly.googleapis.com/v1/assets?key={data["poly_api_key"]}&curated={curated}&pageSize={results}&pageToken={pageNext}')
        if (r.status_code == 200):
            pageNext = r.json()["nextPageToken"]
            continue
    return r.json()

@router.get("/assets/{asset}", response_model=PolyAsset)
async def get_poly_asset(asset : str):
    r = requests.get(f'https://poly.googleapis.com/v1/assets/{asset}?key={data["poly_api_key"]}')
    if (r.status_code == 200):
        return r.json()
    else:
        raise HTTPException(status_code=404, detail="Item not found")

async def import_poly(asset_id: str, asset: PolyAsset, snowflake: int, current_user: FullUser):

    formats = []

    base_path = f'{current_user["id"]}/{snowflake}/'
    #base_path = "test/"

    for format in asset["formats"]:
        format_path = base_path + f'{format["formatType"]}/'
        format_upload_url = await upload_url_gcs(requests.get(format["root"]["url"]).content, f'{format_path}{format["root"]["relativePath"]}')
        if format_upload_url:
            root_format_snowflake = generate_snowflake()
            # Add resources
            resources = []
            if format.get("resources"):
                for resource in format["resources"]:
                    resource_upload_url = await upload_url_gcs(requests.get(resource["url"]).content, f'{format_path}{resource["relativePath"]}')
                    if resource_upload_url:
                        resource_snowflake = generate_snowflake()
                        resources.append({"id": resource_snowflake, "url": resource_upload_url, "format": resource["contentType"]})
            formats.append({"id": root_format_snowflake, "url": "url", "format": format["formatType"], "subfiles": resources})

    if len(formats) == 0:
        raise HTTPException(500, "Unable to upload any files.")

    assettoken = secrets.token_urlsafe(8)
    
    thumbnail_url = None
    if asset.get("thumbnail"):
        thumbnail_url = await upload_url_gcs(requests.get(asset["thumbnail"]["url"]).content, f'{base_path}thumbnail')

    query = assets.insert(None).values(id=snowflake, url=assettoken, name=asset["displayName"], owner = current_user["id"], \
        description=asset.get("description"), formats=formats, polyid=asset_id, polydata=asset, thumbnail=thumbnail_url)
    await database.execute(query)
    print(f'DONE: {snowflake}/{asset["displayName"]}')

@router.post("/import")
async def import_poly_data(assets: List[str], background_tasks: BackgroundTasks, current_user: FullUser = Depends(get_current_user)):
    foundassets = []
    failedassets = []
    for asset in assets:
        snowflake = generate_snowflake()
        try:
            polydata = await get_poly_asset(asset)
            if polydata:
                background_tasks.add_task(import_poly, asset, polydata, snowflake, current_user)
                foundassets.append({"asset" : asset, "upload_job" : str(snowflake)})
        except HTTPException as exception:
            print(f'error fetching {asset}: {exception}')
            failedassets.append({"asset": asset})
    return { "foundassets": foundassets, "failedassets": failedassets }
