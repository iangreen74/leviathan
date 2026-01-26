-- Leviathan Event Journal Schema
-- Append-only event log for event sourcing

CREATE TABLE IF NOT EXISTS events (
    id SERIAL PRIMARY KEY,
    event_id VARCHAR(255) UNIQUE NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    actor_id VARCHAR(255) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Indexes for common queries
    INDEX idx_events_event_type (event_type),
    INDEX idx_events_timestamp (timestamp),
    INDEX idx_events_actor_id (actor_id),
    INDEX idx_events_payload_target_id ((payload->>'target_id')),
    INDEX idx_events_payload_attempt_id ((payload->>'attempt_id'))
);

-- Ensure append-only semantics (no updates or deletes)
CREATE OR REPLACE FUNCTION prevent_event_modification()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'Events are append-only and cannot be modified or deleted';
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER prevent_event_update
    BEFORE UPDATE ON events
    FOR EACH ROW
    EXECUTE FUNCTION prevent_event_modification();

CREATE TRIGGER prevent_event_delete
    BEFORE DELETE ON events
    FOR EACH ROW
    EXECUTE FUNCTION prevent_event_modification();

-- Comments
COMMENT ON TABLE events IS 'Append-only event journal for Leviathan event sourcing';
COMMENT ON COLUMN events.event_id IS 'Unique event identifier (deterministic)';
COMMENT ON COLUMN events.event_type IS 'Event type (e.g., attempt.started, topo.indexed)';
COMMENT ON COLUMN events.timestamp IS 'Event timestamp (ISO 8601)';
COMMENT ON COLUMN events.actor_id IS 'Actor that generated the event';
COMMENT ON COLUMN events.payload IS 'Event payload (JSON)';
