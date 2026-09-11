FROM debian:trixie-slim

RUN apt-get update && apt-get install -y \
    opendkim \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /etc/opendkim/keys && \
    chown -R opendkim:opendkim /etc/opendkim

EXPOSE 8891

CMD ["sh", "-c", "opendkim -f -l -x /etc/opendkim/opendkim.conf 2>&1 | tee /var/log/opendkim.log"]
