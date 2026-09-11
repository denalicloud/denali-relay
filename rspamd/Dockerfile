FROM debian:trixie-slim

RUN apt-get update && apt-get install -y \
    rspamd \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 11332 11333 11334

CMD ["rspamd", "-f", "-u", "root", "-g", "root"]
