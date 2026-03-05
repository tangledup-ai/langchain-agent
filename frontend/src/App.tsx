import { useEffect, useMemo, useState } from "react";
import {
  createPipeline,
  deleteGraphConfig,
  getGraphConfig,
  getGraphDefaultConfig,
  getPipelineDefaultConfig,
  getMcpToolConfig,
  listAvailableGraphs,
  listGraphConfigs,
  listPipelines,
  stopPipeline,
  updateMcpToolConfig,
  upsertGraphConfig,
} from "./api/frontApis";
import { chooseActiveConfigItem, chooseDisplayItemsByPipeline } from "./activeConfigSelection";
import type {
  GraphConfigListItem,
  GraphConfigReadResponse,
  PipelineSpec,
} from "./types";

type EditableAgent = {
  id: string;
  isDraft: boolean;
  graphId: string;
  pipelineId: string;
  promptSetId?: string;
  toolKeys: string[];
  prompts: Record<string, string>;
  apiKey: string;
  llmName: string;
};

type ActiveTab = "agents" | "mcp";

const DEFAULT_LLM_NAME = "qwen-plus";
const DEFAULT_API_KEY = "";
const GRAPH_ARCH_IMAGE_MODULES = import.meta.glob(
  "../assets/images/graph_arch/*.{png,jpg,jpeg,webp,gif}",
  { eager: true, import: "default" }
) as Record<string, string>;
const FALLBACK_PROMPTS_BY_GRAPH: Record<string, Record<string, string>> = {
  routing: {
    route_prompt: "",
    chat_prompt: "",
    tool_prompt: "",
  },
  react: {
    sys_prompt: "",
  },
};

function makeAgentKey(pipelineId: string): string {
  return `pipeline::${pipelineId}`;
}

function parseToolCsv(value: string): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  for (const token of value.split(",")) {
    const trimmed = token.trim();
    if (!trimmed || seen.has(trimmed)) {
      continue;
    }
    seen.add(trimmed);
    out.push(trimmed);
  }
  return out;
}

function maskSecretPreview(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) {
    return "";
  }
  if (trimmed.length <= 10) {
    return trimmed;
  }
  return `${trimmed.slice(0, 5)}...${trimmed.slice(-5)}`;
}

function getGraphArchImage(graphId: string): string | null {
  const normalizedGraphId = graphId.trim().toLowerCase();
  for (const [path, source] of Object.entries(GRAPH_ARCH_IMAGE_MODULES)) {
    const fileName = path.split("/").pop() || "";
    const baseName = fileName.split(".")[0]?.toLowerCase() || "";
    if (baseName === normalizedGraphId) {
      return source;
    }
  }
  return null;
}

function toEditable(
  config: GraphConfigReadResponse,
  draft: boolean
): EditableAgent {
  return {
    id: draft
      ? `draft-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
      : makeAgentKey(config.pipeline_id),
    isDraft: draft,
    graphId: config.graph_id || config.pipeline_id,
    pipelineId: config.pipeline_id,
    promptSetId: config.prompt_set_id,
    toolKeys: config.tool_keys || [],
    prompts: config.prompt_dict || {},
    apiKey: config.api_key || DEFAULT_API_KEY,
    llmName: DEFAULT_LLM_NAME,
  };
}

export default function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("agents");
  const [graphs, setGraphs] = useState<string[]>([]);
  const [configItems, setConfigItems] = useState<GraphConfigListItem[]>([]);
  const [running, setRunning] = useState<PipelineSpec[]>([]);
  const [draftAgents, setDraftAgents] = useState<EditableAgent[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditableAgent | null>(null);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [mcpConfigPath, setMcpConfigPath] = useState<string>("");
  const [mcpConfigRaw, setMcpConfigRaw] = useState<string>("");
  const [mcpToolKeys, setMcpToolKeys] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  const configKeySet = useMemo(
    () => new Set(configItems.map((x) => makeAgentKey(x.pipeline_id))),
    [configItems]
  );
  const visibleConfigItems = useMemo(
    () =>
      configItems.filter((item) => {
        // Hide the pre-seeded template entries (pipeline_id === graph_id, name "default")
        if (
          item.name.toLowerCase() === "default" &&
          item.graph_id &&
          item.pipeline_id === item.graph_id
        ) {
          return false;
        }
        return true;
      }),
    [configItems]
  );
  const displayConfigItems = useMemo(
    () => chooseDisplayItemsByPipeline(visibleConfigItems),
    [visibleConfigItems]
  );
  const runningPipelineIdSet = useMemo(() => {
    const ids = new Set<string>();
    for (const run of running) {
      if (run.enabled) {
        ids.add(run.pipeline_id);
      }
    }
    return ids;
  }, [running]);

  const selectedRuns = useMemo(() => {
    const pipelineId = editor?.pipelineId.trim();
    if (!pipelineId) {
      return [];
    }
    return running.filter((run) => {
      if (run.pipeline_id !== pipelineId) {
        return false;
      }
      return run.enabled;
    });
  }, [editor, running]);
  const isEditorRunning = selectedRuns.length > 0;

  async function refreshConfigs(): Promise<void> {
    const resp = await listGraphConfigs();
    setConfigItems(resp.items);
  }

  async function refreshRunning(): Promise<void> {
    const resp = await listPipelines();
    setRunning(resp.items);
  }

  async function bootstrap(): Promise<void> {
    setBusy(true);
    setStatusMessage("Loading graphs and agent configs...");
    try {
      const [graphResp, configResp, runsResp] = await Promise.all([
        listAvailableGraphs(),
        listGraphConfigs(),
        listPipelines(),
      ]);
      setGraphs(graphResp.available_graphs || []);
      setConfigItems(configResp.items || []);
      setRunning(runsResp.items || []);
      setStatusMessage("");
    } catch (error) {
      setStatusMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    bootstrap();
    const timer = setInterval(() => {
      refreshRunning().catch(() => undefined);
    }, 5000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (selectedId && !selectedId.startsWith("draft-") && !configKeySet.has(selectedId)) {
      setSelectedId(null);
      setEditor(null);
    }
  }, [selectedId, configKeySet]);

  useEffect(() => {
    if (activeTab !== "mcp") {
      return;
    }
    if (mcpConfigRaw) {
      return;
    }
    reloadMcpConfig().catch(() => undefined);
  }, [activeTab]);

  async function selectExisting(item: GraphConfigListItem): Promise<void> {
    const id = makeAgentKey(item.pipeline_id);
    setSelectedId(id);
    setBusy(true);
    setStatusMessage("Loading agent details...");
    try {
      let detail: GraphConfigReadResponse;
      try {
        detail = await getPipelineDefaultConfig(item.pipeline_id);
      } catch {
        const latest = await listGraphConfigs({ pipeline_id: item.pipeline_id });
        const selected = chooseActiveConfigItem(latest.items || [], item.pipeline_id);
        if (!selected) {
          throw new Error(`No prompt set found for pipeline '${item.pipeline_id}'`);
        }
        detail = await getGraphConfig(item.pipeline_id, selected.prompt_set_id);
      }
      const editable = toEditable(detail, false);
      editable.id = id;
      editable.llmName = editor?.pipelineId === editable.pipelineId ? editor.llmName : DEFAULT_LLM_NAME;
      // apiKey is loaded from backend (persisted in DB) — don't override with default
      setEditor(editable);
      setStatusMessage("");
    } catch (error) {
      setStatusMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function addDraftAgent(): Promise<void> {
    const graphId = graphs[0] || "routing";
    setBusy(true);
    setStatusMessage("Preparing new agent draft...");
    try {
      const defaults = await loadPromptDefaults(graphId);
      const editable = toEditable(defaults, true);
      editable.graphId = graphId;
      editable.pipelineId = "";
      editable.promptSetId = undefined;
      editable.id = `draft-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`;
      setDraftAgents((prev) => [editable, ...prev]);
      setEditor(editable);
      setSelectedId(editable.id);
      setStatusMessage("");
    } catch (error) {
      setStatusMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function changeGraph(graphId: string): Promise<void> {
    if (!editor) {
      return;
    }
    setBusy(true);
    setStatusMessage("Loading default prompts for selected graph...");
    try {
      const defaults = await loadPromptDefaults(graphId);
      setEditorAndSyncDraft((prev) => ({
        ...prev,
        graphId,
        prompts: { ...defaults.prompt_dict },
        toolKeys: defaults.tool_keys || [],
      }));
      setStatusMessage("");
    } catch (error) {
      setStatusMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function setEditorAndSyncDraft(
    updater: (prev: EditableAgent) => EditableAgent
  ): void {
    setEditor((prev) => {
      if (!prev) {
        return prev;
      }
      const next = updater(prev);
      if (next.isDraft) {
        setDraftAgents((drafts) => drafts.map((draft) => (draft.id === next.id ? next : draft)));
      }
      return next;
    });
  }

  function updateEditor<K extends keyof EditableAgent>(key: K, value: EditableAgent[K]): void {
    setEditorAndSyncDraft((prev) => ({ ...prev, [key]: value }));
  }

  function updatePrompt(key: string, value: string): void {
    setEditorAndSyncDraft((prev) => ({
      ...prev,
      prompts: {
        ...prev.prompts,
        [key]: value,
      },
    }));
  }

  async function loadPromptDefaults(graphId: string): Promise<GraphConfigReadResponse> {
    try {
      return await getGraphDefaultConfig(graphId);
    } catch {
      const fallbackPrompts = FALLBACK_PROMPTS_BY_GRAPH[graphId] || { sys_prompt: "" };
      setStatusMessage(
        `No backend default config found for '${graphId}'. Using built-in fallback fields.`
      );
      return {
        graph_id: graphId,
        pipeline_id: graphId,
        prompt_set_id: "default",
        tool_keys: [],
        prompt_dict: fallbackPrompts,
        api_key: "",
      };
    }
  }

  async function reloadMcpConfig(): Promise<void> {
    setBusy(true);
    setStatusMessage("Loading MCP config...");
    try {
      const resp = await getMcpToolConfig();
      setMcpConfigPath(resp.path || "");
      setMcpConfigRaw(resp.raw_content || "");
      setMcpToolKeys(resp.tool_keys || []);
      setStatusMessage("MCP config loaded.");
    } catch (error) {
      setStatusMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveMcpConfig(): Promise<void> {
    setBusy(true);
    setStatusMessage("Saving MCP config...");
    try {
      const resp = await updateMcpToolConfig({ raw_content: mcpConfigRaw });
      setMcpConfigPath(resp.path || "");
      setMcpToolKeys(resp.tool_keys || []);
      setStatusMessage("MCP config saved.");
    } catch (error) {
      setStatusMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveConfig(): Promise<void> {
    if (!editor) {
      return;
    }
    const promptEntries = Object.entries(editor.prompts);
    if (!editor.pipelineId.trim()) {
      setStatusMessage("pipeline_id is required.");
      return;
    }
    if (!editor.graphId.trim()) {
      setStatusMessage("graph_id is required.");
      return;
    }
    if (promptEntries.length === 0) {
      setStatusMessage("At least one prompt field is required.");
      return;
    }
    if (promptEntries.some(([_, content]) => !content.trim())) {
      setStatusMessage("All prompt fields must be filled.");
      return;
    }

    setBusy(true);
    setStatusMessage("Saving agent config...");
    try {
      let targetPromptSetId = editor.promptSetId;
      if (!targetPromptSetId) {
        try {
          const active = await getPipelineDefaultConfig(editor.pipelineId.trim());
          targetPromptSetId = active.prompt_set_id;
        } catch {
          throw new Error(
            "No active prompt set for this pipeline. Create/activate one via backend first."
          );
        }
      }
      const upsertResp = await upsertGraphConfig({
        graph_id: editor.graphId,
        pipeline_id: editor.pipelineId.trim(),
        prompt_set_id: targetPromptSetId,
        tool_keys: editor.toolKeys,
        prompt_dict: editor.prompts,
        api_key: editor.apiKey.trim(),
      });

      await refreshConfigs();
      const detail = await getPipelineDefaultConfig(upsertResp.pipeline_id);
      const saved = toEditable(detail, false);
      saved.id = makeAgentKey(upsertResp.pipeline_id);
      // apiKey is loaded from backend (persisted in DB) — don't override
      saved.llmName = editor.llmName;
      setEditor(saved);
      setSelectedId(saved.id);
      setDraftAgents((prev) => prev.filter((d) => d.id !== editor.id));
      setStatusMessage("Agent config saved.");
    } catch (error) {
      setStatusMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function deleteSelected(): Promise<void> {
    if (!editor) {
      return;
    }
    if (editor.isDraft || !editor.promptSetId) {
      setDraftAgents((prev) => prev.filter((d) => d.id !== editor.id));
      setEditor(null);
      setSelectedId(null);
      setStatusMessage("Draft deleted.");
      return;
    }

    setBusy(true);
    setStatusMessage("Deleting agent config...");
    try {
      await deleteGraphConfig(editor.pipelineId, editor.promptSetId);
      await refreshConfigs();
      setEditor(null);
      setSelectedId(null);
      setStatusMessage("Agent deleted.");
    } catch (error) {
      setStatusMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function runSelected(): Promise<void> {
    if (!editor) {
      return;
    }
    if (!editor.promptSetId) {
      setStatusMessage("Save the agent first before running.");
      return;
    }
    if (!editor.pipelineId.trim()) {
      setStatusMessage("pipeline_id is required before run.");
      return;
    }
    if (!editor.apiKey.trim()) {
      setStatusMessage("api_key is required before run.");
      return;
    }

    setBusy(true);
    setStatusMessage("Registering agent runtime...");
    try {
      const resp = await createPipeline({
        graph_id: editor.graphId,
        pipeline_id: editor.pipelineId.trim(),
        prompt_set_id: editor.promptSetId,
        tool_keys: editor.toolKeys,
        api_key: editor.apiKey.trim(),
        llm_name: editor.llmName,
        enabled: true,
      });
      await refreshRunning();
      if (resp.reload_required) {
        setStatusMessage(
          `Agent registered, runtime reload pending. config_file=${resp.config_file}`
        );
      } else {
        setStatusMessage(
          `Agent registered and runtime auto-reload is active. Ready to chat via app_id=${resp.pipeline_id}.`
        );
      }
    } catch (error) {
      setStatusMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function stopSelected(): Promise<void> {
    if (!editor) {
      return;
    }
    const target = selectedRuns[0];
    if (!target) {
      setStatusMessage("No running instance found for this agent.");
      return;
    }

    setBusy(true);
    setStatusMessage("Stopping agent...");
    try {
      await stopPipeline(target.pipeline_id);
      await refreshRunning();
      setStatusMessage("Agent stopped.");
    } catch (error) {
      setStatusMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const rows = [
    ...draftAgents.map((d) => ({
      id: d.id,
      label: d.pipelineId || "(new agent)",
      graphId: d.graphId,
      isRunning: d.pipelineId ? runningPipelineIdSet.has(d.pipelineId.trim()) : false,
      isDraft: true,
    })),
    ...displayConfigItems.map((item) => ({
      id: makeAgentKey(item.pipeline_id),
      label: item.pipeline_id,
      graphId: item.graph_id || item.pipeline_id,
      isRunning: runningPipelineIdSet.has(item.pipeline_id),
      isDraft: false,
    })),
  ];
  const graphArchImage = editor ? getGraphArchImage(editor.graphId) : null;

  const showSidebar = activeTab === "agents";

  return (
    <div className={`app ${showSidebar ? "" : "full-width"}`}>
      {showSidebar ? (
        <aside className="sidebar">
          <div className="sidebar-header">
            <h2>Agents</h2>
            <button onClick={addDraftAgent} disabled={busy}>
              + New
            </button>
          </div>
          <div className="agent-list">
            {rows.map((row) => (
              <button
                key={row.id}
                className={`agent-item ${selectedId === row.id ? "selected" : ""}`}
                onClick={() => {
                  if (row.isDraft) {
                    const selectedDraft = draftAgents.find((d) => d.id === row.id) || null;
                    setSelectedId(row.id);
                    setEditor(selectedDraft);
                    return;
                  }
                  const item = displayConfigItems.find((x) => makeAgentKey(x.pipeline_id) === row.id);
                  if (item) {
                    selectExisting(item);
                  }
                }}
              >
                <span className="agent-item-title">
                  <span>{row.label}</span>
                  <span className={`agent-status-pill ${row.isRunning ? "running" : "stopped"}`}>
                    {row.isRunning ? "Running" : "Stopped"}
                  </span>
                </span>
                <small>{row.graphId}</small>
              </button>
            ))}
            {rows.length === 0 ? <p className="empty">No agents configured yet.</p> : null}
          </div>
        </aside>
      ) : null}

      <main className="content">
        <header className="content-header">
          <h1>Agent Manager</h1>
          <div className="tabs">
            <button
              type="button"
              className={`tab-button ${activeTab === "agents" ? "active" : ""}`}
              onClick={() => setActiveTab("agents")}
              disabled={busy}
            >
              Agents
            </button>
            <button
              type="button"
              className={`tab-button ${activeTab === "mcp" ? "active" : ""}`}
              onClick={() => setActiveTab("mcp")}
              disabled={busy}
            >
              MCP Config
            </button>
          </div>
        </header>

        {statusMessage ? <p className="status">{statusMessage}</p> : null}
        {activeTab === "agents" ? (
          <div className="tab-pane">
            <div className="header-actions">
              <button onClick={saveConfig} disabled={busy || !editor}>
                Save
              </button>
              <button onClick={runSelected} disabled={busy || !editor || isEditorRunning}>
                Run
              </button>
              <button onClick={stopSelected} disabled={busy || !editor || !isEditorRunning}>
                Stop
              </button>
              <button onClick={deleteSelected} disabled={busy || !editor}>
                Delete
              </button>
            </div>

            {!editor ? (
              <div className="empty-panel">
                <p>Select an agent from the left or create a new one.</p>
              </div>
            ) : (
              <section className="form-grid">
                <label>
                  Agent Type (graph_id)
                  <select
                    value={editor.graphId}
                    onChange={(e) => changeGraph(e.target.value)}
                    disabled={busy}
                  >
                    {graphs.map((graph) => (
                      <option key={graph} value={graph}>
                        {graph}
                      </option>
                    ))}
                  </select>
                </label>

                {graphArchImage && (
                  <div className="graph-arch-section">
                    <h3>Graph Architecture</h3>
                    <div className="graph-arch-image-container">
                      <img
                        src={graphArchImage}
                        alt={`${editor.graphId} architecture diagram`}
                        className="graph-arch-image"
                      />
                    </div>
                  </div>
                )}

                <label>
                  pipeline_id
                  <input
                    value={editor.pipelineId}
                    onChange={(e) => updateEditor("pipelineId", e.target.value)}
                    placeholder="example: routing-agent-1"
                    disabled={busy}
                  />
                </label>

                <label>
                  tool_keys (comma separated)
                  <input
                    value={editor.toolKeys.join(", ")}
                    onChange={(e) => updateEditor("toolKeys", parseToolCsv(e.target.value))}
                    placeholder="tool_a, tool_b"
                    disabled={busy}
                  />
                </label>

                <label>
                  api_key
                  <input
                    type="password"
                    value={editor.apiKey}
                    onChange={(e) => updateEditor("apiKey", e.target.value)}
                    placeholder="Enter provider API key"
                    disabled={busy}
                  />
                  {editor.apiKey ? (
                    <small className="empty">Preview: {maskSecretPreview(editor.apiKey)}</small>
                  ) : null}
                </label>

                <label>
                  llm_name
                  <input
                    value={editor.llmName}
                    onChange={(e) => updateEditor("llmName", e.target.value)}
                    disabled={busy}
                  />
                </label>

                <div className="prompt-section">
                  <h3>Prompts</h3>
                  {Object.keys(editor.prompts).length === 0 ? (
                    <p className="empty">No prompt keys returned from backend.</p>
                  ) : (
                    Object.entries(editor.prompts).map(([key, value]) => (
                      <label key={key}>
                        {key}
                        <textarea
                          value={value}
                          onChange={(e) => updatePrompt(key, e.target.value)}
                          rows={4}
                          disabled={busy}
                        />
                      </label>
                    ))
                  )}
                </div>

                <div className="run-info">
                  <div className="run-info-header">
                    <h3>Running Instances</h3>
                    <span className={`runtime-badge ${isEditorRunning ? "running" : "stopped"}`}>
                      Runtime: {isEditorRunning ? "Running" : "Stopped"}
                    </span>
                  </div>
                  {selectedRuns.length === 0 ? (
                    <p className="empty">No active runs for this agent.</p>
                  ) : (
                    selectedRuns.map((run) => (
                      <div key={run.pipeline_id} className="run-card">
                        <div>
                          <strong>pipeline_id:</strong> {run.pipeline_id}
                        </div>
                        <div>
                          <strong>graph_id:</strong> {run.graph_id}
                        </div>
                        <div>
                          <strong>model:</strong> {run.llm_name}
                        </div>
                        <div>
                          <strong>enabled:</strong> {String(run.enabled)}
                        </div>
                        <div>
                          <strong>config_file:</strong> {run.config_file}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </section>
            )}
          </div>
        ) : (
          <section className="mcp-config-section tab-pane">
            <div className="mcp-config-header">
              <h3>Edit MCP Tool Options</h3>
              <div className="header-actions">
                <button type="button" onClick={reloadMcpConfig} disabled={busy}>
                  Reload
                </button>
                <button type="button" onClick={saveMcpConfig} disabled={busy}>
                  Save
                </button>
              </div>
            </div>
            <p className="empty">
              This tab edits <code>configs/mcp_config.json</code> directly (comments supported).
            </p>
            {mcpConfigPath ? (
              <p className="empty">
                File: <code>{mcpConfigPath}</code>
              </p>
            ) : null}
            <p className="empty">
              Tool options detected: {mcpToolKeys.length ? mcpToolKeys.join(", ") : "(none)"}
            </p>
            <textarea
              className="mcp-config-editor"
              value={mcpConfigRaw}
              onChange={(e) => setMcpConfigRaw(e.target.value)}
              rows={18}
              spellCheck={false}
              disabled={busy}
            />
          </section>
        )}
      </main>
    </div>
  );
}

