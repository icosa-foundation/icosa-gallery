import json
from google.cloud import storage

with open("config.json") as config_file:
    data = json.load(config_file)

async def upload_file_gcs(source_file, destination_blob_name):
    """Uploads a file to the bucket."""
    # source_file = "local/path/to/file"
    # destination_blob_name = "storage-object-name"

    storage_client = storage.Client.from_service_account_json(data["service_account_data"])
    bucket = storage_client.bucket(data["gcloud_bucket_name"])
    blob = bucket.blob(destination_blob_name)
    try:
        blob.upload_from_file(source_file)
        blob.make_public()
    except Exception as e:
        print(e)
        return False
    return f'https://storage.googleapis.com/{data["gcloud_bucket_name"]}/{destination_blob_name}'

async def upload_url_gcs(source_url, destination_blob_name):
    """Uploads a file from a url the bucket."""
    # source_url = "example.com/asset.json"
    # destination_blob_name = "storage-object-name"

    storage_client = storage.Client.from_service_account_json(data["service_account_data"])
    bucket = storage_client.bucket(data["gcloud_bucket_name"])
    blob = bucket.blob(destination_blob_name)
    try:
        blob.upload_from_string(source_url)
        blob.make_public()
    except Exception as e:
        print(e)
        return False
    return f'https://storage.googleapis.com/{data["gcloud_bucket_name"]}/{destination_blob_name}'

async def remove_file_gcs(file_blob):
    """Removes a file from the bucket."""
    storage_client = storage.Client.from_service_account_json(data["service_account_data"])
    bucket = storage_client.bucket(data["gcloud_bucket_name"])
    blob = bucket.blob(file_blob)
    try:
        blob.delete()
    except Exception as e:
        print(e)
        return False
    return True