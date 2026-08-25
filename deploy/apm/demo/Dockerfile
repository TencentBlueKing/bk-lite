FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 demo \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin demo

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY service.py loadgen.py ./
USER 10001:10001
EXPOSE 8080

CMD ["python", "/app/service.py"]
