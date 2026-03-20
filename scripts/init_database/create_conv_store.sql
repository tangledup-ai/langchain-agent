-- Create the messages table
-- This script runs in the ai_conversations database context
CREATE TABLE IF NOT EXISTS messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    pipeline_id TEXT,
    message_type VARCHAR(10) NOT NULL CHECK (message_type IN ('human', 'ai', 'tool')),
    content TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast retrieval of all messages in a conversation (in order)
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages (conversation_id, sequence_number);

-- Prevent duplicate sequence numbers within the same conversation.
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_conversation_sequence_unique
    ON messages (conversation_id, sequence_number);

-- Index for fast lookup by pipeline_id
CREATE INDEX IF NOT EXISTS idx_messages_pipeline ON messages (pipeline_id);

-- Grant permissions to app user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO myapp_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO myapp_user;