"""Measure triangle counts from model files *without* downloading the geometry.

The strategy is format-specific but always avoids loading the full mesh into
memory:

* glTF / GLB: the accessor `count` values live in the JSON header. For a `.glb`
  we issue HTTP Range requests for the 12-byte header + the JSON chunk only,
  never fetching the (potentially large) binary buffer. Draco/meshopt
  compression is irrelevant because the logical accessor counts are still
  present in the JSON.
* OBJ: streamed line-by-line, counting `f` faces in constant memory.
* VOX (MagicaVoxel): Range requests read each model's voxel count and seek past
  the voxel payload, then estimate triangles as voxels * `TRIANGLES_PER_VOXEL`.

Other (binary) formats are not supported here and return ``None``.
"""

import json
import struct
from typing import Optional

import requests

# glTF primitive modes.
_MODE_TRIANGLES = 4
_MODE_TRIANGLE_STRIP = 5
_MODE_TRIANGLE_FAN = 6

_GLB_MAGIC = 0x46546C67  # "glTF" little-endian
_GLB_JSON_CHUNK = 0x4E4F534A  # "JSON" little-endian

# A voxel meshes to a cube: 6 faces * 2 triangles each. This assumes no greedy
# meshing, so it is an over-estimate, but a cheap and consistent one — there is
# no canonical triangle count for a voxel model, it depends on the mesher.
TRIANGLES_PER_VOXEL = 12

DEFAULT_TIMEOUT = 30


class TriangleCountError(Exception):
    """Raised when a model file cannot be parsed for a triangle count."""


def triangles_from_gltf_doc(doc: dict) -> int:
    """Compute the triangle count for a parsed glTF/GLB JSON document.

    Walks the node graph so that meshes instanced by multiple nodes are
    counted once per instance, matching what is actually rendered.
    """
    # glTF 1.0 uses a fundamentally different, string-keyed structure for
    # meshes/accessors/nodes; this parser targets 2.0. Bail out clearly rather
    # than mis-count or crash. 1.0 assets in this catalogue always ship a
    # GLB/GLTF2/OBJ companion we can measure instead.
    version = str(doc.get("asset", {}).get("version", "2.0"))
    if version.startswith("1") or isinstance(doc.get("meshes"), dict):
        raise TriangleCountError(f"glTF 1.0 is not supported (version {version!r})")

    accessors = doc.get("accessors", [])
    meshes = doc.get("meshes", [])

    def primitive_triangles(prim: dict) -> int:
        mode = prim.get("mode", _MODE_TRIANGLES)
        if mode not in (_MODE_TRIANGLES, _MODE_TRIANGLE_STRIP, _MODE_TRIANGLE_FAN):
            return 0  # points / lines contribute no triangles
        indices = prim.get("indices")
        if indices is not None:
            count = accessors[indices]["count"]
        else:
            position = prim.get("attributes", {}).get("POSITION")
            if position is None:
                return 0
            count = accessors[position]["count"]
        if mode == _MODE_TRIANGLES:
            return count // 3
        # strip / fan: each vertex after the first two adds one triangle
        return max(count - 2, 0)

    mesh_triangles = [sum(primitive_triangles(p) for p in m.get("primitives", [])) for m in meshes]

    nodes = doc.get("nodes", [])
    if nodes:
        total = 0
        instanced = False
        for node in nodes:
            mesh_index = node.get("mesh")
            if mesh_index is not None and 0 <= mesh_index < len(mesh_triangles):
                total += mesh_triangles[mesh_index]
                instanced = True
        if instanced:
            return total

    # No nodes reference meshes (or no node graph at all): fall back to one
    # instance of every defined mesh.
    return sum(mesh_triangles)


def count_triangles_glb(url: str, session: Optional[requests.Session] = None, timeout: int = DEFAULT_TIMEOUT) -> int:
    """Read a `.glb` header via Range requests and return its triangle count."""
    session = session or requests
    # First 20 bytes: 12-byte GLB header + 8-byte first-chunk header.
    head = _range_get(session, url, 0, 19, timeout)
    if len(head) < 20:
        raise TriangleCountError(f"GLB too short to contain a header: {url}")
    magic, _version, _length = struct.unpack_from("<III", head, 0)
    if magic != _GLB_MAGIC:
        raise TriangleCountError(f"Not a GLB file (bad magic): {url}")
    json_len, json_type = struct.unpack_from("<II", head, 12)
    if json_type != _GLB_JSON_CHUNK:
        raise TriangleCountError(f"First GLB chunk is not JSON: {url}")
    json_bytes = _range_get(session, url, 20, 20 + json_len - 1, timeout)
    doc = json.loads(json_bytes[:json_len])
    return triangles_from_gltf_doc(doc)


def count_triangles_gltf(url: str, session: Optional[requests.Session] = None, timeout: int = DEFAULT_TIMEOUT) -> int:
    """Fetch a `.gltf` JSON document (ignoring its `.bin`) and count triangles."""
    session = session or requests
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    return triangles_from_gltf_doc(resp.json())


def count_triangles_obj(url: str, session: Optional[requests.Session] = None, timeout: int = DEFAULT_TIMEOUT) -> int:
    """Stream an OBJ file and sum its triangulated faces in constant memory."""
    session = session or requests
    triangles = 0
    with session.get(url, stream=True, timeout=timeout) as resp:
        resp.raise_for_status()
        for raw in resp.iter_lines():
            # `f a b c ...` — an n-gon triangulates into (n - 2) triangles.
            if raw[:2] == b"f " or raw[:2] == b"f\t":
                verts = len(raw.split()) - 1
                if verts >= 3:
                    triangles += verts - 2
    return triangles


def count_triangles_vox(url: str, session: Optional[requests.Session] = None, timeout: int = DEFAULT_TIMEOUT) -> int:
    """Estimate triangles for a MagicaVoxel `.vox` file from its voxel count.

    Only the ``numVoxels`` field (first 4 bytes of each ``XYZI`` chunk) is
    needed, so we Range-request chunk headers and *seek past* the voxel payload
    using each chunk's declared content size — the bulky voxel array is never
    downloaded. A `.vox` can hold several models (an optional ``PACK`` chunk
    gives the count, otherwise there is one); their voxel counts are summed,
    then multiplied by ``TRIANGLES_PER_VOXEL``.
    """
    session = session or requests
    # 8-byte file header (magic + version) + 12-byte MAIN chunk header.
    head = _range_get(session, url, 0, 19, timeout)
    if head[:4] != b"VOX ":
        raise TriangleCountError(f"Not a VOX file (bad magic): {url}")

    offset = 20  # past the file header and MAIN header; MAIN's children follow
    num_models = 1
    seen_models = 0
    voxels = 0
    # MagicaVoxel scene-graph chunks can be numerous, but model data always
    # comes first; we stop as soon as every model's XYZI has been read. The
    # bound is just a guard against a malformed/looping file.
    for _ in range(100_000):
        header = _range_get(session, url, offset, offset + 11, timeout)
        if len(header) < 12:
            break
        chunk_id = header[:4]
        content_size = struct.unpack_from("<i", header, 4)[0]
        body = offset + 12
        if chunk_id == b"PACK":
            num_models = struct.unpack("<i", _range_get(session, url, body, body + 3, timeout))[0]
        elif chunk_id == b"XYZI":
            voxels += struct.unpack("<i", _range_get(session, url, body, body + 3, timeout))[0]
            seen_models += 1
            if seen_models >= num_models:
                break
        # Only MAIN has children, so non-MAIN chunks advance by header + content.
        offset = body + content_size
    return voxels * TRIANGLES_PER_VOXEL


def count_triangles(url: str, session: Optional[requests.Session] = None, timeout: int = DEFAULT_TIMEOUT) -> Optional[int]:
    """Dispatch on file extension. Returns ``None`` for unsupported formats."""
    ext = url.rsplit("?", 1)[0].rsplit(".", 1)[-1].lower()
    if ext == "glb":
        return count_triangles_glb(url, session, timeout)
    if ext == "gltf":
        return count_triangles_gltf(url, session, timeout)
    if ext == "obj":
        return count_triangles_obj(url, session, timeout)
    if ext == "vox":
        return count_triangles_vox(url, session, timeout)
    return None


def _range_get(session, url: str, start: int, end: int, timeout: int) -> bytes:
    resp = session.get(url, headers={"Range": f"bytes={start}-{end}"}, timeout=timeout)
    resp.raise_for_status()
    return resp.content
