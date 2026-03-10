-- A prompt_set groups a full collection of prompts together.
-- This script runs in the ai_conversations database context
-- Each pipeline can have many sets (versions, A/B variants, etc.);
-- exactly one should be marked is_active per pipeline.
CREATE TABLE IF NOT EXISTS prompt_sets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id VARCHAR(64) NOT NULL,
    graph_id VARCHAR(64),
    name VARCHAR(128) NOT NULL,
    description TEXT DEFAULT '',
    is_active BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),
    list Varchar(255) DEFAULT '',  -- tool_set list for client_tool_manager
    api_key TEXT DEFAULT ''        -- provider api key used to run pipeline
);

-- Backward-compatible migration for existing deployments.
ALTER TABLE prompt_sets
ADD COLUMN IF NOT EXISTS graph_id VARCHAR(64);
ALTER TABLE prompt_sets
ADD COLUMN IF NOT EXISTS api_key TEXT DEFAULT '';
UPDATE prompt_sets
SET graph_id = pipeline_id
WHERE graph_id IS NULL;

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

-- Grant permissions to app user
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO myapp_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO myapp_user;

-- Seed: initial prompt set for lang_agent/graphs/routing.py
-- The pipeline_id can be used by RoutingConfig.pipeline_id to load these prompts.
INSERT INTO prompt_sets (pipeline_id, graph_id, name, description, is_active, list)
SELECT
    'routing',
    'routing',
    'default',
    'Initial prompt set for RoutingGraph nodes',
    true,
    ''
WHERE NOT EXISTS (
    SELECT 1
    FROM prompt_sets
    WHERE pipeline_id = 'routing'
      AND name = 'default'
);

INSERT INTO prompt_templates (prompt_set_id, prompt_key, content)
SELECT ps.id, t.prompt_key, t.content
FROM prompt_sets ps
JOIN (
    VALUES
        ('route_prompt', '决定用工具或者聊天'),
        ('chat_prompt', '正常聊天时说什么'),
        ('tool_prompt', '如何用工具')
) AS t(prompt_key, content)
    ON true
WHERE ps.pipeline_id = 'routing'
  AND ps.name = 'default'
ON CONFLICT (prompt_set_id, prompt_key)
DO UPDATE SET
    content = EXCLUDED.content,
    updated_at = now();

-- Seed: default prompt set for xiaozhan agent (RoutingGraph)
INSERT INTO prompt_sets (pipeline_id, graph_id, name, description, is_active, list)
SELECT
    'xiaozhan',
    'routing',
    'default',
    'Default prompt set for xiaozhan (RoutingGraph)',
    true,
    ''
WHERE NOT EXISTS (
    SELECT 1
    FROM prompt_sets
    WHERE pipeline_id = 'xiaozhan'
      AND name = 'default'
);

INSERT INTO prompt_templates (prompt_set_id, prompt_key, content)
SELECT ps.id, t.prompt_key, t.content
FROM prompt_sets ps
JOIN (
    VALUES
        ('route_prompt', '决定用工具或者聊天'),
        ('chat_prompt', '正常聊天时说什么'),
        ('tool_prompt', '如何用工具')
) AS t(prompt_key, content)
    ON true
WHERE ps.pipeline_id = 'xiaozhan'
  AND ps.name = 'default'
ON CONFLICT (prompt_set_id, prompt_key)
DO UPDATE SET
    content = EXCLUDED.content,
    updated_at = now();

-- Seed: initial prompt set for lang_agent/graphs/react.py
-- ReactGraph uses prompt key "sys_prompt" (see default_key in build_prompt_store).
INSERT INTO prompt_sets (pipeline_id, graph_id, name, description, is_active, list)
SELECT
    'react',
    'react',
    'default',
    'Initial prompt set for ReactGraph',
    true,
    ''
WHERE NOT EXISTS (
    SELECT 1
    FROM prompt_sets
    WHERE pipeline_id = 'react'
      AND name = 'default'
);

INSERT INTO prompt_templates (prompt_set_id, prompt_key, content)
SELECT ps.id, 'sys_prompt', '如何用工具'
FROM prompt_sets ps
WHERE ps.pipeline_id = 'react'
  AND ps.name = 'default'
ON CONFLICT (prompt_set_id, prompt_key)
DO UPDATE SET
    content = EXCLUDED.content,
    updated_at = now();

-- Seed: default prompt set for blueberry agent (ReactGraph)
INSERT INTO prompt_sets (pipeline_id, graph_id, name, description, is_active, list)
SELECT
    'blueberry',
    'react',
    'default',
    'Default prompt set for blueberry (ReactGraph)',
    true,
    ''
WHERE NOT EXISTS (
    SELECT 1
    FROM prompt_sets
    WHERE pipeline_id = 'blueberry'
      AND name = 'default'
);

INSERT INTO prompt_templates (prompt_set_id, prompt_key, content)
SELECT ps.id, 'sys_prompt', '如何用工具'
FROM prompt_sets ps
WHERE ps.pipeline_id = 'blueberry'
  AND ps.name = 'default'
ON CONFLICT (prompt_set_id, prompt_key)
DO UPDATE SET
    content = EXCLUDED.content,
    updated_at = now();

-- Seed: initial prompt set for lang_agent/graphs/deepagents_qt.py
-- DeepAgent uses prompt key "sys_prompt" with DB-first, file-fallback loading.
INSERT INTO prompt_sets (pipeline_id, graph_id, name, description, is_active, list)
SELECT
    'deepagent',
    'deepagent',
    'default',
    'Initial prompt set for DeepAgent',
    true,
    ''
WHERE NOT EXISTS (
    SELECT 1
    FROM prompt_sets
    WHERE pipeline_id = 'deepagent'
      AND name = 'default'
);

INSERT INTO prompt_templates (prompt_set_id, prompt_key, content)
SELECT ps.id, 'sys_prompt', '你是一个擅长调用工具和处理文件任务的深度代理。'
FROM prompt_sets ps
WHERE ps.pipeline_id = 'deepagent'
  AND ps.name = 'default'
ON CONFLICT (prompt_set_id, prompt_key)
DO UPDATE SET
    content = EXCLUDED.content,
    updated_at = now();
