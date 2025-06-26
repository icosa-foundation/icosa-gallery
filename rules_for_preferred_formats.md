# How we chose preferred formats

This document describes the logic behind how we chose which format to use in the viewer, and which formats and urls we used to present downloads to the user. It is my hope that this can explain what our thinking was before we baked this logic into the database in the form of "preffered for viewer" and "hidden from download" boolean fields.


## Preferred formats for the viewer

There can be only one preferred format for the viewer. We constructed a dictionary with the following keys which were passed to the viewer code (hereinafter referred to as the "_format dict_"):

- `format`: <Format Model> A reference to the format we chose.
- `url`: <Optional String> A url from where the resource can be downloaded by the viewer code. Usually derived from the format's `root_resource.internal_url_or_none()` method. If `None` we could not use this for our chosen format, so would return `None` for the preferred format.
- `materialUrl`: <Optional String> Used **only** with blocks formats where we chose `obj` as the format. Explained in more detail below.
- `resource`: <Resource Model> A reference to the chosen format's `root_resource`.

### General flow

Choosing a format is a two-pass process. Firstly, we would try each of the following steps until we can return something or `None`.

#### First Pass

1. Do we have a `preferred_format_override` set? If so, use that in all cases. Populate the _format dict_ directly using the format and its `root_resource`'s properties.
2. Is `has_blocks` True? If so, return the format chosen from that code path or `None`. (See more below.)
3. Attempt to return the first format we find with a role of POLYGONE_GLB_FORMAT or POLYGONE_GLTF_FORMAT.
4. Attempt to return the first format we find with a role of UPDATED_GLTF_FORMAT.
5. Attempt to return the first format we find with a role of ORIGINAL_GLTF_FORMAT.
6. If we didn't return anything from any of the above steps, try to return a format from our fallback rules. (See more below.)
7. Return `None`.

#### Second Pass

1. Did the First Pass return `None`? If so, return `None` overall.
2. In all cases except during step 2 of the First Pass (blocks), the `url` field of the _format dict_ could be `None`. If it is, return `None` overall.
3. Finally, return the _format dict_.

### Blocks

In the general flow, we hit this decision tree if the asset has at least one format of type BLOCKS:

1. Check if the asset has at least one format of type GLTF2. If not...
    1. Find the asset's first format which has a type of OBJ and has an existing `root_resource`.
    2. Find this format's first non-root resource and assume (but don't check) that this is an mtl file.
    3. Populate and return a _format dict_ with the additional `materialUrl` key taken from the previous step.
    4. If we didn't find a format in step 1, return `None`.
2. ...if we did find a GLTF2 format:
    1. Try to get that format's `root_resource` and return `None` if it doesn't have one.
    2. If we have a format with a `root_resource`, populate the _format dict_ but, for the `url`, add our suffixed version that was uploaded to a different location in our storage. (See Suffixing, below).
3. Return the first of what we got from steps 1 or 2.


### Fallback rules

In the general flow, we hit this decision tree if we could not return anything from steps 1-5:

1. Gather a dictionary of all formats and populate a _format dict_ from each one. The keys for this are each format's `format_type`.
2. If we find a `format_type` we are interested in, in the dictionary's keys, return that _format dict_. We check for the existence of each key **in order** from the following list:
    - GLB
    - GLTF2
    - GLTF1 (named GLTF at the time)
    - OBJ
3. If none of the above exists, return `None`.
4. Continue to the Second Pass.

## Preferred formats for download

We chose what formats to show in the download list using these rules:

1. If the logged-in user owns the asset, show all formats, otherwise:
2. If the asset's license is all rights reserved, show nothing.
3. If the asset's license is non-remixable, show formats with the following roles:
    - ORIGINAL_OBJ_FORMAT
    - ORIGINAL_FBX_FORMAT
    - USD_FORMAT
    - GLB_FORMAT
    - ORIGINAL_TRIANGULATED_OBJ_FORMAT
    - USDZ_FORMAT
    - UPDATED_GLTF_FORMAT
    - USER_SUPPLIED_GLTF
4. If the asset's licence is remixable, show formats from rule 3, plus:
    - TILT_NATIVE_GLTF
    - TILT_FORMAT
    - BLOCKS_FORMAT

For each of the formats shown, we then chose how to compile the download pack of resource data based on the following rules:

1. If the format has a zip archive url, link to that, otherwise:
2. If the format has just one resource, link to that, otherwise:
3. If the format has more than one resource, include a list of files that we use to dynamically zip when the client clicks the link. This list of files is compiled based on the Multi-file rules below.
4. If, during the above checks, one or more of the resources does not have a url, local or otherwise, do not show it in the download list.

### Multi-file rules

The following rules determine what urls we provide in the list for the clien to dynamically zip up:

1. If the format has role POLYGONE_GLTF_FORMAT, we provide all the original urls from each of the format's resources, plus a separate set of our suffixes urls (see Suffixing below). The client is free to choose the suffixed or non-suffixed version for downloads. Otherwise:
2. If all files in all resources are either locally hosted, or are external but the urls are in our CORS whitelist, return this list. Otherwise:
3. If the format has role UPDATED_GLTF_FORMAT, we assume we can safely perform step 1 as if the format was POLYGONE_GLTF_FORMAT **except** we only offer the suffixed versions (see Suffixing below).

# Suffixing

Some of the original gltf2 files associated with our polygone dataset did not work with our viewer. We uploaded a completely different set of files to a separate storage location that were known to work and completely supplant the files that were part of the original Blocks upload.

They differ in that the suffix "_(GLTFupdated)" was added to the filename, and the base folder in our storage was changed from "icosa" to "poly".

## when we add the suffixed filename

To summarise and collect from the steps above: we offer a version of gltf files with the suffix `_(GLTFupdated)` in a few scenarios (see usage for the `suffix` function in the codebase):

### For the viewer

Only when `asset.has_blocks == True`, inside the `handle_blocks_preferred_format` function.

### For downloads (per format)

When these conditions are met:

- The format has more than resource without an external url AND:
- EITHER the role is POLYGONE_GLTF_FORMAT (in which case we offer both the suffixed and non-suffixed version);
- OR the role is UPDATED_GLTF_FORMAT and we have no local files.

