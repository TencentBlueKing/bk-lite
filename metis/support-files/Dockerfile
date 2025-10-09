FROM bklite/metis:base

WORKDIR /app

ADD . .

ADD ./support-files/service.conf /etc/supervisor/conf.d/service.conf

ENTRYPOINT ["/bin/bash","/app/support-files/startup.sh"]