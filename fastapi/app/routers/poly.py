import json
import math
import secrets
from typing import List

import requests
from app.database.database_connector import database
from app.database.database_schema import assets
from app.routers.users import get_me_assets
from app.storage.storage import upload_url_gcs
from app.utilities.authentication import get_current_user
from app.utilities.schema_models import (
    FullUser,
    PolyAsset,
    PolyPizzaAsset,
    PolyPizzaList,
)
from app.utilities.snowflake import generate_snowflake

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

with open("config.json") as config_file:
    data = json.load(config_file)

router = APIRouter(prefix="/poly", tags=["Poly"])

POLY_API_ROOT = "https://api.poly.pizza/v1"


@router.get("/assets", response_model=PolyPizzaList)
async def get_poly_assets_list(results: int = 20, page: int = 0):
    headers = {"x-auth-token": data["poly_api_key"]}
    r = requests.get(
        f"{POLY_API_ROOT}/search?Limit={results}&Page={page}", headers=headers
    )
    return r.json()


@router.get("/assets/{asset}", response_model=PolyPizzaAsset)
async def get_poly_asset(asset: str):
    headers = {"x-auth-token": data["poly_api_key"]}
    r = requests.get(f"{POLY_API_ROOT}/model/{asset}", headers=headers)
    if r.status_code == 200:
        return r.json()
    else:
        raise HTTPException(status_code=404, detail="Item not found")


async def import_poly(
    asset_id: str, asset: PolyAsset, snowflake: int, current_user: FullUser
):
    formats = []

    base_path = f'{current_user["id"]}/{snowflake}/'
    # base_path = "test/"

    for format in asset["formats"]:
        format_path = base_path + f'{format["formatType"]}/'
        format_upload_url = await upload_url_gcs(
            requests.get(format["root"]["url"]).content,
            f'{format_path}{format["root"]["relativePath"]}',
        )
        if format_upload_url:
            root_format_snowflake = generate_snowflake()
            # Add resources
            resources = []
            if format.get("resources"):
                for resource in format["resources"]:
                    resource_upload_url = await upload_url_gcs(
                        requests.get(resource["url"]).content,
                        f'{format_path}{resource["relativePath"]}',
                    )
                    if resource_upload_url:
                        resource_snowflake = generate_snowflake()
                        resources.append(
                            {
                                "id": resource_snowflake,
                                "url": resource_upload_url,
                                "format": resource["contentType"],
                            }
                        )
            formats.append(
                {
                    "id": root_format_snowflake,
                    "url": format_upload_url,
                    "format": format["formatType"],
                    "subfiles": resources,
                }
            )

    if len(formats) == 0:
        raise HTTPException(500, "Unable to upload any files.")

    assettoken = secrets.token_urlsafe(8)

    thumbnail_url = None
    if asset.get("thumbnail"):
        thumbnail_url = await upload_url_gcs(
            requests.get(asset["thumbnail"]["url"]).content,
            f"{base_path}thumbnail",
        )

    query = assets.insert(None).values(
        id=snowflake,
        url=assettoken,
        name=asset["displayName"],
        owner=current_user["id"],
        description=asset.get("description"),
        formats=formats,
        polyid=asset_id,
        polydata=asset,
        thumbnail=thumbnail_url,
    )
    await database.execute(query)
    print(f'DONE: {snowflake}/{asset["displayName"]}')


@router.post("/import")
async def import_poly_data(
    asset_ids: List[str],
    background_tasks: BackgroundTasks,
    current_user: FullUser = Depends(get_current_user),
):
    foundassets = []
    failedassets = []

    for asset in asset_ids:
        query = assets.select()
        query = query.where(assets.c.polyid == asset)
        data = await database.fetch_one(query)
        if data:
            print(f"asset {asset} already in database.")
            failedassets.append(
                {"asset": asset, "reason": "Asset already exists."}
            )
            continue
        try:
            snowflake = generate_snowflake()
            polydata = await get_poly_asset(asset)
            if polydata:
                background_tasks.add_task(
                    import_poly, asset, polydata, snowflake, current_user
                )
                foundassets.append(
                    {"asset": asset, "upload_job": str(snowflake)}
                )
        except HTTPException as exception:
            print(f"error fetching {asset}: {exception}")
            failedassets.append(
                {"asset": asset, "reason": "Failed to fetch asset."}
            )
    return {"foundassets": foundassets, "failedassets": failedassets}
