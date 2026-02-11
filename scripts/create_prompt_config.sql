-- A prompt_set groups a full collection of prompts together.
-- Each pipeline can have many sets (versions, A/B variants, etc.);
-- exactly one should be marked is_active per pipeline.
CREATE TABLE IF NOT EXISTS prompt_sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id VARCHAR(64) NOT NULL,
    name VARCHAR(128) NOT NULL,
    description TEXT DEFAULT '',
    is_active BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    list Varchar(255) DEFAULT ''   -- tool_set list for client_tool_manager
);

-- Fast lookup of the active set for a pipeline
CREATE INDEX IF NOT EXISTS idx_prompt_sets_pipeline_active
    ON prompt_sets(pipeline_id, is_active);

-- Each prompt belongs to a prompt_set, keyed by prompt_key.
CREATE TABLE IF NOT EXISTS prompt_templates (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    prompt_set_id UUID NOT NULL REFERENCES prompt_sets(id) ON DELETE CASCADE,
    prompt_key VARCHAR(64) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(prompt_set_id, prompt_key)
);

CREATE INDEX IF NOT EXISTS idx_prompt_templates_set_id
    ON prompt_templates(prompt_set_id);
