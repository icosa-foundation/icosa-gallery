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
if [[ $DEPLOYMENT_ENV == 'production' ]];
then
    python manage.py run_huey &
    gunicorn -c gunicorn/config.py django_project.wsgi:application
else
    python manage.py run_huey &
    python manage.py runserver 0.0.0.0:8000
fi
