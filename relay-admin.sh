#!/bin/bash
# relay-admin.sh — Denali PRO SA relay user management
# Usage: ./relay-admin.sh <command> [arguments]

set -uo pipefail

SASL_PASSWD="/opt/relay/postfix/sasl/sasl_passwd"
QUOTA_CONF="/opt/relay/policy-daemon/quota.conf"
COMPOSE_DIR="/opt/relay"

REDIS_PASS=$(grep requirepass /opt/relay/redis/redis.conf | awk '{print $2}')

usage() {
    echo "Usage: $0 <command> [arguments]"
    echo ""
    echo "Available commands:"
    echo "  add <user@domain> <password> [quota]   Add user (default quota: 1000)"
    echo "  remove <user@domain>                   Remove user"
    echo "  passwd <user@domain> <new_password>    Change password"
    echo "  quota <user@domain> <new_limit>        Change monthly quota"
    echo "  list                                   List users and quotas"
    echo "  stats                                  Redis counters for current month"
    echo "  reset <user@domain>                    Reset user's monthly counter"
    exit 1
}

redis_cmd() {
    docker compose -f "$COMPOSE_DIR/docker-compose.yml" exec -T redis \
        redis-cli -a "$REDIS_PASS" "$@" < /dev/null 2>/dev/null | grep -v "Warning" || true
}

restart_postfix() {
    echo "→ Restarting postfix..."
    docker compose -f "$COMPOSE_DIR/docker-compose.yml" restart postfix
}

restart_policy() {
    echo "→ Restarting policy-daemon..."
    docker compose -f "$COMPOSE_DIR/docker-compose.yml" restart policy-daemon
}

restart_webui() {
    echo "→ Restarting webui..."
    docker compose -f "$COMPOSE_DIR/docker-compose.yml" restart webui
}

cmd_add() {
    local userhost="$1"
    local pass="$2"
    local quota="${3:-1000}"

    [ -z "$userhost" ] || [ -z "$pass" ] && { echo "Error: specify user@domain and password"; exit 1; }

    if grep -q "^${userhost}" "$SASL_PASSWD" 2>/dev/null; then
        echo "Error: user $userhost already exists"
        exit 1
    fi

    printf '%s\t%s\n' "$userhost" "$pass" >> "$SASL_PASSWD"
    chmod 600 "$SASL_PASSWD"

    sed -i "/^\[quotas\]/a ${userhost} = ${quota}" "$QUOTA_CONF"

    echo "✓ User $userhost added with quota $quota"
    restart_postfix
    restart_policy
}

cmd_remove() {
    local userhost="$1"
    [ -z "$userhost" ] && { echo "Error: specify user@domain"; exit 1; }

    if ! grep -q "^${userhost}" "$SASL_PASSWD" 2>/dev/null; then
        echo "Error: user $userhost not found"
        exit 1
    fi

    local user="${userhost%@*}"
    local domain="${userhost#*@}"

    sed -i "/^${userhost}/d" "$SASL_PASSWD"
    sed -i "/^${userhost}/d" "$QUOTA_CONF"

    docker compose -f "$COMPOSE_DIR/docker-compose.yml" exec -T postfix \
        saslpasswd2 -d -u "$domain" "$user" < /dev/null 2>/dev/null || true

    local key="quota:$(date +%Y-%m):${userhost}"
    redis_cmd del "$key" > /dev/null

    echo "✓ User $userhost removed"
    restart_postfix
    restart_policy
    restart_webui
}

cmd_passwd() {
    local userhost="$1"
    local newpass="$2"
    [ -z "$userhost" ] || [ -z "$newpass" ] && { echo "Error: specify user@domain and new password"; exit 1; }

    if ! grep -q "^${userhost}" "$SASL_PASSWD" 2>/dev/null; then
        echo "Error: user $userhost not found"
        exit 1
    fi

    sed -i "s|^${userhost}\t.*|${userhost}\t${newpass}|" "$SASL_PASSWD"
    chmod 600 "$SASL_PASSWD"

    echo "✓ Password updated for $userhost"
    restart_postfix
    restart_webui
}

cmd_quota() {
    local userhost="$1"
    local newquota="$2"
    [ -z "$userhost" ] || [ -z "$newquota" ] && { echo "Error: specify user@domain and quota"; exit 1; }

    if ! grep -q "^${userhost}" "$QUOTA_CONF" 2>/dev/null; then
        echo "Error: user $userhost not found in quota.conf"
        exit 1
    fi

    sed -i "s|^${userhost} = .*|${userhost} = ${newquota}|" "$QUOTA_CONF"

    echo "✓ Quota updated for $userhost: $newquota"
    restart_policy
}

cmd_list() {
    echo "=== Relay users and quotas ==="
    printf "%-35s %s\n" "USER" "MONTHLY QUOTA"
    echo "---------------------------------------------------"
    while IFS=$'\t' read -r userhost pass; do
        [ -z "$userhost" ] && continue
        quota=$(grep "^${userhost}" "$QUOTA_CONF" 2>/dev/null | awk -F' = ' '{print $2}')
        quota="${quota:-default}"
        printf "%-35s %s\n" "$userhost" "$quota"
    done < "$SASL_PASSWD"
}

cmd_stats() {
    local month count quota
    month=$(date +%Y-%m)
    echo "=== Send counters — $month ==="
    printf "%-35s %s\n" "USER" "SENT"
    echo "---------------------------------------------------"
    while IFS=$'\t' read -r userhost pass; do
        [ -z "$userhost" ] && continue
        count=$(docker compose -f "$COMPOSE_DIR/docker-compose.yml" exec -T redis \
            redis-cli -a "$REDIS_PASS" get "quota:${month}:${userhost}" \
            < /dev/null 2>/dev/null | grep -v "Warning" | tr -d '[:space:]') || true
        [ -z "$count" ] || [ "$count" = "nil" ] && count="0"
        quota=$(grep "^${userhost}" "$QUOTA_CONF" 2>/dev/null | awk -F' = ' '{print $2}')
        quota="${quota:-default}"
        printf "%-35s %s\n" "$userhost" "${count}/${quota}"
    done < "$SASL_PASSWD"
}

cmd_reset() {
    local userhost="$1"
    [ -z "$userhost" ] && { echo "Error: specify user@domain"; exit 1; }

    local key="quota:$(date +%Y-%m):${userhost}"
    redis_cmd del "$key" > /dev/null
    echo "✓ Counter reset for $userhost"
}

# Main
case "${1:-}" in
    add)    cmd_add "${2:-}" "${3:-}" "${4:-}" ;;
    remove) cmd_remove "${2:-}" ;;
    passwd) cmd_passwd "${2:-}" "${3:-}" ;;
    quota)  cmd_quota "${2:-}" "${3:-}" ;;
    list)   cmd_list ;;
    stats)  cmd_stats ;;
    reset)  cmd_reset "${2:-}" ;;
    *)      usage ;;
esac
