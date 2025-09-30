# Getting Started

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
> [!TIP]
> **Windows users** should make sure that line endings are configured correctly. Don't commit line ending changes; instead:

Configure git to use Windows line endings:

``` bash
git config core.eol lf
git config core.autocrlf input
```
Update git's attributes for all source files. Either edit `.git\info\attributes` directly or:

``` bash
Add-Content .git\info\attributes "* text eol=lf"
```

Clean up the repo (this shouldn't result in a commit):

``` bash
git rm --cached -r .
git reset --hard
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

Icosa gallery has two main, public-facing, components: The Web UI and the API. These can be run at the same domain, e.g. `example.com` for the Web UI and `example.com/api` for the API.

You can alternatively choose to run the api at a subdomain of the main site, e.g `example.com` and `api.example.com` respectively.

> [!NOTE]
> You **must** choose one of these; there is no default and the application will fail to run if you do not choose.

#### If you wish to use the single-domain configuration:

``` bash
cp nginx/templates/api-no-subdomain.conf.template nginx/templates/default.conf.template
```

And edit the following values in your `.env` file:

``` bash
DEPLOYMENT_HOST_WEB=example.com
DEPLOYMENT_HOST_API=example.com
```

#### If you wish to run the api at a subdomain:

``` bash
cp nginx/templates/api-subdomain.conf.template nginx/templates/default.conf.template
```

And edit the following values in your `.env` file:

``` bash
DEPLOYMENT_HOST_WEB=example.com
DEPLOYMENT_HOST_API=api.example.com
```

#### For local deployment only

> [!NOTE]
> For either of the above domain configurations, if you are planning on running this software on your own machine instead of a web host, you'll want to set your `.env` file to something like:

``` bash
DEPLOYMENT_HOST_WEB=example.localhost
DEPLOYMENT_HOST_API=api.example.localhost
```

You'll then need to configure your local hosts file so that these domains are routed properly. Your `/etc/hosts` file (on MacOS and Linux) or `C:\Windows\System32\drivers\etc\hosts` file (on Windows) would then look something like this:

```
127.0.0.1       example.localhost
127.0.0.1       api.example.localhost
```

### Step 4 - Build and run the project

``` bash
docker compose build
docker compose up -d
```

If you've updated your `.env` file as above, visit http://example.localhost

Unlike some Docker setups, you will need to visit your url on the normal port 80. The web service's internal port of 8000 will not work because nginx needs to serve requests to the web application.

> [!NOTE]
> The `-d` flag in the above command runs Docker Compose in the background so that you can continue to use your terminal or disconnect from your ssh session without stopping the server. If you wish to stop the server after using this command you can type the following:

``` bash
docker compose down
```

> [!NOTE]
> The django service waits for postgres to come up before running itself. When running `docker compose up -d` for the first time, postgres might take longer than on subsequent runs. This is normal. See `Quirks` in the [main project readme](./README.md) for more info.

### Step 5 - Add sketch assets dependencies

We currently have a dependency on a separate project: https://github.com/icosa-foundation/icosa-sketch-assets

We haven't yet settled on a build step for this dependency so for now, you will need to make sure that the `brushes`, `environments`, and `textures` directories of that project are placed inside the directory as defined in the settings file: `ICOSA_SKETCH_ASSETS_LOCATION`.

For now, to do this manually, clone the repository to your host machine and then copy the assets into this project using something like the following.

Create the necessary directories for the static assets inside the container:

``` bash
docker exec -it ig-web bash -c "mkdir -p /opt/static/icosa-sketch-assets/"
docker exec -it ig-web bash -c "mkdir -p /opt/static/icosa-sketch-assets-experimental/"
docker exec -it ig-web bash -c "mkdir -p /opt/static/icosa-sketch-assets-previous/"
```

Then copy the files from all three respective branches in the repo.

``` bash
git clone https://github.com/icosa-foundation/icosa-sketch-assets
cd icosa-sketch-assets
docker cp brushes ig-web:/opt/static/icosa-sketch-assets/brushes
docker cp textures ig-web:/opt/static/icosa-sketch-assets/textures
docker cp environments ig-web:/opt/static/icosa-sketch-assets/environments

git checkout versions/previous && git pull
docker cp brushes/. ig-web:/opt/static/icosa-sketch-assets-previous/brushes/
docker cp textures/. ig-web:/opt/static/icosa-sketch-assets-previous/textures/
docker cp environments/. ig-web:/opt/static/icosa-sketch-assets-previous/environments/

git checkout versions/experimental && git pull
docker cp brushes/. ig-web:/opt/static/icosa-sketch-assets-experimental/brushes/
docker cp textures/. ig-web:/opt/static/icosa-sketch-assets-experimental/textures/
docker cp environments/. ig-web:/opt/static/icosa-sketch-assets-experimental/environments/
```

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

