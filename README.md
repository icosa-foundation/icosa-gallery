# Icosa Gallery

> [!NOTE]
> This codebase is not currently at a stable release and everything is subject to change. If you want to use this then reach out to us. There may be breaking changes and refactors that you will want to know about first.

![Icosa Gallery](https://github.com/icosa-foundation/icosa-gallery/blob/main/docs/images/icosa-gallery-screenshot.jpg?raw=true)

Icosa Gallery is an open source 3D model hosting solution, intended as a replacement for the defunct [Google Poly](https://en.wikipedia.org/wiki/Poly_(website)).

Our official instance is available at [https://icosa.gallery](https://icosa.gallery) and we have attempted to restore as much public content from Poly as possible. We'd like to thank [Archive Team](https://wiki.archiveteam.org/) volunteers for their timely preservation work and the [Internet Archive](https://archive.org) for hosting the historically valuable work.

We aim to develop integration into a wide range of apps and platforms and current integrations including [Open Brush](https://openbrush.app), [Open Blocks](https://openblocks.app), [Blender](https://blender.org) and [Godot](https://godotengine.org). See the section below on "Clients, plugins and integrations" for more info.

## Philosophy and Tech Stack

The backend code is built on Django - a clean, mature and stable web framework with a strong ecosystem.

We aim to avoid heavy javascript frameworks on the front end as we are firm believers in [progressive enhancement](https://en.wikipedia.org/wiki/Progressive_enhancement). We mainly use vanilla JS with a light scattering of HTMX where it is useful.

Docker is currently used for deployment and development but we are working to become agnostic about deployment technologies.

We currently support PostgreSQL as the database backend but this is not a hard dependency and it should be simple to swap out your relational database of choice (from local tests SQLite seems perfectly viable)

* [Docker Compose](https://docs.docker.com/compose/)
* [Django](https://www.djangoproject.com/)
* [PostgreSQL](https://www.postgresql.org/)
* [Django Ninja](https://django-ninja.rest-framework.com/)
* [HTMX](https://htmx.org/)
* [three.js](https://threejs.org/)

## Getting Started

See [the installation guide](docs/INSTALL.md) for details.

## API

![api.png](https://github.com/icosa-foundation/icosa-gallery/blob/main/docs/images/api.jpg?raw=true)

The official instance of the Icosa Gallery has OpenAPI docs here: [https://api.icosa.gallery/v1/docs](https://api.icosa.gallery/v1/docs).

If you deploy your own instance the docs will be at `api.yoursite.com/v1/docs/` or `yoursite.com/api/v1/docs/` depending on your configuration.

## Clients, plugins and integrations

### Web

![gallery-viewer.png](https://github.com/icosa-foundation/icosa-gallery/blob/main/docs/images/gallery-viewer.jpg?raw=true)

* Three.js based viewer: [Gallery Viewer](https://github.com/icosa-foundation/gallery-viewer)
* Open Brush Material Importer (used by gallery-viewer): [Gallery Viewer](https://github.com/icosa-foundation/gallery-viewer)

We would like to add support for [Babylon.js](https://www.babylonjs.com/) and [PlayCanvas](https://playcanvas.com/) based viewers in the future. If you are interested in helping with this please get in touch.

### Unity 

![unity-client.png](https://github.com/icosa-foundation/icosa-gallery/blob/main/docs/images/unity-client.jpg?raw=true)

Asset browser and importer for editor and runtime use: [Icosa API Client](https://github.com/icosa-foundation/icosa-api-client-unity)

### Blender

![blender.png](https://github.com/icosa-foundation/icosa-gallery/blob/main/docs/images/blender.jpg?raw=true)

Plugin for browsing and importing assets from Icosa Gallery: [Icosa Gallery Blender Plugin](https://github.com/icosa-foundation/icosa-blender-plugin)

### Godot

![godot.png](https://github.com/icosa-foundation/icosa-gallery/blob/main/docs/images/godot.jpg?raw=true)

Asset browser and importer for editor and runtime use: [Godot Addon](https://github.com/icosa-foundation/icosa-godot-addon)

### Hubs

![hubs.png](https://github.com/icosa-foundation/icosa-gallery/blob/main/docs/images/hubs.jpg?raw=true)

We have pull requests to integrate Icosa Gallery as an asset source in [Hubs](https://hubsfoundation.org/):

https://github.com/Hubs-Foundation/Spoke/pull/1301
https://github.com/Hubs-Foundation/reticulum/pull/723

## Funding

This project is funded through [NGI0 Entrust](https://nlnet.nl/entrust), a fund established by [NLnet](https://nlnet.nl) with financial support from the European Commission's [Next Generation Internet](https://ngi.eu) program. Learn more at the [NLnet project page](https://nlnet.nl/project/IcosaGallery).

[<img src="https://nlnet.nl/logo/banner.png" alt="NLnet foundation logo" width="20%" />](https://nlnet.nl)
[<img src="https://nlnet.nl/image/logos/NGI0_tag.svg" alt="NGI Zero Logo" width="20%" />](https://nlnet.nl/entrust)

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
