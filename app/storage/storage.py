import json
from google.cloud import storage

with open("config.json") as config_file:
    data = json.load(config_file)

def upload_file_gcs(source_file, destination_blob_name):
    """Uploads a file to the bucket."""
    # source_file = "local/path/to/file"
    # destination_blob_name = "storage-object-name"

    storage_client = storage.Client.from_service_account_json(data["service_account_data"])
    bucket = storage_client.bucket(data["gcloud_bucket_name"])
    blob = bucket.blob(destination_blob_name)

    try:
        blob.upload_from_file(source_file)
    except:
        return False
    return True