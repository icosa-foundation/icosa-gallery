# Getting Started

This guide is for deploying this software to a web target. If you want to try out the software locally first, see the [installation guide](./INSTALL.md).

## Software Requirements

Install the following software if you haven't already:

- [git](https://git-scm.com/)
- [Docker](https://docs.docker.com/engine/install/)
- [Docker Compose](https://docs.docker.com/compose/install/)


## Install via Docker Compose

Below are the steps to deploy Icosa Gallery with Docker Compose. This is currently the recommended (and only official) way to run Icosa Gallery.

This guide assumes some familiarity with the command line on your chosen platform.

### Step 1 - Download the repository

``` bash
git clone https://github.com/icosa-foundation/icosa-gallery.git
cd icosa-gallery
```

> [!NOTE]
> Further steps assume you are now in the `icosa-gallery` directory.

### Step 2 - Populate the .env file with your custom values

You can configure Icosa Gallery to your needs using an `.env` file. Copy the provided example file into place and amend its default values.

``` bash
cp example.env .env
```

Complete documentation of every variable and its purpose can be found in the `.env` file itself.

> [!IMPORTANT]
> The application will not start without you first having populated the following values with something secure, for instance the output of something like [this](https://django-secret-key-generator.netlify.app/):

``` bash
DJANGO_SECRET_KEY=
JWT_SECRET_KEY=
```

> [!NOTE]
> So that Docker can correctly parse your environment variables, try to ensure none of them contain the `$` character. If a value must contain `$`, then wrap the value in single quotes. For example:

`MY_BAD_PASSWORD='pa$$word'`

### Step 3 - Choose a domain configuration

> [!WARNING]
> You **must** choose one of the below options; there is no default and the application will fail to run if you do not choose. 

> [!NOTE]
> For trying the software out on your local machine, skip to the [local configuration](#local-configuration) below. This is the easiest way to get started. For other options, read on.

Icosa gallery has two main, public-facing, components: The Web UI and the API. These can be run at the same domain, e.g. `example.com` for the Web UI and `example.com/api` for the API.

You can alternatively choose to run the api at a subdomain of the main site, e.g `example.com` and `api.example.com` respectively.

#### local configuration:

``` bash
cp nginx/templates/local.conf.template nginx/templates/default.conf.template
```

And edit the following values in your `.env` file:

``` bash
DEPLOYMENT_HOST_WEB=localhost
DEPLOYMENT_HOST_API=localhost
DEPLOYMENT_ENV=local
```

#### single-domain configuration:

``` bash
cp nginx/templates/api-no-subdomain.conf.template nginx/templates/default.conf.template
```

And edit the following values in your `.env` file:

``` bash
DEPLOYMENT_HOST_WEB=example.com
DEPLOYMENT_HOST_API=example.com
```

#### subdomain configuration:

``` bash
cp nginx/templates/api-subdomain.conf.template nginx/templates/default.conf.template
```

And edit the following values in your `.env` file:

``` bash
DEPLOYMENT_HOST_WEB=example.com
DEPLOYMENT_HOST_API=api.example.com
```
### Step 4 - Build and run the project

``` bash
docker compose build
docker compose up -d
```

If you've updated your `.env` file as above, visit http://example.

> [!NOTE]
> The django service waits for postgres to come up before running itself. When running `docker compose up -d` for the first time, postgres might take longer than on subsequent runs. This is normal. See `Quirks` in the [main project readme](../README.md) for more info.

### Step 5 - Add sketch assets dependencies

To show assets generated in Open Brush, we use brushes, and textures from [a separate codebase](https://github.com/icosa-foundation/icosa-sketch-assets). You can pull this repo and copy the required assets into place by running:

`./install-sketch-assets.sh`

> [!NOTE]
> You should run this file from the same directory that contains the file.

Alternatively, link to the sketch assets somewhere on the web by putting the following in your `.env` file (for example):

`ICOSA_SKETCH_ASSETS_LOCATION=https://icosa.gallery/static/sketch-assets`

### Step 6 - Setup an admin user

Type the following commands to create an admin user. You'll then be able to log in as this user at http://example.localhost/admin

Access the Docker container where the web service is running:

``` bash
docker exec -it ig-web bash
```

Create a superuser to log into the admin with. You'll be prompted for the username, email address and password to use:

``` bash
./manage.py createsuperuser
```

Exit the Docker container back to your normal shell:

``` bash
exit
```

### Step 7 - Configure SSL

While this installation will listen to requests on https, we do not currently manage SSL certificates for you. The simplest option to secure your site with an SSL certificate and accept traffic over https is to configure a service like [cloudflare](cloudflare.com).

