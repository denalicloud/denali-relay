# Host Configuration

Files to be deployed manually on the host system (not inside Docker containers).

## fail2ban

Protects SMTP ports 25 and 587 from SASL brute-force attacks.

### Install

```bash
cp fail2ban/filter.d/relay-postfix-sasl.conf /etc/fail2ban/filter.d/
cp fail2ban/jail.d/relay-postfix-sasl.conf /etc/fail2ban/jail.d/
systemctl restart fail2ban
fail2ban-client status relay-postfix-sasl
```

## systemd — relay-postfix-log

Forwards Postfix container logs to `/var/log/relay-postfix.log` on the host.
Required by fail2ban to read Postfix authentication failures.

### Install

```bash
touch /var/log/relay-postfix.log
cp systemd/relay-postfix-log.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now relay-postfix-log
```
