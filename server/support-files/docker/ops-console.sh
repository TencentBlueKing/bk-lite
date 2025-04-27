python manage.py migrate
python manage.py createcachetable django_cache
python manage.py collectstatic --noinput
supervisord -n