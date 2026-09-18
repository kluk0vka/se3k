FROM python:3.12-slim
ARG SERVICE
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY common /tmp/common
COPY ${SERVICE}/requirements.txt /tmp/requirements.txt
RUN pip install /tmp/common -r /tmp/requirements.txt && rm -rf /tmp/common /tmp/requirements.txt
COPY ${SERVICE}/app ./app
RUN useradd -u 10001 app
USER 10001
EXPOSE 8000
CMD ["opentelemetry-instrument", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
