---
id: zero-trust-network
type: policy
title: Zero Trust Network Architecture Policy
version: 2.5.0
status: active
updated_at: "2026-08-14T08:00:00Z"
verified_by: ciso@weftkit.internal
tags:
  - zero-trust
  - network
  - mtls
  - security
relations:
  applies_to:
    - vault-secrets-engine
    - user-auth-service
---

# Zero Trust Network Architecture Policy

All communications between microservices, gateway layers, and data stores must enforce mutual TLS (mTLS) with cryptographically validated client certificates issued by the internal Vault PKI.
No perimeter network trust is granted; all requests are authenticated and authorized per call.
