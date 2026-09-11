#!/bin/bash
set -e
chown root:root /var/spool/postfix
chmod 755 /var/spool/postfix
chown -R postfix:postdrop /var/spool/postfix/maildrop 2>/dev/null || true
chmod 730 /var/spool/postfix/maildrop 2>/dev/null || true

if [ -f /etc/postfix/sasl_passwd ]; then
    while read -r line; do
        [ -z "$line" ] && continue
        userhost=$(echo "$line" | awk '{print $1}')
        pass=$(echo "$line" | awk '{print $2}')
        [ -z "$userhost" ] || [ -z "$pass" ] && continue
        user="${userhost%@*}"
        domain="${userhost#*@}"
        echo "$pass" | saslpasswd2 -p -c -u "$domain" "$user"
        echo "Created SASL user: $user@$domain"
    done < /etc/postfix/sasl_passwd
    chown postfix:sasl /etc/sasldb2 2>/dev/null || true
    chmod 640 /etc/sasldb2 2>/dev/null || true
fi

# Genera transport.db da transport se presente
if [ -f /etc/postfix/transport ]; then
    cp /etc/postfix/transport /tmp/transport
    postmap /tmp/transport
    cp /tmp/transport.db /etc/postfix/transport.db
    echo "Generated transport.db"
fi

for dir in active bounce corrupt defer deferred flush hold incoming trace; do
    chown -R postfix:postfix /var/spool/postfix/$dir 2>/dev/null || true
done
exec postfix start-fg
