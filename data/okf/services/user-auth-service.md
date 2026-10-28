---
id: user-auth-service
type: service
title: User Authentication & Identity Service
version: 3.0.1
status: active
updated_at: "2026-10-20T11:00:00Z"
verified_by: identity-team@weftkit.internal
resource: auth-prod
tags:
  - auth
  - jwt
  - ed25519
  - oauth
relations:
  depends_on:
    - vault-secrets-engine
  governed_by:
    - zero-trust-network
---

# User Authentication & Identity Service

The core authentication provider issuing Ed25519-signed JWT tokens and handling OAuth 2.0 PKCE.

## Supported Protocols
- Google Identity OpenID Connect (OIDC).
- Loopback desktop redirect for Tauri desktop applications (WeftKit client).
- API token signing keys rotate dynamically via HashiCorp Vault.
