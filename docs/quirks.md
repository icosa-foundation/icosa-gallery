## Quirks

This section documents behaviours of the site that might not be intuitive at first glance.

### Asset downloads available via the web UI

Asset formats are assigned roles when importing or uploading. These roles and the heuristics that decide how they are applied are likely to change.

The current roles available for download via the web UI are:

- ORIGINAL_OBJ_FORMAT,
- TILT_FORMAT,
- ORIGINAL_FBX_FORMAT,
- BLOCKS_FORMAT,
- USD_FORMAT,
- GLB_FORMAT,
- ORIGINAL_TRIANGULATED_OBJ_FORMAT,
- USDZ_FORMAT,
- UPDATED_GLTF_FORMAT,
- TILT_NATIVE_GLTF,
- USER_SUPPLIED_GLTF.

We provide some logic as to whether or not to provide a download, namely:

If there is more than one resource, this means we need to create a zip file of it on the client. We can only do this
if either:

- the resource is hosted by Django
- all the resources we need to zip are accessible because they are on the CORS allow list.

The second criteria is met if the resource's remote host is in the EXTERNAL_MEDIA_CORS_ALLOW_LIST setting in constance.

We also have some undocumented logic that is special to various data sets we are using on the flagship instance. This is extremely subject to change.

