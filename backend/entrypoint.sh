#!/bin/sh
# Runs before every container start: migrations and the plan catalogue must
# exist before the app serves a single request, in dev and in prod alike.
set -e

python manage.py migrate --noinput
python manage.py seed_plans

# Whitenoise's manifest storage needs the hashed files to exist on disk
# before it can resolve {% static %} - notably the vendored Scalar bundle at
# apps/core/static/core/vendor/. Cheap and idempotent, safe on every start.
python manage.py collectstatic --noinput

exec "$@"
