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

**Note:** Further steps assume you are now in the `icosa-gallery` directory.

### Step 2 - Populate the .env file with your custom values

You can configure Icosa Gallery to your needs using an `.env` file. Copy the provided example file into place and amend its default values.

``` bash
cp example.env .env
```

Complete documentation of every variable and its purpose can be found in the `.env` file itself.

**Important:** The application will not start without you first having populated the following values
with something secure, for instance the output of something like [this](https://django-secret-key-generator.netlify.app/):

``` bash
DJANGO_SECRET_KEY=
JWT_SECRET_KEY=
```

**Note:** So that Docker can correctly parse your environment variables, try to ensure none of them contain the `$` character. If a value must contain `$`, then wrap the value in single quotes. For example:

`MY_BAD_PASSWORD='pa$$word'`


### Step 3 - Choose a domain configuration

Icosa gallery has two main, public-facing, components: The Web UI and the API. These can be run at the same domain, e.g. `example.com` for the Web UI and `example.com/api` for the API.

You can alternatively choose to run the api at a subdomain of the main site, e.g `example.com` and `api.example.com` respectively.

#### If you wish to use the single-domain configuration:

``` bash
ln -s nginx/templates/api-no-subdomain.conf.template nginx/templates/default.conf.template
```

And edit the following values in your `.env` file:

``` bash
DEPLOYMENT_HOST_WEB=example.com
DEPLOYMENT_HOST_API=example.com
```

#### If you wish to run the api at a subdomain:

``` bash
ln -s nginx/templates/api-subdomain.conf.template nginx/templates/default.conf.template
```

And edit the following values in your `.env` file:

``` bash
DEPLOYMENT_HOST_WEB=example.com
DEPLOYMENT_HOST_API=api.example.com
```

### Step 3½ - For local deployment only

**Note:** For either of the above domain configurations, if you are planning on running this software on your own machine instead of a web host, you'll want to set your `.env` file to something like:

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

**Note:** The `-d` flag in the above command runs Docker Compose in the background so that you can continue to use your terminal or disconnect from your ssh session without stopping the server. If you wish to stop the server after using this command you can type the following:

``` bash
docker compose down
```

**Note:** When running  `docker compose up -d` for the first time, the api service may start before postgres is fully available and fail to start. Subsequent runs should work as expected, so if you find that the software shows database-related errors on startup:

``` bash
docker compose down
docker compose up -d
```

We're working to make this better for first-time users.

### Step 5 - Setup an admin user

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

### Step 6 - Configure SSL

While this installation will listen to requests on https, we do not currently manage SSL certificates for you. The simplest option to secure your site with an SSL certificate and accept traffic over https is to configure a service like [cloudflare](cloudflare.com).

