FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN useradd --create-home --uid 10001 app
WORKDIR /app

# Dependencies first, so a code change does not reinstall them.
COPY requirements.lock .
RUN pip install -r requirements.lock

COPY . .
# collectstatic only reads settings; these values are never used to connect anywhere.
RUN DJANGO_SECRET_KEY=collectstatic-only DATABASE_URL=sqlite:///unused MONGO_URL=mongodb://unused \
    python manage.py collectstatic --noinput

USER app
EXPOSE 8000
# Workers come from WEB_CONCURRENCY, which gunicorn reads by itself.
CMD ["gunicorn", "shopfinder.wsgi:application", "--bind", "0.0.0.0:8000", "--access-logfile", "-"]
