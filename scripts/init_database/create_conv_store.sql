-- Create the messages table
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

-- Index for fast lookup by pipeline_id
CREATE INDEX IF NOT EXISTS idx_messages_pipeline ON messages (pipeline_id);