import { useEffect, useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  createPipeline,
  deleteGraphConfig,
  getGraphConfig,
  getPipelineConversationMessages,
  getGraphDefaultConfig,
  getPipelineDefaultConfig,
  getMcpToolConfig,
  listPipelineConversations,
  listMcpAvailableTools,
  listAvailableGraphs,
  listGraphConfigs,
  listPipelines,
  stopPipeline,
  updateMcpToolConfig,
  upsertGraphConfig,
} from "./api/frontApis";
import { chooseActiveConfigItem, chooseDisplayItemsByPipeline } from "./activeConfigSelection";
import type {
  ConversationListItem,
  ConversationMessageItem,
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

type ActiveTab = "agents" | "discussions" | "mcp";
type McpTransport = "streamable_http" | "sse" | "stdio";
type McpEntry = {
  id: string;
  name: string;
  transport: McpTransport;
  url: string;
  command: string;
  args: string;
  authorization: string;
  extraFields: Record<string, unknown>;
};

const DEFAULT_LLM_NAME = "qwen-plus";
const DEFAULT_API_KEY = "";
const MCP_TRANSPORT_OPTIONS: McpTransport[] = ["streamable_http", "sse", "stdio"];
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

function parseArgCsv(value: string): string[] {
  const out: string[] = [];
  for (const token of value.split(",")) {
    const trimmed = token.trim();
    if (!trimmed) {
      continue;
    }
    out.push(trimmed);
  }
  return out;
}

function isMcpTransport(value: unknown): value is McpTransport {
  return (
    value === "streamable_http" ||
    value === "sse" ||
    value === "stdio"
  );
}

function stripJsonComments(value: string): string {
  let out = "";
  let i = 0;
  let inString = false;
  let escaped = false;

  while (i < value.length) {
    const current = value[i];
    const next = value[i + 1];

    if (inString) {
      out += current;
      if (escaped) {
        escaped = false;
      } else if (current === "\\") {
        escaped = true;
      } else if (current === "\"") {
        inString = false;
      }
      i += 1;
      continue;
    }

    if (current === "\"") {
      inString = true;
      out += current;
      i += 1;
      continue;
    }

    if (current === "/" && next === "/") {
      i += 2;
      while (i < value.length && value[i] !== "\n") {
        i += 1;
      }
      continue;
    }

    if (current === "/" && next === "*") {
      i += 2;
      while (i < value.length && !(value[i] === "*" && value[i + 1] === "/")) {
        i += 1;
      }
      i += 2;
      continue;
    }

    out += current;
    i += 1;
  }

  return out;
}

function stripTrailingCommas(value: string): string {
  let out = "";
  let i = 0;
  let inString = false;
  let escaped = false;

  while (i < value.length) {
    const current = value[i];

    if (inString) {
      out += current;
      if (escaped) {
        escaped = false;
      } else if (current === "\\") {
        escaped = true;
      } else if (current === "\"") {
        inString = false;
      }
      i += 1;
      continue;
    }

    if (current === "\"") {
      inString = true;
      out += current;
      i += 1;
      continue;
    }

    if (current === ",") {
      let j = i + 1;
      while (j < value.length && /\s/.test(value[j])) {
        j += 1;
      }
      if (value[j] === "}" || value[j] === "]") {
        i += 1;
        continue;
      }
    }

    out += current;
    i += 1;
  }

  return out;
}

function createEmptyMcpEntry(): McpEntry {
  return {
    id: `mcp-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    name: "",
    transport: "streamable_http",
    url: "",
    command: "",
    args: "",
    authorization: "",
    extraFields: {},
  };
}

function parseMcpEntries(rawContent: string): McpEntry[] {
  const normalized = stripTrailingCommas(stripJsonComments(rawContent)).trim();
  if (!normalized) {
    return [];
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(normalized);
  } catch (error) {
    throw new Error(`MCP config parse error: ${(error as Error).message}`);
  }

  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error("MCP config must be a JSON object at top level.");
  }

  const configObj = parsed as Record<string, unknown>;
  return Object.entries(configObj).map(([name, server]) => {
    const serverObj =
      server && typeof server === "object" && !Array.isArray(server)
        ? ({ ...(server as Record<string, unknown>) } as Record<string, unknown>)
        : {};
    const rawTransport = serverObj.transport;
    const transport: McpTransport = isMcpTransport(rawTransport)
      ? rawTransport
      : "streamable_http";
    const url = typeof serverObj.url === "string" ? serverObj.url : "";
    const command = typeof serverObj.command === "string" ? serverObj.command : "";
    const args =
      Array.isArray(serverObj.args) && serverObj.args.every((x) => typeof x === "string")
        ? (serverObj.args as string[]).join(", ")
        : typeof serverObj.args === "string"
          ? serverObj.args
          : "";
    const headers =
      serverObj.headers && typeof serverObj.headers === "object" && !Array.isArray(serverObj.headers)
        ? ({ ...(serverObj.headers as Record<string, unknown>) } as Record<string, unknown>)
        : null;
    const authorization = headers && typeof headers.Authorization === "string" ? headers.Authorization : "";
    if (headers) {
      delete headers.Authorization;
      if (Object.keys(headers).length > 0) {
        serverObj.headers = headers;
      } else {
        delete serverObj.headers;
      }
    }
    delete serverObj.transport;
    delete serverObj.url;
    delete serverObj.command;
    delete serverObj.args;
    return {
      id: `mcp-${name}-${Math.random().toString(36).slice(2, 6)}`,
      name,
      transport,
      url,
      command,
      args,
      authorization,
      extraFields: serverObj,
    };
  });
}

function buildMcpRawContent(entries: McpEntry[]): string {
  const root: Record<string, Record<string, unknown>> = {};
  for (const entry of entries) {
    const key = entry.name.trim();
    if (!key) {
      continue;
    }
    const payload: Record<string, unknown> = {
      ...entry.extraFields,
      transport: entry.transport,
    };
    const payloadHeaders =
      payload.headers && typeof payload.headers === "object" && !Array.isArray(payload.headers)
        ? ({ ...(payload.headers as Record<string, unknown>) } as Record<string, unknown>)
        : null;
    if (payloadHeaders) {
      delete payloadHeaders.Authorization;
      if (Object.keys(payloadHeaders).length > 0) {
        payload.headers = payloadHeaders;
      } else {
        delete payload.headers;
      }
    }
    if (entry.transport === "stdio") {
      payload.command = entry.command.trim();
      const args = parseArgCsv(entry.args);
      if (args.length > 0) {
        payload.args = args;
      } else {
        delete payload.args;
      }
      delete payload.url;
    } else {
      payload.url = entry.url.trim();
      if (entry.authorization.trim()) {
        payload.headers = {
          ...(payload.headers &&
          typeof payload.headers === "object" &&
          !Array.isArray(payload.headers)
            ? (payload.headers as Record<string, unknown>)
            : {}),
          Authorization: entry.authorization.trim(),
        };
      }
      delete payload.command;
      delete payload.args;
    }
    root[key] = payload;
  }
  return `${JSON.stringify(root, null, 2)}\n`;
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

function sanitizeConfigPath(path: string): string {
  if (!path.trim()) {
    return path;
  }
  const normalized = path.replace(/\\/g, "/");
  const marker = "/configs/";
  const markerIndex = normalized.lastIndexOf(marker);
  if (markerIndex >= 0) {
    return normalized.slice(markerIndex + 1);
  }
  const parts = normalized.split("/").filter(Boolean);
  if (parts.length >= 2) {
    return parts.slice(-2).join("/");
  }
  return normalized;
}

function formatDateTime(value?: string | null): string {
  if (!value) {
    return "";
  }
  const timestamp = Date.parse(value);
  if (Number.isNaN(timestamp)) {
    return value;
  }
  return new Date(timestamp).toLocaleString();
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
  const [mcpEntries, setMcpEntries] = useState<McpEntry[]>([]);
  const [mcpToolKeys, setMcpToolKeys] = useState<string[]>([]);
  const [mcpToolsByServer, setMcpToolsByServer] = useState<Record<string, string[]>>({});
  const [mcpErrorsByServer, setMcpErrorsByServer] = useState<Record<string, string>>({});
  const [discussionConversations, setDiscussionConversations] = useState<ConversationListItem[]>([]);
  const [selectedConversationId, setSelectedConversationId] = useState<string | null>(null);
  const [discussionMessages, setDiscussionMessages] = useState<ConversationMessageItem[]>([]);
  const [discussionLoading, setDiscussionLoading] = useState(false);
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
  const selectedPipelineId = editor?.pipelineId.trim() || "";
  const canViewDiscussions = !!selectedPipelineId && !editor?.isDraft;

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
    if (mcpEntries.length > 0) {
      return;
    }
    reloadMcpConfig().catch(() => undefined);
  }, [activeTab, mcpEntries.length]);

  async function loadPipelineDiscussions(
    pipelineId: string,
    opts: { keepSelection?: boolean } = {}
  ): Promise<void> {
    if (!pipelineId) {
      setDiscussionConversations([]);
      setSelectedConversationId(null);
      setDiscussionMessages([]);
      return;
    }
    setDiscussionLoading(true);
    try {
      const conversations = await listPipelineConversations(pipelineId);
      setDiscussionConversations(conversations);
      const nextSelected = opts.keepSelection
        ? conversations.find((item) => item.conversation_id === selectedConversationId)
          ? selectedConversationId
          : null
        : null;
      const initialConversationId = nextSelected || conversations[0]?.conversation_id || null;
      setSelectedConversationId(initialConversationId);

      if (initialConversationId) {
        const messages = await getPipelineConversationMessages(
          pipelineId,
          initialConversationId
        );
        setDiscussionMessages(messages);
      } else {
        setDiscussionMessages([]);
      }
    } catch (error) {
      setStatusMessage((error as Error).message);
      setDiscussionConversations([]);
      setSelectedConversationId(null);
      setDiscussionMessages([]);
    } finally {
      setDiscussionLoading(false);
    }
  }

  async function selectDiscussionConversation(conversationId: string): Promise<void> {
    if (!selectedPipelineId) {
      return;
    }
    setSelectedConversationId(conversationId);
    setDiscussionLoading(true);
    try {
      const messages = await getPipelineConversationMessages(
        selectedPipelineId,
        conversationId
      );
      setDiscussionMessages(messages);
    } catch (error) {
      setStatusMessage((error as Error).message);
      setDiscussionMessages([]);
    } finally {
      setDiscussionLoading(false);
    }
  }

  useEffect(() => {
    if (activeTab !== "discussions") {
      return;
    }
    if (!canViewDiscussions) {
      setDiscussionConversations([]);
      setSelectedConversationId(null);
      setDiscussionMessages([]);
      return;
    }
    loadPipelineDiscussions(selectedPipelineId, { keepSelection: true }).catch(
      () => undefined
    );
  }, [activeTab, canViewDiscussions, selectedPipelineId]);

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
    const targetEditorId = editor.id;
    setBusy(true);
    setStatusMessage("Loading default prompts for selected graph...");
    try {
      const defaults = await loadPromptDefaults(graphId);
      setEditor((prev) => {
        if (!prev || prev.id !== targetEditorId) {
          // Selection changed while defaults were loading; do not mutate another agent.
          return prev;
        }
        const next: EditableAgent = {
          ...prev,
          graphId,
          prompts: { ...defaults.prompt_dict },
          toolKeys: defaults.tool_keys || [],
        };
        if (next.isDraft) {
          setDraftAgents((drafts) => drafts.map((draft) => (draft.id === next.id ? next : draft)));
        }
        return next;
      });
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
      setMcpToolKeys(resp.tool_keys || []);
      try {
        setMcpEntries(parseMcpEntries(resp.raw_content || ""));
      } catch (error) {
        setMcpEntries([]);
        setStatusMessage((error as Error).message);
        return;
      }
      await refreshMcpAvailableTools();
      setStatusMessage("MCP config loaded.");
    } catch (error) {
      setStatusMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function saveMcpConfig(): Promise<void> {
    const names = new Set<string>();
    for (const entry of mcpEntries) {
      const name = entry.name.trim();
      if (!name) {
        setStatusMessage("Each MCP entry must have a name.");
        return;
      }
      if (names.has(name)) {
        setStatusMessage(`Duplicate MCP name '${name}'.`);
        return;
      }
      names.add(name);
      if (entry.transport === "stdio") {
        if (!entry.command.trim()) {
          setStatusMessage(`MCP '${name}' requires command for stdio transport.`);
          return;
        }
      } else if (!entry.url.trim()) {
        setStatusMessage(`MCP '${name}' requires url for ${entry.transport} transport.`);
        return;
      }
    }

    const rawContent = buildMcpRawContent(mcpEntries);
    setBusy(true);
    setStatusMessage("Saving MCP config...");
    try {
      const resp = await updateMcpToolConfig({ raw_content: rawContent });
      setMcpConfigPath(resp.path || "");
      setMcpToolKeys(resp.tool_keys || []);
      await refreshMcpAvailableTools();
      setStatusMessage("MCP config saved.");
    } catch (error) {
      setStatusMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function refreshMcpAvailableTools(): Promise<void> {
    try {
      const resp = await listMcpAvailableTools();
      const nextTools: Record<string, string[]> = {};
      const nextErrors: Record<string, string> = {};
      const servers = resp.servers || {};
      for (const [serverName, info] of Object.entries(servers)) {
        nextTools[serverName] = Array.isArray(info?.tools) ? info.tools : [];
        if (typeof info?.error === "string" && info.error.trim()) {
          nextErrors[serverName] = info.error;
        }
      }
      setMcpToolsByServer(nextTools);
      setMcpErrorsByServer(nextErrors);
    } catch (error) {
      const message = (error as Error).message || "Unknown error";
      setMcpToolsByServer({});
      setMcpErrorsByServer({ _global: message });
    }
  }

  function addMcpEntry(): void {
    setMcpEntries((prev) => [...prev, createEmptyMcpEntry()]);
  }

  function removeMcpEntry(id: string): void {
    setMcpEntries((prev) => prev.filter((entry) => entry.id !== id));
  }

  function updateMcpEntry(id: string, patch: Partial<McpEntry>): void {
    setMcpEntries((prev) =>
      prev.map((entry) => (entry.id === id ? { ...entry, ...patch } : entry))
    );
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

      let yamlSyncError = "";
      try {
        await createPipeline({
          graph_id: editor.graphId,
          pipeline_id: editor.pipelineId.trim(),
          prompt_set_id: upsertResp.prompt_set_id,
          tool_keys: editor.toolKeys,
          api_key: editor.apiKey.trim(),
          llm_name: editor.llmName || DEFAULT_LLM_NAME,
          enabled: isEditorRunning,
        });
        await refreshRunning();
      } catch (error) {
        // Preserve the DB save result but surface why YAML/registry sync failed.
        yamlSyncError = (error as Error).message;
      }

      await refreshConfigs();
      const detail = await getPipelineDefaultConfig(upsertResp.pipeline_id);
      const saved = toEditable(detail, false);
      saved.id = makeAgentKey(upsertResp.pipeline_id);
      // apiKey is loaded from backend (persisted in DB) — don't override
      saved.llmName = editor.llmName;
      setEditor(saved);
      setSelectedId(saved.id);
      setDraftAgents((prev) => prev.filter((d) => d.id !== editor.id));
      setStatusMessage(
        yamlSyncError
          ? `Agent config saved, but YAML sync failed: ${yamlSyncError}`
          : "Agent config saved and YAML synced."
      );
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

  const showSidebar = activeTab !== "mcp";

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
              className={`tab-button ${activeTab === "discussions" ? "active" : ""}`}
              onClick={() => setActiveTab("discussions")}
              disabled={busy}
            >
              Agent Discussions
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
        ) : activeTab === "discussions" ? (
          <section className="discussion-section tab-pane">
            <div className="discussion-header">
              <h3>Agent Discussions</h3>
              <div className="header-actions">
                <button
                  type="button"
                  onClick={() =>
                    loadPipelineDiscussions(selectedPipelineId, { keepSelection: true })
                  }
                  disabled={busy || discussionLoading || !canViewDiscussions}
                >
                  Refresh
                </button>
              </div>
            </div>
            {!editor ? (
              <p className="empty">Select an agent from the left to view its discussions.</p>
            ) : editor.isDraft || !selectedPipelineId ? (
              <p className="empty">Save this agent first to start tracking discussion history.</p>
            ) : (
              <div className="discussion-layout">
                <div className="discussion-list">
                  {discussionConversations.length === 0 ? (
                    <p className="empty">No discussions found for this agent yet.</p>
                  ) : (
                    discussionConversations.map((conversation) => (
                      <button
                        key={conversation.conversation_id}
                        className={`discussion-item ${
                          selectedConversationId === conversation.conversation_id
                            ? "selected"
                            : ""
                        }`}
                        onClick={() =>
                          selectDiscussionConversation(conversation.conversation_id)
                        }
                        disabled={discussionLoading}
                      >
                        <strong>{conversation.conversation_id}</strong>
                        <small>
                          messages: {conversation.message_count}
                          {conversation.last_updated
                            ? ` • ${formatDateTime(conversation.last_updated)}`
                            : ""}
                        </small>
                      </button>
                    ))
                  )}
                </div>
                <div className="discussion-thread">
                  {!selectedConversationId ? (
                    <p className="empty">Select a discussion to inspect messages.</p>
                  ) : discussionMessages.length === 0 ? (
                    <p className="empty">No stored messages for this discussion.</p>
                  ) : (
                    discussionMessages.map((message) => (
                      <article
                        key={`${message.sequence_number}-${message.created_at}`}
                        className={`discussion-message ${message.message_type}`}
                      >
                        <div className="discussion-message-meta">
                          <strong>{message.message_type}</strong>
                          <small>
                            #{message.sequence_number}
                            {message.created_at
                              ? ` • ${formatDateTime(message.created_at)}`
                              : ""}
                          </small>
                        </div>
                        <div className="discussion-message-markdown">
                          <ReactMarkdown
                            remarkPlugins={[remarkGfm]}
                            components={{
                              a: ({ node: _node, ...props }) => (
                                <a {...props} target="_blank" rel="noreferrer" />
                              ),
                            }}
                          >
                            {message.content}
                          </ReactMarkdown>
                        </div>
                      </article>
                    ))
                  )}
                </div>
              </div>
            )}
          </section>
        ) : (
          <section className="mcp-config-section tab-pane">
            <div className="mcp-config-header">
              <h3>MCP Tool Options</h3>
              <div className="header-actions">
                <button type="button" onClick={addMcpEntry} disabled={busy}>
                  Add
                </button>
                <button type="button" onClick={reloadMcpConfig} disabled={busy}>
                  Reload
                </button>
                <button type="button" onClick={saveMcpConfig} disabled={busy}>
                  Save
                </button>
              </div>
            </div>
            <p className="empty">
              Configure MCP servers here and save to <code>configs/mcp_config.json</code>.
            </p>
            {mcpConfigPath ? (
              <p className="empty">
                File: <code>{sanitizeConfigPath(mcpConfigPath)}</code>
              </p>
            ) : null}
            <p className="empty">
              Tool options detected: {mcpToolKeys.length ? mcpToolKeys.join(", ") : "(none)"}
            </p>
            <div className="mcp-entry-list">
              {mcpEntries.length === 0 ? (
                <p className="empty">No MCP entries yet. Click Add to create one.</p>
              ) : (
                mcpEntries.map((entry) => (
                  <div key={entry.id} className="mcp-entry-card">
                    <div className="mcp-entry-header">
                      <strong>{entry.name.trim() || "New MCP"}</strong>
                      <button
                        type="button"
                        onClick={() => removeMcpEntry(entry.id)}
                        disabled={busy}
                      >
                        Remove
                      </button>
                    </div>
                    {entry.name.trim() ? (
                      <div className="mcp-tools-inline">
                        <p className="empty">
                          Available tools:{" "}
                          {(mcpToolsByServer[entry.name.trim()] || []).length > 0
                            ? mcpToolsByServer[entry.name.trim()].join(", ")
                            : "(none)"}
                        </p>
                        {mcpErrorsByServer[entry.name.trim()] ? (
                          <p className="mcp-tools-error">
                            Error: {mcpErrorsByServer[entry.name.trim()]}
                          </p>
                        ) : null}
                      </div>
                    ) : (
                      <p className="empty">Set MCP Name, then Save/Reload to fetch tools.</p>
                    )}
                    <div className="mcp-entry-grid">
                      <label>
                        MCP Name
                        <input
                          value={entry.name}
                          onChange={(e) => updateMcpEntry(entry.id, { name: e.target.value })}
                          placeholder="weather"
                          disabled={busy}
                        />
                      </label>
                      <label>
                        Transport
                        <select
                          value={entry.transport}
                          onChange={(e) =>
                            updateMcpEntry(entry.id, {
                              transport: e.target.value as McpTransport,
                            })
                          }
                          disabled={busy}
                        >
                          {MCP_TRANSPORT_OPTIONS.map((option) => (
                            <option key={option} value={option}>
                              {option}
                            </option>
                          ))}
                        </select>
                      </label>
                      {entry.transport === "stdio" ? (
                        <>
                          <label>
                            Command
                            <input
                              value={entry.command}
                              onChange={(e) =>
                                updateMcpEntry(entry.id, { command: e.target.value })
                              }
                              placeholder="python"
                              disabled={busy}
                            />
                          </label>
                          <label>
                            Args (comma separated, optional)
                            <input
                              value={entry.args}
                              onChange={(e) => updateMcpEntry(entry.id, { args: e.target.value })}
                              placeholder="server.py, --port, 8000"
                              disabled={busy}
                            />
                          </label>
                        </>
                      ) : (
                        <>
                          <label className="mcp-entry-wide">
                            URL
                            <input
                              value={entry.url}
                              onChange={(e) => updateMcpEntry(entry.id, { url: e.target.value })}
                              placeholder="http://127.0.0.1:8100"
                              disabled={busy}
                            />
                          </label>
                          <label className="mcp-entry-wide">
                            Authorization (optional)
                            <input
                              value={entry.authorization}
                              onChange={(e) =>
                                updateMcpEntry(entry.id, { authorization: e.target.value })
                              }
                              placeholder="Bearer <token>"
                              disabled={busy}
                            />
                          </label>
                        </>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
            {mcpErrorsByServer._global ? (
              <p className="mcp-tools-error">Error: {mcpErrorsByServer._global}</p>
            ) : null}
          </section>
        )}
      </main>
    </div>
  );
}

