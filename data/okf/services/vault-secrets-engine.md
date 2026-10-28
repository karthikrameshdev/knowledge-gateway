---
id: vault-secrets-engine
type: service
title: HashiCorp Vault Secrets Engine
version: 1.15.2
status: active
updated_at: "2026-10-18T14:15:00Z"
verified_by: security-platform@weftkit.internal
resource: vault-prod
tags:
  - vault
  - secrets
  - encryption
  - kms
relations:
  governed_by:
    - zero-trust-network
---

# HashiCorp Vault Secrets Engine

Manages all static and dynamic cryptographic secrets across the infrastructure.

## Secret Leases
- Database credentials rotate automatically every 60 minutes.
- Encryption-at-rest keys for Qdrant vector databases and PostgreSQL are managed through Vault Transit Engine.
- PKI root certificate authority issues mutual-TLS certificates to microservices.
