# WeftKit OAuth 2.0 PKCE Security Specification

## Protocol Details
- Flow: Authorization Code Flow with Proof Key for Code Exchange (PKCE).
- Code Verifier: Cryptographically random 128-character high-entropy string using SHA-256 code challenge.
- Redirect URI: `http://127.0.0.1:<random-port>/auth/callback` managed via Tauri dynamic loopback listener.
- Token Storage: Secure OS Keychain (macOS Keychain via Security framework, Windows Credential Manager).
