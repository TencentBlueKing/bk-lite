FROM python:3.12
WORKDIR /apps

RUN apt-get update -y && \
    apt-get upgrade -y && \
    apt-get install -y vim supervisor && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ADD ./support-files/release/supervisor/app.conf  /etc/supervisor/conf.d/app.conf
ADD ./support-files/release/supervisor/nats.conf  /etc/supervisor/conf.d/nats.conf
ADD ./support-files/release/supervisor/beat.conf  /etc/supervisor/conf.d/beat.conf
ADD ./support-files/release/supervisor/celery.conf  /etc/supervisor/conf.d/celery.conf

ADD . .
RUN pip install uv
RUN uv sync --all-groups
RUN uv sync --all-extras

RUN chmod +x ./support-files/release/startup.sh
ENTRYPOINT ["/bin/bash","/apps/support-files/release/startup.sh"]