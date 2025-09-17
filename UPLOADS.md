# Documentation for the unstable API uploads

> [!IMPORTANT]
> This entire document is subject to change and describes an unstable part of the API. Don't rely on any of this to be true in the future.

## Basic usage

POST a zip archive to `<api>/v1/assets/`. The request must be `multipart/form-data` including the zip archive in the `files` field.

For the upload to process anything at all, it must at least contain one of these valid file types:

- `.tilt`
- `.blocks`
- `.glb`
- `.gltf`
- `.bin`
- `.obj`
- `.mtl`
- `.fbx`
- `.fbm`
- `.ply`
- `.stl`
- `.usdx`
- `.vox`
- `.splat`
- `.ksplat`

Note that some of the above file types do not make sense on their own, e.g. `mtl`.

To add a thumbnail, include `thumbnail.png` or `thumbnail.jpg` in the root of the zip archive.

## The manifest file

Optionally, include `manifest.json` in the root of the zip archive to override our internal logic for assigning roles to certain files.

Note: reliance on roles will be removed. Role will become used solely for install-specific notes.

An example is:

```json
{
  "upload.glb": "UNKNOWN_GLB_FORMAT_B",
  "upload.gltf": "TILT_NATIVE_GLTF"
}
```

The available roles at the time of writing were:

```python
LEGACY_ROLES = {
    1: "ORIGINAL_OBJ_FORMAT",
    2: "TILT_FORMAT",
    4: "UNKNOWN_GLTF_FORMAT_A",
    6: "ORIGINAL_FBX_FORMAT",
    7: "BLOCKS_FORMAT",
    8: "USD_FORMAT",
    11: "HTML_FORMAT",
    12: "ORIGINAL_GLTF_FORMAT",
    13: "TOUR_CREATOR_EXPERIENCE",
    15: "JSON_FORMAT",
    16: "LULLMODEL_FORMAT",
    17: "SAND_FORMAT_A",
    18: "GLB_FORMAT",
    19: "SAND_FORMAT_B",
    20: "SANDC_FORMAT",
    21: "PB_FORMAT",
    22: "UNKNOWN_GLTF_FORMAT_B",
    24: "ORIGINAL_TRIANGULATED_OBJ_FORMAT",
    25: "JPG_BUGGY",
    26: "USDZ_FORMAT",
    30: "UPDATED_GLTF_FORMAT",
    32: "EDITOR_SETTINGS_PB_FORMAT",
    35: "UNKNOWN_GLTF_FORMAT_C",
    36: "UNKNOWN_GLB_FORMAT_A",
    38: "UNKNOWN_GLB_FORMAT_B",
    39: "TILT_NATIVE_GLTF",
    40: "USER_SUPPLIED_GLTF",
    1000: "POLYGONE_TILT_FORMAT",
    1001: "POLYGONE_BLOCKS_FORMAT",
    1002: "POLYGONE_GLB_FORMAT",
    1003: "POLYGONE_GLTF_FORMAT",
    1004: "POLYGONE_OBJ_FORMAT",
    1005: "POLYGONE_FBX_FORMAT",
}
```

## Constraints

The zip archive must not:

- be larger than 500MB uncompressed
- take us longer than 2 minutes to uncompress

Any files in sub directories are currently ignored (this matches the behaviour of Icosa Gallery beta mk1).
