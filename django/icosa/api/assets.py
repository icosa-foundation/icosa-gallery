import re
from typing import List, NoReturn, Optional

from icosa.models import PUBLIC, Asset, User
from ninja import Router
from ninja.errors import HttpError
from ninja.pagination import paginate

from django.db.models import Q
from django.http import HttpRequest

from .authentication import AuthBearer
from .schema import AssetSchemaIn, AssetSchemaOut

router = Router()


IMAGE_REGEX = re.compile("(jpe?g|tiff?|png|webp|bmp)")


def user_can_view_asset(
    request: HttpRequest,
    asset: Asset,
) -> bool:
    if asset.visibility == "PRIVATE":
        return user_owns_asset(request, asset)
    return True


def user_owns_asset(
    request: HttpRequest,
    asset: Asset,
) -> bool:
    if (
        request.auth.is_anonymous
        or User.from_ninja_request(request) != asset.owner
    ):
        return False
    return True


def check_user_owns_asset(
    request: HttpRequest,
    asset: Asset,
) -> NoReturn:
    if not user_owns_asset(request, asset):
        raise HttpError(403, "Unauthorized user.")


def get_asset_by_id(
    request: HttpRequest,
    asset: int,
) -> Asset:
    # get_object_or_404 raises the wrong error text
    try:
        asset = Asset.objects.get(pk=asset)
    except Asset.DoesNotExist:
        raise HttpError(404, "Asset not found.")
    if not user_can_view_asset(request, asset):
        raise HttpError(404, "Asset not found.")
    return asset


def get_my_id_asset(
    request,
    asset: int,
):
    try:
        asset = get_asset_by_id(request, asset)
    except Exception:
        raise
    check_user_owns_asset(request, asset)
    return asset


@router.get("/id/{asset}", response=AssetSchemaOut)
def get_id_asset(
    request,
    asset: int,
):
    return get_asset_by_id(request, asset)


@router.patch(
    "/{str:asset}/unpublish", auth=AuthBearer(), response=AssetSchemaIn
)
def unpublish_asset(
    request,
    asset: int,
):
    asset = get_my_id_asset(request, asset)
    asset.visibility = "PRIVATE"
    asset.save()
    return asset


@router.get("/{str:userurl}/{asseturl}", response=AssetSchemaOut)
def get_asset(
    request,
    userurl: str,
    asseturl: str,
):
    # get_object_or_404 raises the wrong error text
    try:
        asset = Asset.objects.get(url=asseturl, owner__url=userurl)
    except Asset.DoesNotExist:
        raise HttpError(404, "Asset not found.")

    if not user_can_view_asset(request, asset):
        raise HttpError(404, "Asset not found.")
    return asset


# def validate_file(file: UploadFile, extension: str):
#     # Need to check if the resource is a main file or helper file.
#     # Return format is (file: UploadFile, extension: str, filetype: str, mainfile: bool)
#     # Ordered in most likely file types for 'performance'

#     # TODO(safety): Do we fail to identify what the main file is if the zip
#     # archive contains both (e.g.) a .tilt and a .fbx?

#     if extension == "tilt":
#         return (file, extension, "TILT", True)

#     # GLTF/GLB/BIN
#     if extension == "glb":
#         return (file, extension, "GLTF2", True)

#     if extension == "gltf":
#         # TODO: need extra checks here to determine if GLTF 1 or 2.
#         return (file, extension, "GLTF2", True)
#     if extension == "bin":
#         return (file, extension, "BIN", False)

#     # OBJ
#     if extension == "obj":
#         return (file, extension, "OBJ", True)
#     if extension == "mtl":
#         return (file, extension, "MTL", False)

#     # FBX
#     if extension == "fbx":
#         return (file, extension, "FBX", True)
#     if extension == "fbm":
#         return (file, extension, "FBM", False)

#     # Images
#     if IMAGE_REGEX.match(extension):
#         return (file, extension, "IMAGE", False)
#     return None


# async def upload_background(
#     current_user: User,
#     files: List[UploadFile],
#     thumbnail: UploadFile,
#     job_snowflake: int,
# ):
#     if len(files) == 0:
#         raise HTTPException(422, "No files provided.")

#     # Loop on files provided and check types.
#     # We need to see one of: tilt, glb, gltf, obj, fbx
#     mainfile_details = []
#     subfile_details = []
#     name = ""

#     processed_files = []

#     for file in files:
#         # Handle thumbnail included in the zip
#         # How do we handle multiple thumbnails? Currently non-zip thumbnails take priority
#         if thumbnail is None and file.filename.lower() in [
#             "thumbnail.png",
#             "thumbnail.jpg",
#         ]:
#             thumbnail = file
#         elif file.filename.endswith(".zip"):
#             # Read the file as a ZIP file
#             with zipfile.ZipFile(io.BytesIO(await file.read())) as zip_file:
#                 # Iterate over each file in the ZIP
#                 for zip_info in zip_file.infolist():
#                     # Skip directories
#                     if zip_info.is_dir():
#                         continue
#                     # Read the file contents
#                     with zip_file.open(zip_info) as extracted_file:
#                         # Create a new UploadFile object
#                         content = extracted_file.read()
#                         processed_file = UploadFile(
#                             filename=zip_info.filename,
#                             file=io.BytesIO(content),
#                         )
#                         processed_files.append(processed_file)
#                         if thumbnail is None and zip_info.filename.lower() in [
#                             "thumbnail.png",
#                             "thumbnail.jpg",
#                         ]:
#                             thumbnail = processed_file
#         else:
#             processed_files.append(file)

#     for file in processed_files:
#         splitnames = file.filename.split(".")
#         extension = splitnames[-1].lower()
#         uploadDetails = validate_file(file, extension)
#         if uploadDetails:
#             if uploadDetails[3]:
#                 mainfile_details.append(uploadDetails)
#                 name = splitnames[0]
#             else:
#                 subfile_details.append(uploadDetails)

#     if name == "":
#         raise HTTPException(
#             415, "Not supplied with one of tilt, glb, gltf, obj, fbx."
#         )

#     # begin upload process
#     assetsnowflake = job_snowflake
#     assettoken = secrets.token_urlsafe(8)
#     formats = []

#     for mainfile in mainfile_details:
#         # Main files determine folder
#         base_path = f'{current_user["id"]}/{assetsnowflake}/{mainfile[2]}/'
#         model_path = base_path + f"model.{mainfile[1]}"
#         model_uploaded_url = await upload_file_gcs(
#             mainfile[0].file, model_path
#         )

#         # Only bother processing extras if success
#         if model_uploaded_url:
#             mainfile_snowflake = generate_snowflake()
#             extras = []

#             for subfile in subfile_details:
#                 # Horrendous check for supposedly compatible subfiles. can definitely be improved with parsing, but is it necessary?
#                 if (
#                     (
#                         mainfile[2] == "GLTF2"
#                         and (subfile[2] == "BIN" or subfile[2] == "IMAGE")
#                     )
#                     or (
#                         mainfile[2] == "OBJ"
#                         and (subfile[2] == "MTL" or subfile[2] == "IMAGE")
#                     )
#                     or (
#                         mainfile[2] == "FBX"
#                         and (subfile[2] == "FBM" or subfile[2] == "IMAGE")
#                     )
#                 ):
#                     subfile_path = base_path + f"{subfile[0].filename}"
#                     subfile_uploaded_url = await upload_file_gcs(
#                         subfile[0].file, subfile_path
#                     )
#                     if subfile_uploaded_url:
#                         subfile_snowflake = generate_snowflake()
#                         extras.append(
#                             {
#                                 "id": subfile_snowflake,
#                                 "url": subfile_uploaded_url,
#                                 "format": subfile[2],
#                             }
#                         )
#             if len(extras) > 0:
#                 formats.append(
#                     {
#                         "id": mainfile_snowflake,
#                         "url": model_uploaded_url,
#                         "format": mainfile[2],
#                         "subfiles": extras,
#                     }
#                 )
#             else:
#                 formats.append(
#                     {
#                         "id": mainfile_snowflake,
#                         "url": model_uploaded_url,
#                         "format": mainfile[2],
#                     }
#                 )

#     thumbnail_uploaded_url = None
#     if thumbnail:
#         extension = thumbnail.filename.split(".")[-1].lower()
#         thumbnail_upload_details = validate_file(file, extension)
#         if thumbnail_upload_details and thumbnail_upload_details[2] == "IMAGE":
#             thumbnail_path = (
#                 base_path + "thumbnail." + thumbnail_upload_details[1]
#             )
#             thumbnail_uploaded_url = await upload_file_gcs(
#                 thumbnail_upload_details[0].file, thumbnail_path
#             )

#     # Add to database
#     if len(formats) == 0:
#         raise HTTPException(500, "Unable to upload any files.")
#     query = assets.insert(None).values(
#         id=assetsnowflake,
#         url=assettoken,
#         name=name,
#         owner=current_user["id"],
#         formats=formats,
#         thumbnail=thumbnail_uploaded_url,
#     )
#     await database.execute(query)
#     query = assets.select()
#     query = query.where(assets.c.id == assetsnowflake)
#     newasset = jsonable_encoder(await database.fetch_one(query))
#     print("DONE")
#     print(newasset["id"])
#     print(newasset)
#     return newasset


# async def upload_thumbnail_background(
#     current_user: User, thumbnail: UploadFile, asset_id: int
# ):
#     splitnames = thumbnail.filename.split(".")
#     extension = splitnames[-1].lower()
#     if not IMAGE_REGEX.match(extension):
#         raise HTTPException(415, "Thumbnail must be png or jpg")

#     base_path = f'{current_user["id"]}/{asset_id}/'
#     thumbnail_path = f"{base_path}thumbnail.{extension}"
#     thumbnail_uploaded_url = await upload_file_gcs(
#         thumbnail.file, thumbnail_path
#     )

#     if thumbnail_uploaded_url:
#         # Update database
#         query = assets.update(None)
#         query = query.where(assets.c.id == asset_id)
#         query = query.values(thumbnail=thumbnail_uploaded_url)
#         await database.execute(query)


# @router.post("", status_code=202)
# @router.post("/", status_code=202, include_in_schema=False)
# async def upload_new_assets(
#     background_tasks: BackgroundTasks,
#     current_user: User = Depends(get_current_user),
#     files: List[UploadFile] = File(...),
# ):
#     if len(files) == 0:
#         raise HTTPException(422, "No files provided.")
#     job_snowflake = generate_snowflake()
#     background_tasks.add_task(
#         upload_background, current_user, files, None, job_snowflake
#     )
#     return {"upload_job": str(job_snowflake)}


# @router.patch("/{asset}", response_model=Asset)
# async def update_asset(
#     background_tasks: BackgroundTasks,
#     request: Request,
#     asset: int,
#     data: Optional[AssetPatchData] = None,
#     name: Optional[str] = Form(None),
#     url: Optional[str] = Form(None),
#     description: Optional[str] = Form(None),
#     visibility: Optional[str] = Form(None),
#     current_user: User = Depends(get_current_user),
#     thumbnail: Optional[UploadFile] = File(None),
# ):
#     current_asset = _DBAsset(**(await get_my_id_asset(asset, current_user)))

#     if request.headers.get("content-type") == "application/json":
#         update_data = data.dict(exclude_unset=True)
#     elif request.headers.get("content-type").startswith("multipart/form-data"):
#         update_data = {
#             k: v
#             for k, v in {
#                 "name": name,
#                 "url": url,
#                 "description": description,
#                 "visibility": visibility,
#             }.items()
#             if v is not None
#         }
#     else:
#         raise HTTPException(
#             status_code=415, detail="Unsupported content type."
#         )

#     updated_asset = current_asset.copy(update=update_data)
#     updated_asset.id = int(updated_asset.id)
#     updated_asset.owner = int(updated_asset.owner)
#     query = assets.update(None)
#     query = query.where(assets.c.id == updated_asset.id)
#     query = query.values(updated_asset.dict())
#     await database.execute(query)
#     if thumbnail:
#         background_tasks.add_task(
#             upload_thumbnail_background, current_user, thumbnail, asset
#         )
#     return await get_my_id_asset(asset, current_user)


# @router.delete("/{asset}")
# async def delete_asset(
#     request,
#     asset: int,
# ):
#     try:
#         asset = get_my_id_asset(request, asset)
#     except Exception:
#         raise
#     check_user_owns_asset(request, asset)
#     asset.delete()
#     # Asset removal from storage
#     owner = User.from_ninja_request(request)
#     asset_folder = f"{owner.id}/{asset}/"
#     if not (await remove_folder_gcs(asset_folder)):
#         print(f"Failed to remove asset {asset}")
#         raise HTTPException(
#             status_code=500, detail=f"Failed to remove asset {asset}"
#         )
#     return check_asset


@router.get("", response=List[AssetSchemaOut])
@router.get("/", response=List[AssetSchemaOut], include_in_schema=False)
@paginate
def get_assets(
    request,
    curated: bool = False,
    name: Optional[str] = None,
    description: Optional[str] = None,
    ownername: Optional[str] = None,
    format: Optional[str] = None,
):
    # TODO(james): limit max pagination to 100 results
    # TODO(james): `limit` query param should be `pageSize`; need to find out
    # what `offset` should be
    q = Q(visibility=PUBLIC)

    if curated:
        q &= Q(curated=True)
    if name:
        q &= Q(name__icontains=name)
    if description:
        q &= Q(description__icontains=description)
    if ownername:
        q &= Q(owner__displayname__icontains=ownername)
    if format:
        q &= Q(formats__contains=[{"format": format}])

    assets = Asset.objects.filter(q)
    return assets
