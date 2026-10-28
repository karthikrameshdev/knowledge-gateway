"""Synthetic documents for explicitly enabled local demos only."""
DEMO_DOCUMENTS = [
                {
                    "id": "enterprise_rag_core_arch",
                    "title": "Enterprise Native Core & IPC Bridge",
                    "content": "Enterprise desktop architecture leverages native bindings. The frontend client invokes secure IPC commands to access system resources, native file watchers, and OS keychains.",
                    "category": "architecture",
                    "tags": ["native", "ipc", "desktop", "architecture"],
                },
                {
                    "id": "enterprise_rag_auth_flow",
                    "title": "Enterprise OAuth PKCE Authentication Rails",
                    "content": "Client authentication is performed via Google Identity with loopback redirects on 127.0.0.1. Tokens are verified with Ed25519 signing keys and cached securely in the OS Keychain.",
                    "category": "security",
                    "tags": ["auth", "google", "oauth", "pkce"],
                },
                {
                    "id": "enterprise_rag_vault_transit",
                    "title": "HashiCorp Vault Transit Engine Encryption",
                    "content": "Database credentials rotate every hour. Transit engine handles encryption-at-rest for PostgreSQL and vector embeddings without storing plain cryptographic keys on worker nodes.",
                    "category": "security",
                    "tags": ["vault", "transit", "encryption", "kms"],
                },
                {
                    "id": "enterprise_rag_pci_dss",
                    "title": "PCI-DSS Level 1 Compliance & Tokenization",
                    "content": "Cardholder payment transactions are tokenized end-to-end. Cardholder data environment (CDE) is isolated with strict zero-trust network boundaries and auditable access logs.",
                    "category": "compliance",
                    "tags": ["pci-dss", "payment", "compliance", "stripe"],
                },
                {
                    "id": "enterprise_rag_disaster_recovery",
                    "title": "Automated Multi-Region Failover Architecture",
                    "content": "Multi-region disaster recovery ensures sub-5-minute RTO and zero RPO. PostgreSQL standby read replicas are promoted automatically when health check ping fails.",
                    "category": "infrastructure",
                    "tags": ["disaster-recovery", "failover", "rto", "rpo", "postgres"],
                },
            ]
