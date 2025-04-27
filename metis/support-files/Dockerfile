FROM python:3.12

RUN apt-get update && \
    apt-get install -y libhdf5-dev vim  unzip curl pkg-config libssl-dev libffi-dev supervisor \
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libxcomposite1 libxdamage1 libxfixes3\
    libxrandr2 libgbm1 libxkbcommon0 libasound2 libatspi2.0-0 libgl1-mesa-glx&& \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

ADD . .

RUN pip install -r ./requirements/requirements.in
RUN pip install -r ./requirements/requirements-dev.in
RUN playwright install chromium
ADD ./support-files/service.conf /etc/supervisor/conf.d/service.conf

RUN python ./server.py download_models
ENTRYPOINT ["/bin/bash","/app/support-files/startup.sh"]