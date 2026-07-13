Until this project is made a completely separate app, you can change the look and feel by overriding template files. We've included some standard configuration which means you can make changes in a separate app while not polluting the main repo git history. This guide assumes you have followed the instructions in INSTALL.md and are using the docker setup.

It is assumed that your python and pip binaries are named `python` and `pip` respectively. Please change these if they differ on your system (e.g. `python3` or `pip3`).

To create the app that will house your changes:
1. `cd` to the project root.
2. Create a python virtualenv: `python -m venv venv`
3. Activate the virtualenv: `. ./venv/bin/activate`
4. `cd django`
5. Install requirements for the project: `pip install -r requirements.in`
6. Create the custom app that will house your overrides (please use this exact name): `./manage.py startapp icosa_custom_overrides`
7. Edit your `.env` file to include `DJANGO_USE_CUSTOM_OVERRIDES=True`
9. Copy files you want to overwrite from the `icosa` app to the `icosa_custom_overrides` app, preserving the full directory structure exactly.
8. Make your changes and restart docker services: `docker compose down && docker compose up -d`
