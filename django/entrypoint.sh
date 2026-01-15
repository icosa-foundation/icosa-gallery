#!/bin/bash

UP_TEST_RETRIES=10
until bash -c '(echo > /dev/tcp/db/5432) > /dev/null 2>&1' || [ $UP_TEST_RETRIES -eq 0 ]; do
    echo "Waiting for Postgres server, $((UP_TEST_RETRIES--)) remaining attempts..."
    sleep 1
done

python manage.py migrate
python manage.py collectstatic --noinput

if [[ -v DEPLOYMENT_HOST_WEB ]];
then
    echo "Setting $DEPLOYMENT_HOST_WEB as the default domain"
    python manage.py shell -c \
    "from django.contrib.sites.models import Site; Site.objects.filter(domain='example.com').update(domain='$DEPLOYMENT_HOST_WEB', name='$DEPLOYMENT_HOST_WEB')"
fi


echo "Running in $DEPLOYMENT_ENV mode"
python manage.py run_huey &
gunicorn -c gunicorn_config/config.py django_project.asgi:application
