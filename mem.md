# Memory: Bayer Chat API Integration

## Date: 2026-04-21

## Issue: Pipeline Not Showing in Frontend UI

### Problem
After adding `bayer_simple` to the pipeline registry (`configs/pipeline_registry.json`), the pipeline was not appearing in the frontend UI sidebar. The backend API `/v1/pipelines` correctly returned the pipeline, but the frontend did not display it.

### Root Cause
The frontend UI uses **two different data sources**:
1. **Pipeline Registry** (`/v1/pipelines`) - From `configs/pipeline_registry.json`
2. **Graph Configs** (`/v1/graph-configs`) - From PostgreSQL `prompt_sets` table

The sidebar renders from `displayConfigItems` which comes from `configItems` (the `/v1/graph-configs` endpoint), NOT from `/v1/pipelines`. 

The pipeline registry entry alone is not sufficient - there must be a corresponding database entry in the `prompt_sets` table AND prompt templates in the `prompt_templates` table.

### Solution

Three steps are required to make a new pipeline visible in the frontend:

#### Step 1: Add to Pipeline Registry
Edit `configs/pipeline_registry.json`:
```json
{
    "pipelines": {
        "bayer_simple": {
            "enabled": true,
            "config_file": "configs/pipelines/bayer_simple.yaml",
            "graph_id": "react",
            "llm_name": "gemini-3-flash"
        }
    }
}
```

#### Step 2: Create Database Entry
Insert a record into the `prompt_sets` table:
```sql
INSERT INTO prompt_sets (
    pipeline_id, 
    graph_id, 
    name, 
    description, 
    is_active, 
    list, 
    api_key
) VALUES (
    'bayer_simple', 
    'react', 
    'default', 
    'Default prompt set for bayer_simple (ReactGraph)', 
    true, 
    '', 
    'mga-4947a0d8ccf2bdbdad70d8d9b2684b3098e11588'
)
RETURNING id;
```

#### Step 3: Add Prompt Templates
Insert the required prompts into `prompt_templates`:
```sql
INSERT INTO prompt_templates (prompt_set_id, prompt_key, content)
VALUES (
    '4d622ca4-c2e2-4b08-8ad0-7315914eae07',  -- from step 2
    'sys_prompt', 
    'You are a helpful AI assistant powered by the Bayer Chat API...'
);
```

### Verification

Check the pipeline appears in both APIs:
```bash
# Check pipeline registry
curl http://localhost:8500/v1/pipelines

# Check graph configs
curl "http://localhost:8500/v1/graph-configs?pipeline_id=bayer_simple"

# Check prompt templates
curl http://localhost:8500/v1/graph-configs/bayer_simple/{prompt_set_id}
```

### Frontend Data Flow

```
Frontend Sidebar
       ↓
displayConfigItems ← chooseDisplayItemsByPipeline(visibleConfigItems)
       ↓
visibleConfigItems ← configItems.filter(...)
       ↓
configItems ← /v1/graph-configs (from DB prompt_sets table)
       ↓
PostgreSQL: prompt_sets + prompt_templates
```

The `running` state from `/v1/pipelines` is only used to show the "Running"/"Stopped" status indicator, not for the list itself.

### Bayer API Configuration

The `.env` file contains:
```bash
BAYER_API_KEY="mga-4947a0d8ccf2bdbdad70d8d9b2684b3098e11588"
BAYER_BASE_URL="https://chat.int.bayer.com/api/v2/"
```

The pipeline config file (`configs/pipelines/bayer_simple.yaml`) uses:
- Model: `gemini-3-flash`
- Provider: `openai` (OpenAI-compatible)
- Base URL: From BAYER_BASE_URL
- API Key: From BAYER_API_KEY

## Issue: `base_url` Was Not Editable In Frontend

### Problem
The agent editor exposed `api_key` and `llm_name`, but not `base_url`. For OpenAI-compatible providers like Bayer, that meant the UI could regenerate YAML using the default provider URL instead of the intended custom endpoint.

### Root Cause
- `EditableAgent` in `frontend/src/App.tsx` had no `baseUrl` field.
- `buildGraphParams()` did not include `base_url`.
- `lang_agent/front_api/build_server_utils.py` accepted `llm_name` and `api_key`, but not `base_url`.
- `lang_agent/fastapi_server/front_apis.py` only extracted deepagent-specific `graph_params`, so existing YAML `base_url` values were not sent back to the frontend editor.

### Fix
- Added a `base_url` input to the frontend editor.
- Added `baseUrl` to the editor state and included it in `graph_params` when saving.
- Updated backend graph param extraction to expose `base_url` for all graph types.
- Updated pipeline builder functions to forward both `--pipeline.base-url` and graph-level `--base-url` to the Tyro config builder.
- Corrected `configs/pipelines/bayer_simple.yaml` to use the Bayer API key, Bayer base URL, and `gemini-3-flash`.

### Verification
- Selecting `bayer_simple` now returns `graph_params.base_url` from the backend.
- The frontend can display and edit `base_url`.
- Re-saving a pipeline from the UI preserves the custom provider endpoint instead of falling back to DashScope.

## Issue: `llm_name` Always Loaded As Default In Frontend

### Problem
The frontend editor always showed `qwen-plus` when loading an existing pipeline, even when the YAML and runtime registry were configured with a different model such as `gemini-3-flash`.

### Root Cause
- `GraphConfigReadResponse` did not include `llm_name` from the backend.
- `toEditable()` in `frontend/src/App.tsx` initialized `llmName` to `DEFAULT_LLM_NAME`.
- `selectExisting()` then explicitly overwrote the loaded value with `DEFAULT_LLM_NAME` again.

### Fix
- Added `llm_name` to the backend `GraphConfigReadResponse`.
- Added backend logic to load `llm_name` from the pipeline registry, with YAML fallback.
- Updated frontend types to include `llm_name`.
- Updated `toEditable()` to use `config.llm_name`.
- Removed the frontend overwrite in `selectExisting()` that forced `qwen-plus`.

### Verification
- Existing pipelines now show their configured model in the editor.
- `bayer_simple` loads as `gemini-3-flash` instead of `qwen-plus`.

## Issue: Registry Did Not Auto-Discover YAML Pipelines

### Problem
Pipelines placed under `configs/pipelines/` were not automatically registered in `configs/pipeline_registry.json`. That meant new YAML configs could exist on disk but still not appear in the runtime registry until someone manually edited the registry file or created the pipeline through the frontend API.

### Fix (Install-Time Registration)
- Added `sync_pipeline_registry_from_configs()` in `lang_agent/front_api/build_server_utils.py`.
- It scans `configs/pipelines/*.yaml` and `*.yml`, loads each config, infers:
  - `pipeline_id`
  - `graph_id`
  - `llm_name`
  - `config_file`
- Existing `enabled` values are preserved if the pipeline already exists in the registry.
- Created `scripts/py_scripts/register_pipelines.py` - a standalone registration script.
- Updated `scripts/shell_scripts/install.sh` to run registration during installation.

### Result
- Running `./scripts/shell_scripts/install.sh` now auto-registers all YAML pipelines before building Docker images.
- For local development without Docker, run `python scripts/py_scripts/register_pipelines.py` once before starting the server.
- Runtime registry reads no longer modify the registry file, ensuring stability.

### Usage

**Docker-only (Cross-platform - Windows/Mac/Linux):**
```bash
# Create .env file, then:
cd docker
docker compose -f docker-compose.docker-only.yml up -d
```

**Traditional install script (macOS/Linux only):**
```bash
./scripts/shell_scripts/install.sh
```

**For local development without Docker:**
```bash
# One-time registration
python scripts/py_scripts/register_pipelines.py

# Then start the server
python lang_agent/fastapi_server/combined.py --port 8500
```

### Running the Server

```bash
# Important: Unset proxy variables when on VPN
unset HTTP_PROXY http_proxy HTTPS_PROXY https_proxy ALL_PROXY all_proxy

# Start the combined server
python lang_agent/fastapi_server/combined.py --port 8500
```

### Related Files

- `configs/pipeline_registry.json` - Pipeline registry configuration
- `configs/pipelines/bayer_simple.yaml` - Pipeline YAML configuration
- `lang_agent/config/db_config_manager.py` - Database operations
- `lang_agent/fastapi_server/front_apis.py` - API endpoints
- `frontend/src/App.tsx` - Frontend UI (see `rows` variable around line 1357)
