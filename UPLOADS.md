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

(Support for `.ply`, `.stl`, `.usdx`, and `.vox` will be added soon.) 

Note that some of the above file types do not make sense on their own, e.g. `mtl`.

To add a thumbnail, include `thumbnail.png` or `thumbnail.jpg` in the root of the zip archive.

## The manifest file

Optionally, include `manifest.json` in the root of the zip archive to override our internal logic for assigning roles to certain files.

An example is:

```json
{
  "upload.glb": "UNKNOWN_GLB_FORMAT_B",
  "upload.gltf": "TILT_NATIVE_GLTF"
}
```

The available roles can be found at the top of `django/icosa/helpers/format_roles.py`.

## Constraints

The zip archive must not:

- be larger than 500MB uncompressed
- take us longer than 2 minutes to uncompress

Any files in sub directories are currently ignored (this matches the behaviour of Icosa Gallery beta mk1).
