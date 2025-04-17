# Icosa Gallery

> [!NOTE]
> This codebase is not currently at a stable release and everything is subject to change. If you want to use this then reach out to us. There may be breaking changes and refactors that you will want to know about first.

Icosa Gallery is an open source 3D model hosting solution, intended as a replacement for Google's Poly.

![Icosa Gallery](https://github.com/icosa-foundation/icosa-gallery/blob/main/icosa-gallery-screenshot.png?raw=true)

## Getting Started

See [the installation guide](./INSTALL.md) for details.

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

### Docker's startup order

Despite the web container depending on the postgres container, Docker makes no guarantees about the status of various services once the containers have started.

We check for postgres availability by listening to `/dev/tcp/db/5432` from within the django container at the start of `entrypoint.sh`. This improves the initial run experience for new users, but can result in delayed startups if you change the postgres service name or port in `docker-compose.yml` for any reason. In that case, you will need to change the values in `entrypoint.sh`, too.

# Usage and customisation

Once you have a superuser, you can log in to the admin at <example.com>/admin

From there you, can change some settings for allowing signup and other site behaviours at <example.com>/admin/constance/config/

> [!NOTE]
> While this application supports uploading via an undocumented API, we would encourage users to only upload via the web UI until this area of the site is stabilised.

## Managements commands

There are a number of managements commands you can run from the Django container to make administering the site easier.

To run a management command, enter the Django container:

`docker exec -it ig-web bash`

Then run the command:

`python manage.py <my_command>`

The following custom commands are available:

### `create_apikey [username]`

Creates a JWT for the specified Django user, identified by their username, for accessing the API. Expires after two weeks, by default. Used as an alternative to the device login flow provided by Open Brush.

Arguments:

`--username`

The username of the Django user.

### `save_all_assets [options]`

Runs a bulk save of all assets in the database. Most useful when denormalising metadata after, for example, bulk importing assets from somewhere.

Options:

`--verbose`

Prints logs to stdout

`--background`

Queues the bulk save as a background task so that you are free to log out while the job continues.

`--kill`

Kills all running jobs.

`--resume`

Resumes the last killed job.

### `create_django_user_from_asset_owner [id]`

Creates a Django user based on an existing Asset Owner.

Arguments:

`--id`

The primary key of the Asset Owner from which to create a Django User.

## Customising the look and feel

Some basic experience with working with Django is currently required. We are working to make customisations easier out of the box, but for now, follow the below instructions.

First, you'll need to fork this repo. 

Then, to make changes to any html template, you can do so without modifying the base application code by including your own templates in a new Django app.

See (the Django tutorial for starting a new app)[https://docs.djangoproject.com/en/5.2/intro/tutorial01/#creating-the-polls-app]. You'll need to run Django commands from inside the docker container: `docker exec -it ig-web bash`.

Then, add your new app to `INSTALLED_APPS` in `django/django_project/settings.py` *before* the `"icosa"` app.

Inside your app's templates directory, duplicate the path of the template you'd like to override. For example to completely override the base template, create `base.html` inside `django/my_app/templates/`. You can include any custom styles and other static assets in your app's static folder: `django/my_app/static/`.

# Contributing

This project is still in its early days. If you've forked this repo or are using it as is and you'd like to contribute a change, fix or improvement, please get in touch; we'd love to chat!

## Code style

Currently running `ruff check --select I --fix - | ruff format --line-length 120 -` on python files. We'll provide official code style guidelines soon.
