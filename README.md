# Icosa API

Repository for Icosa API

## Docker quick start

Copy the following files:

- `cp example.env .env`
- `cp config.example.json config.json`
- `cp gcp-service-account.example.json gcp-service-account.json`

Or create and fill them in manually.

When running in docker, the api service needs its host specified as `db` instead of `localhost` where `db` is the postgres service name. This is currently set in the `dblocation` key inside `config.json`.

Before running for the first time, build the project:

`docker compose build`

Then:

`docker compose up -d`

TODO: When running  `docker compose up -d` for the first time, the api service may start before postgres is fully available and fail to start. Subsequent runs should work as expected.

