#!/bin/bash

python manage.py migrate
python manage.py collectstatic --noinput
echo "Running in $DEPLOYMENT_ENV mode"
if [[ $DEPLOYMENT_ENV == 'production' ]]; then
    gunicorn django_project.wsgi:application --bind 0.0.0.0:8000 --timeout 900
else
    python manage.py runserver 0.0.0.0:8000
fi
