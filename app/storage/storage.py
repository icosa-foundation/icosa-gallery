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
    return f'https://storage.cloud.google.com/{data["gcloud_bucket_name"]}/{destination_blob_name}'

def remove_file_gcs(file_blob):
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