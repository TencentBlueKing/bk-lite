python manage.py migrate
python manage.py createcachetable django_cache
python manage.py collectstatic --noinput

python manage.py init_realm
python manage.py init_realm_resource

supervisord -n