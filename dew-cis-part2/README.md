# LDAP Query — Dew CIS Solutions
## Ref: 60/2026

## Setup

```bash
docker compose up -d
# Wait 15 seconds for OpenLDAP to seed data
pip3 install -r requirements.txt
```

## Run the script

```bash
python3 ldap_query.py developers
python3 ldap_query.py ops
python3 ldap_query.py finance
python3 ldap_query.py hr
python3 ldap_query.py phantom   # error case
```

## Expected output (developers)

Group: developers (gidNumber: 2001)
Members:
alice | Alice Mwangi | /home/alice
bob | Bob Otieno | /home/bob

## Expected output (phantom — error case)

Error: group 'phantom' not found in directory.

Exit code: 1

## Run tests

```bash
pytest test_ldap.py -v
```

## phpLDAPadmin (browser UI)

URL: http://localhost:8090
Login DN: cn=admin,dc=dewcis,dc=com
Password: adminpass
