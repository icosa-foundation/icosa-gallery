# Icosa API

Repository for Icosa API

## Docker quick start

Copy the following files:

- `cp example.env .env`
- `cp fastapi/config.example.json fastapi/config.json`
- `cp fastapi/gcp-service-account.example.json fastapi/gcp-service-account.json`

Or create and fill them in manually.

When running in docker, the api service needs its host specified as `db` instead of `localhost` where `db` is the postgres service name. This is currently set in the `dblocation` key inside `config.json`.

Before running for the first time, build the project:

`docker compose build`

To run as if from a fresh install if you have already run the setup process before:

    TODO - explain what this deletes and what this retains

`docker compose build --no-cache --force-rm`

Then:

`docker compose up -d`

TODO: When running  `docker compose up -d` for the first time, the api service may start before postgres is fully available and fail to start. Subsequent runs should work as expected, so if you find that the initial migrations didn't run, and your database is empty, try:

`docker compose down`

`docker compose up -d`

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

## With a .dump file

`docker cp <db.dump> ig-db:/opt/`

`docker exec -it ig-db bash`

Then from inside the container:

`pg_restore --data-only -U icosa -d icosa /opt/<db.dump>`

## With a .sql file

`docker cp <db.sql> ig-db:/opt/`

`docker exec -it ig-db bash`

Then from inside the container:

`psql -U icosa`

Then from inside the postgres shell:

Make sure you are connected to the correct database:

`\c`

You should see `You are now connected to database "icosa" as user "icosa".`

Import the sql data:

`\i /opt/db.sql`


## Running updated versions of the code

There are 3 scenarios and respective actions to take:

### You've updated your .env files

`docker compose down`

`docker compose build`

`docker compose up`

### Incoming code has updated requirements.txt/requirements.in

`docker compose down`

`docker compose build`

`docker compose up`

### Incoming code has updated anything else

`docker compose restart`

