#!/usr/bin/env python3
"""
Postfix quota policy daemon — TCP server mode
Denali PRO SA — mx517.servers.li
"""

import socketserver
import logging
import configparser
from datetime import datetime
import redis

CONFIG_FILE = "/etc/quota.conf"
LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 10031

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE)
    return cfg

def get_redis_client(cfg):
    return redis.Redis(
        host=cfg.get("redis", "host", fallback="redis"),
        port=cfg.getint("redis", "port", fallback=6379),
        password=cfg.get("redis", "password", fallback=None),
        db=cfg.getint("redis", "db", fallback=0),
        decode_responses=True
    )

def get_quota(cfg, username):
    if cfg.has_option("quotas", username):
        return cfg.getint("quotas", username)
    return cfg.getint("quotas", "default", fallback=1000)

def get_redis_key(username):
    month = datetime.now().strftime("%Y-%m")
    return f"quota:{month}:{username}"

def check_and_increment(r, cfg, username):
    quota = get_quota(cfg, username)
    key = get_redis_key(username)
    current = r.get(key)
    current = int(current) if current else 0

    if current >= quota:
        logging.warning(f"REJECT {username}: {current}/{quota}")
        return False, current, quota

    pipe = r.pipeline()
    pipe.incr(key)
    pipe.expire(key, 60 * 60 * 24 * 35)
    pipe.execute()
    logging.info(f"OK {username}: {current+1}/{quota}")
    return True, current + 1, quota

class PolicyHandler(socketserver.StreamRequestHandler):
    def handle(self):
        cfg = load_config()
        r = get_redis_client(cfg)

        attrs = {}
        while True:
            try:
                line = self.rfile.readline().decode().strip()
            except Exception:
                break

            if line == "":
                if not attrs:
                    break

                username = attrs.get("sasl_username", "").strip()

                if not username:
                    logging.warning(f"REJECT no auth: sender={attrs.get('sender','?')}")
                    response = "action=REJECT Authentication required\n\n"
                else:
                    allowed, count, quota = check_and_increment(r, cfg, username)
                    if allowed:
                        response = "action=DUNNO\n\n"
                    else:
                        response = (
                            f"action=REJECT Monthly quota exceeded "
                            f"({count}/{quota}). Contact support@denali.pro\n\n"
                        )

                self.wfile.write(response.encode())
                self.wfile.flush()
                attrs = {}
            elif "=" in line:
                k, v = line.split("=", 1)
                attrs[k.strip()] = v.strip()

class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True

if __name__ == "__main__":
    logging.info(f"Policy daemon listening on {LISTEN_HOST}:{LISTEN_PORT}")
    with ThreadedTCPServer((LISTEN_HOST, LISTEN_PORT), PolicyHandler) as server:
        server.serve_forever()
