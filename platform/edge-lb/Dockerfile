FROM haproxy:3.2-alpine
USER root
RUN apk add --no-cache keepalived gettext procps
COPY haproxy.cfg /usr/local/etc/haproxy/haproxy.cfg
COPY keepalived.conf.tmpl /etc/keepalived/keepalived.conf.tmpl
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
