-- Relational Database Initialization Script (PostgreSQL / MySQL compatible schema)
-- Created for Knowledge Gateway Relational SQL Data Source

CREATE TABLE IF NOT EXISTS knowledge_articles (
    id SERIAL PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    category VARCHAR(100) NOT NULL,
    tags TEXT NOT NULL,
    content TEXT NOT NULL,
    author VARCHAR(100) DEFAULT 'system',
    status VARCHAR(50) DEFAULT 'active',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS system_configs (
    id SERIAL PRIMARY KEY,
    config_key VARCHAR(150) UNIQUE NOT NULL,
    config_value TEXT NOT NULL,
    scope VARCHAR(50) NOT NULL,
    description TEXT NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS system_audit_logs (
    id SERIAL PRIMARY KEY,
    event_type VARCHAR(100) NOT NULL,
    actor VARCHAR(100) NOT NULL,
    details TEXT NOT NULL,
    logged_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Seed knowledge_articles records
INSERT INTO knowledge_articles (title, category, tags, content, author, status) VALUES
(
    'Enterprise OAuth 2.0 PKCE Authentication Rails',
    'authentication',
    'oauth, google, identity, auth, loopback',
    'Enterprise client authenticates users via Google OAuth 2.0 PKCE flow. The application spins up a local ephemeral loopback HTTP server on 127.0.0.1:<port> to capture the OAuth redirect code, exchanges it for an ID token, and stores refresh credentials in the secure OS Keychain.',
    'security.architect',
    'active'
),
(
    'Multi-Source Knowledge Gateway Architecture',
    'architecture',
    'knowledge, gateway, rag, okf, sql, onnx, redis',
    'The Knowledge Gateway architecture departs from single-source RAG by establishing a unified gateway. This combines Open Knowledge Format (OKF) deterministic graphs, Qdrant vector embeddings, local git repositories, filesystem docs, and Postgres relational records, with re-ranking powered by an ONNX neural model and caching via Redis and in-memory LRU.',
    'platform.lead',
    'active'
),
(
    'Microservice IPC Communication Protocol',
    'core',
    'ipc, rust, api, gateway, networking',
    'Service frontend renderer communicates with native core using secure IPC commands and event listeners. Sensitive system operations (keychain access, process spawning, file system watchers) are isolated to backend processes with strict capability-based security boundaries.',
    'platform.team',
    'active'
),
(
    'PCI-DSS Compliance for Core Payment Rails',
    'compliance',
    'pci-dss, payment, security, vault',
    'All transaction payloads must satisfy PCI-DSS requirement 3.4 by encrypting cardholder data with AES-256-GCM via HashiCorp Vault. No raw card numbers or CVV codes may be persisted in PostgreSQL tables or logging streams.',
    'compliance.officer',
    'active'
),
(
    'Enterprise PostgreSQL Disaster Recovery & Failover',
    'infrastructure',
    'disaster-recovery, postgres, failover, rto, rpo',
    'PostgreSQL primary database operates with streaming replication to a multi-AZ standby. Automatic health failover triggers within 45 seconds under unrecoverable network partition or storage degradation.',
    'sre.team',
    'active'
);

-- Seed system_configs records
INSERT INTO system_configs (config_key, config_value, scope, description) VALUES
(
    'auth.oauth.client_id',
    'enterprise-auth-client.apps.googleusercontent.com',
    'identity',
    'OAuth Client ID used by the client for federated single sign-on.'
),
(
    'gateway.vector.embedding_model',
    'text-embedding-3-small',
    'gateway',
    'OpenAI-compatible embedding model deployed for Qdrant RAG dense vector indexing.'
),
(
    'gateway.onnx.reranker_path',
    'models/reranker.onnx',
    'gateway',
    'Path to the local ONNX neural re-ranking model used for consolidating multi-source results.'
),
(
    'storage.postgres.max_connections',
    '50',
    'database',
    'Maximum concurrent connection pool size for PostgreSQL knowledge tables.'
),
(
    'security.vault.transit_mount',
    'transit/enterprise-keys',
    'security',
    'HashiCorp Vault transit engine mount path for cryptographic operations.'
);
