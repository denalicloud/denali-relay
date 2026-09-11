FROM debian:trixie-slim

RUN apt-get update && apt-get install -y \
    postfix \
    sasl2-bin \
    libsasl2-2 \
    libsasl2-modules \
    libsasl2-modules-db \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY scripts/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 25 587

ENTRYPOINT ["/entrypoint.sh"]
