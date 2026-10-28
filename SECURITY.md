# Security Policy

## Supported Versions

We actively maintain and provide security updates for the latest releases on the `main` branch.

| Version | Supported          |
| ------- | ------------------ |
| `main`  | :white_check_mark: |
| < 0.1.0 | :x:                |

---

## Reporting a Vulnerability

The **Knowledge Gateway** maintainers take the security of our application and users seriously. If you discover a security vulnerability, we appreciate your help in disclosing it responsibly.

### How to Report

Please **DO NOT report security issues via public GitHub issues, discussions, or pull requests.**

Instead, report vulnerabilities through one of the following channels:

1. **GitHub Private Vulnerability Reporting (Preferred)**:
   Navigate to the [Security tab](https://github.com/karthikrameshdev/knowledge-gateway/security/advisories/new) of the repository and click **Report a vulnerability**. This creates a secure, private advisory where you can collaborate directly with the maintainers.

2. **Email**:
   If Private Vulnerability Reporting is unavailable, send an encrypted or direct email to:
   **karthik.ramesh.dev@gmail.com** with the subject `[SECURITY] knowledge-gateway Vulnerability Report`.

### What to Include in Your Report

To help us triage and resolve the issue quickly, please include:
- A description of the vulnerability and its potential impact.
- Clear steps to reproduce the issue (proof-of-concept script, payloads, or sample request payloads).
- Any affected components (e.g., Connector endpoints, SQL queries, Redis cache deserialization, ONNX inference runtime).
- Your proposed remediation or mitigation, if known.

### Response & Disclosure Process

- **Acknowledgement**: We will acknowledge receipt of your report within 48 hours.
- **Assessment**: We will confirm the vulnerability and determine the severity and impact.
- **Fix & Patch**: A fix will be developed and tested in a private fork.
- **Release & Credit**: We will release a security patch and publicly credit your responsible disclosure (unless you prefer to remain anonymous).
