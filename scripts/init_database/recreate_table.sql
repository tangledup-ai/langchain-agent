-- Drop the index first (if it exists)
DROP INDEX IF EXISTS idx_messages_conversation;
DROP INDEX IF EXISTS idx_messages_pipeline;

-- Drop the messages table (if it exists)
DROP TABLE IF EXISTS messages;

-- Recreate the messages table with TEXT conversation_id
-- Note: UUID extension is no longer needed since conversation_id is TEXT
CREATE TABLE messages (
    id BIGSERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    pipeline_id TEXT,
    message_type VARCHAR(10) NOT NULL CHECK (message_type IN ('human', 'ai', 'tool')),
    content TEXT NOT NULL,
    sequence_number INTEGER NOT NULL CHECK (sequence_number >= 0),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Recreate the index for fast retrieval of all messages in a conversation (in order)
CREATE INDEX idx_messages_conversation ON messages (conversation_id, sequence_number);

-- Prevent duplicate sequence numbers within the same conversation.
CREATE UNIQUE INDEX idx_messages_conversation_sequence_unique
    ON messages (conversation_id, sequence_number);

-- Index for fast lookup by pipeline_id
CREATE INDEX idx_messages_pipeline ON messages (pipeline_id);

