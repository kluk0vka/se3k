#!/bin/sh
set -eu
envsubst < /etc/keepalived/keepalived.conf.tmpl > /etc/keepalived/keepalived.conf
haproxy -W -db -f /usr/local/etc/haproxy/haproxy.cfg &
exec keepalived --dont-fork --log-console --log-detail --vrrp -f /etc/keepalived/keepalived.conf
