import { useEffect, useMemo, useState } from "react";
import {
  createPipeline,
  deleteGraphConfig,
  getGraphConfig,
  getGraphDefaultConfig,
  listAvailableGraphs,
  listGraphConfigs,
  listPipelines,
  stopPipeline,
  upsertGraphConfig,
} from "./api/frontApis";
import type {
  GraphConfigListItem,
  GraphConfigReadResponse,
  PipelineRunInfo,
} from "./types";

type EditableAgent = {
  id: string;
  isDraft: boolean;
  graphId: string;
  pipelineId: string;
  promptSetId?: string;
  toolKeys: string[];
  prompts: Record<string, string>;
  port: number;
  entryPoint: string;
  llmName: string;
};

const DEFAULT_ENTRY_POINT = "fastapi_server/server_dashscope.py";
const DEFAULT_LLM_NAME = "qwen-plus";
const DEFAULT_PORT = 8100;

function makeAgentKey(pipelineId: string, promptSetId: string): string {
  return `${pipelineId}::${promptSetId}`;
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

function toEditable(
  config: GraphConfigReadResponse,
  draft: boolean
): EditableAgent {
  return {
    id: draft
      ? `draft-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
      : makeAgentKey(config.pipeline_id, config.prompt_set_id),
    isDraft: draft,
    graphId: config.graph_id || config.pipeline_id,
    pipelineId: config.pipeline_id,
    promptSetId: config.prompt_set_id,
    toolKeys: config.tool_keys || [],
    prompts: config.prompt_dict || {},
    port: DEFAULT_PORT,
    entryPoint: DEFAULT_ENTRY_POINT,
    llmName: DEFAULT_LLM_NAME,
  };
}

export default function App() {
  const [graphs, setGraphs] = useState<string[]>([]);
  const [configItems, setConfigItems] = useState<GraphConfigListItem[]>([]);
  const [running, setRunning] = useState<PipelineRunInfo[]>([]);
  const [draftAgents, setDraftAgents] = useState<EditableAgent[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [editor, setEditor] = useState<EditableAgent | null>(null);
  const [statusMessage, setStatusMessage] = useState<string>("");
  const [busy, setBusy] = useState(false);

  const configKeySet = useMemo(
    () => new Set(configItems.map((x) => makeAgentKey(x.pipeline_id, x.prompt_set_id))),
    [configItems]
  );

  const selectedRuns = useMemo(() => {
    if (!editor?.pipelineId) {
      return [];
    }
    return running.filter((run) => {
      if (run.pipeline_id !== editor.pipelineId) {
        return false;
      }
      if (!editor.promptSetId) {
        return true;
      }
      return run.prompt_set_id === editor.promptSetId;
    });
  }, [editor, running]);

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

  async function selectExisting(item: GraphConfigListItem): Promise<void> {
    const id = makeAgentKey(item.pipeline_id, item.prompt_set_id);
    setSelectedId(id);
    setBusy(true);
    setStatusMessage("Loading agent details...");
    try {
      const detail = await getGraphConfig(item.pipeline_id, item.prompt_set_id);
      const editable = toEditable(detail, false);
      editable.id = id;
      editable.port = editor?.pipelineId === editable.pipelineId ? editor.port : DEFAULT_PORT;
      editable.entryPoint =
        editor?.pipelineId === editable.pipelineId ? editor.entryPoint : DEFAULT_ENTRY_POINT;
      editable.llmName = editor?.pipelineId === editable.pipelineId ? editor.llmName : DEFAULT_LLM_NAME;
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
      const defaults = await getGraphDefaultConfig(graphId);
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
      const defaults = await getGraphDefaultConfig(graphId);
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
      const upsertResp = await upsertGraphConfig({
        graph_id: editor.graphId,
        pipeline_id: editor.pipelineId.trim(),
        prompt_set_id: editor.promptSetId,
        tool_keys: editor.toolKeys,
        prompt_dict: editor.prompts,
      });

      await refreshConfigs();
      const detail = await getGraphConfig(upsertResp.pipeline_id, upsertResp.prompt_set_id);
      const saved = toEditable(detail, false);
      saved.id = makeAgentKey(upsertResp.pipeline_id, upsertResp.prompt_set_id);
      saved.port = editor.port;
      saved.entryPoint = editor.entryPoint;
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
    if (!Number.isInteger(editor.port) || editor.port <= 0) {
      setStatusMessage("port must be a positive integer.");
      return;
    }

    setBusy(true);
    setStatusMessage("Starting agent...");
    try {
      const resp = await createPipeline({
        graph_id: editor.graphId,
        pipeline_id: editor.pipelineId.trim(),
        prompt_set_id: editor.promptSetId,
        tool_keys: editor.toolKeys,
        port: editor.port,
        entry_point: editor.entryPoint,
        llm_name: editor.llmName,
      });
      await refreshRunning();
      setStatusMessage(`Agent started. URL: ${resp.url}`);
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
      await stopPipeline(target.run_id);
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
      isDraft: true,
    })),
    ...configItems.map((item) => ({
      id: makeAgentKey(item.pipeline_id, item.prompt_set_id),
      label: item.pipeline_id,
      graphId: item.graph_id || item.pipeline_id,
      isDraft: false,
    })),
  ];

  return (
    <div className="app">
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
                const item = configItems.find(
                  (x) => makeAgentKey(x.pipeline_id, x.prompt_set_id) === row.id
                );
                if (item) {
                  selectExisting(item);
                }
              }}
            >
              <span>{row.label}</span>
              <small>{row.graphId}</small>
            </button>
          ))}
          {rows.length === 0 ? <p className="empty">No agents configured yet.</p> : null}
        </div>
      </aside>

      <main className="content">
        <header className="content-header">
          <h1>Agent Configuration</h1>
          <div className="header-actions">
            <button onClick={saveConfig} disabled={busy || !editor}>
              Save
            </button>
            <button onClick={runSelected} disabled={busy || !editor}>
              Run
            </button>
            <button onClick={stopSelected} disabled={busy || !editor}>
              Stop
            </button>
            <button onClick={deleteSelected} disabled={busy || !editor}>
              Delete
            </button>
          </div>
        </header>

        {statusMessage ? <p className="status">{statusMessage}</p> : null}

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
              prompt_set_id
              <input value={editor.promptSetId || "(assigned on save)"} readOnly />
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
              port
              <input
                type="number"
                min={1}
                value={editor.port}
                onChange={(e) => updateEditor("port", Number(e.target.value))}
                disabled={busy}
              />
            </label>

            <label>
              entry_point
              <input
                value={editor.entryPoint}
                onChange={(e) => updateEditor("entryPoint", e.target.value)}
                disabled={busy}
              />
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
              <h3>Running Instances</h3>
              {selectedRuns.length === 0 ? (
                <p className="empty">No active runs for this agent.</p>
              ) : (
                selectedRuns.map((run) => (
                  <div key={run.run_id} className="run-card">
                    <div>
                      <strong>run_id:</strong> {run.run_id}
                    </div>
                    <div>
                      <strong>pid:</strong> {run.pid}
                    </div>
                    <div>
                      <strong>url:</strong>{" "}
                      <a href={run.url} target="_blank" rel="noreferrer">
                        {run.url}
                      </a>
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

