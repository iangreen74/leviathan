-- Leviathan Graph Control Plane Schema
-- Migration 001: Initial schema

-- Events table (append-only, source of truth)
CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(255) NOT NULL UNIQUE,
    event_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL,
    actor_id VARCHAR(255),
    payload JSONB NOT NULL,
    prev_hash VARCHAR(64),
    hash VARCHAR(64) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_events_timestamp ON events(timestamp);
CREATE INDEX idx_events_type ON events(event_type);
CREATE INDEX idx_events_hash ON events(hash);

-- Nodes table (projection from events)
CREATE TABLE IF NOT EXISTS nodes (
    node_id VARCHAR(255) PRIMARY KEY,
    node_type VARCHAR(50) NOT NULL,
    properties JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_nodes_type ON nodes(node_type);
CREATE INDEX idx_nodes_created ON nodes(created_at);

-- Edges table (projection from events)
CREATE TABLE IF NOT EXISTS edges (
    edge_id VARCHAR(512) PRIMARY KEY,
    edge_type VARCHAR(50) NOT NULL,
    from_node VARCHAR(255) NOT NULL,
    to_node VARCHAR(255) NOT NULL,
    properties JSONB,
    created_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (from_node) REFERENCES nodes(node_id) ON DELETE CASCADE,
    FOREIGN KEY (to_node) REFERENCES nodes(node_id) ON DELETE CASCADE
);

CREATE INDEX idx_edges_type ON edges(edge_type);
CREATE INDEX idx_edges_from ON edges(from_node);
CREATE INDEX idx_edges_to ON edges(to_node);
CREATE INDEX idx_edges_from_type ON edges(from_node, edge_type);

-- Artifacts table (content-addressed storage metadata)
CREATE TABLE IF NOT EXISTS artifacts (
    artifact_id VARCHAR(255) PRIMARY KEY,
    sha256 VARCHAR(64) NOT NULL UNIQUE,
    artifact_type VARCHAR(50) NOT NULL,
    size_bytes BIGINT NOT NULL,
    mime_type VARCHAR(100),
    storage_path TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    metadata JSONB
);

CREATE INDEX idx_artifacts_sha256 ON artifacts(sha256);
CREATE INDEX idx_artifacts_type ON artifacts(artifact_type);

-- Projection state (tracks which events have been applied to graph)
CREATE TABLE IF NOT EXISTS projection_state (
    id SERIAL PRIMARY KEY,
    last_event_id VARCHAR(255) NOT NULL,
    last_event_hash VARCHAR(64) NOT NULL,
    last_applied_at TIMESTAMPTZ DEFAULT NOW()
);
