# Icosa Gallery

![Icosa Gallery](https://github.com/icosa-foundation/icosa-gallery/blob/main/icosa-gallery-screenshot.png?raw=true)

## Installation

### Prerequisites

This assumes you've already installed Docker.
If you're not sure the best way to do this, the simplest option is to install the Docker Desktop App.

### Configuration Files

Copy the supplied example config files to their correct locations:

```
cp example.env .env
```

TODO Explain what each of these files are for and what values you need to change

TODO this is confusing ^

Before running for the first time, build the project:

`docker compose build`

To run as if from a fresh install if you have already run the setup process before:

TODO - explain what this deletes and what this retains

`docker compose build --no-cache --force-rm`

Then:

`docker compose up -d`

TODO Explain -d and why you might or might not want it

TODO: When running  `docker compose up -d` for the first time, the api service may start before postgres is fully available and fail to start. Subsequent runs should work as expected, so if you find that the initial migrations didn't run, and your database is empty, try:

```
docker compose down
docker compose up -d
```

(We're working to make this better for first-time users.)

## Services

### Direct from localhost

- web front end: localhost:3000
- fastapi backend: localhost:8000
- django backend: localhost:8001

### Using the included proxy

Let's say, you've set `DEPLOYMENT_HOST` in `.env` to `icosa.localhost`, you can access the following services thus:

- web front end: http://icosa.localhost
- fastapi backend: http://api.icosa.localhost
- django backend: http://api-django.icosa.localhost

You'll need to add the following line to your `/etc/hosts` file (on MacOS and Linux)
or C:\Windows\System32\drivers\etc\hosts (on Windows)

```
127.0.0.1       icosa.localhost
127.0.0.1       icosa-api.localhost
127.0.0.1       icosa-api-django.localhost
```

## Seeding the database

TODO - explain what "seeding" means and why you'd want to

TODO - explain "from inside the container"

## With a .dump file

```
docker cp <db.dump> ig-db:/opt/
docker exec -it ig-db bash
```

Then from inside the container:

`pg_restore --data-only -U icosa -d icosa /opt/<db.dump>`

## With a .sql file

```
docker cp <db.sql> ig-db:/opt/
docker exec -it ig-db bash
```

Then from inside the container:

`psql -U icosa`

Then from inside the postgres shell:

Make sure you are connected to the correct database:

`\c`

You should see `You are now connected to database "icosa" as user "icosa".`

Import the sql data:

`\i /opt/db.sql`


## Running updated versions of the code

TODO - how are people meant to distinguish between 2 and 3?
Give them a single, safe default action even if it's a bit slower
Is (3) even needed? Seems to happen automatically for me.

There are 3 possible scenarios:


### 1. You've updated your own .env files

```
docker compose down
docker compose build
docker compose up
```

### 2. Incoming code has updated requirements.txt/requirements.in

```
docker compose down`
docker compose build`
docker compose up
```

### 3. Incoming code has updated anything else

`docker compose restart`
