import type {
  AvailableGraphsResponse,
  ConversationListItem,
  ConversationMessageItem,
  GraphConfigListResponse,
  GraphConfigReadResponse,
  GraphConfigUpsertRequest,
  GraphConfigUpsertResponse,
  McpAvailableToolsResponse,
  McpToolConfigResponse,
  McpToolConfigUpdateRequest,
  McpToolConfigUpdateResponse,
  PipelineCreateRequest,
  PipelineCreateResponse,
  PipelineConversationListResponse,
  PipelineConversationMessagesResponse,
  PipelineListResponse,
  PipelineStopResponse,
  RuntimeAuthInfoResponse,
} from "../types";

const API_BASE_URL =
  import.meta.env.VITE_FRONT_API_BASE_URL?.trim() || "http://127.0.0.1:8500";

// Log which backend the frontend is targeting on startup, with file + line hint.
// This runs once when the module is loaded.
// eslint-disable-next-line no-console
console.info(
  `[frontend] Using FRONT_API_BASE_URL=${API_BASE_URL} (src/api/frontApis.ts:16)`
);

async function fetchJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers || {}),
    },
    ...init,
  });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as { detail?: string };
      if (payload.detail) {
        message = payload.detail;
      }
    } catch {
      // Use fallback message if response is not JSON.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export function listAvailableGraphs(): Promise<AvailableGraphsResponse> {
  return fetchJson("/v1/pipelines/graphs");
}

export function listGraphConfigs(
  params?: Partial<{ pipeline_id: string; graph_id: string }>
): Promise<GraphConfigListResponse> {
  const query = new URLSearchParams();
  if (params?.pipeline_id) {
    query.set("pipeline_id", params.pipeline_id);
  }
  if (params?.graph_id) {
    query.set("graph_id", params.graph_id);
  }
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return fetchJson(`/v1/graph-configs${suffix}`);
}

export function getGraphConfig(
  pipelineId: string,
  promptSetId: string
): Promise<GraphConfigReadResponse> {
  return fetchJson(`/v1/graph-configs/${pipelineId}/${promptSetId}`);
}

export function getGraphDefaultConfig(
  graphId: string
): Promise<GraphConfigReadResponse> {
  return fetchJson(`/v1/graphs/${graphId}/default-config`);
}

export function getPipelineDefaultConfig(
  pipelineId: string
): Promise<GraphConfigReadResponse> {
  return fetchJson(`/v1/graph-configs/default/${pipelineId}`);
}

export function upsertGraphConfig(
  payload: GraphConfigUpsertRequest
): Promise<GraphConfigUpsertResponse> {
  return fetchJson("/v1/graph-configs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function deleteGraphConfig(
  pipelineId: string,
  promptSetId: string
): Promise<{ status: string; pipeline_id: string; prompt_set_id: string }> {
  return fetchJson(`/v1/graph-configs/${pipelineId}/${promptSetId}`, {
    method: "DELETE",
  });
}

export function getMcpToolConfig(): Promise<McpToolConfigResponse> {
  return fetchJson("/v1/tool-configs/mcp");
}

export function updateMcpToolConfig(
  payload: McpToolConfigUpdateRequest
): Promise<McpToolConfigUpdateResponse> {
  return fetchJson("/v1/tool-configs/mcp", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function listMcpAvailableTools(): Promise<McpAvailableToolsResponse> {
  return fetchJson("/v1/tool-configs/mcp/tools");
}

export function createPipeline(
  payload: PipelineCreateRequest
): Promise<PipelineCreateResponse> {
  return fetchJson("/v1/pipelines", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listPipelines(): Promise<PipelineListResponse> {
  return fetchJson("/v1/pipelines");
}

export function stopPipeline(pipelineId: string): Promise<PipelineStopResponse> {
  return fetchJson(`/v1/pipelines/${pipelineId}`, {
    method: "DELETE",
  });
}

export function getRuntimeAuthInfo(): Promise<RuntimeAuthInfoResponse> {
  return fetchJson("/v1/runtime-auth");
}

export async function listPipelineConversations(
  pipelineId: string,
  limit = 100
): Promise<ConversationListItem[]> {
  const response = await fetchJson<PipelineConversationListResponse>(
    `/v1/pipelines/${encodeURIComponent(pipelineId)}/conversations?limit=${limit}`
  );
  return response.items || [];
}

export async function getPipelineConversationMessages(
  pipelineId: string,
  conversationId: string
): Promise<ConversationMessageItem[]> {
  const response = await fetchJson<PipelineConversationMessagesResponse>(
    `/v1/pipelines/${encodeURIComponent(pipelineId)}/conversations/${encodeURIComponent(conversationId)}/messages`
  );
  return response.items || [];
}

type StreamAgentChatOptions = {
  appId: string;
  sessionId: string;
  apiKey: string;
  message: string;
  onText: (text: string) => void;
};

function parseErrorDetail(payload: unknown): string | null {
  if (!payload || typeof payload !== "object") {
    return null;
  }
  const detail = (payload as { detail?: unknown }).detail;
  return typeof detail === "string" && detail.trim() ? detail : null;
}

export async function streamAgentChatResponse(
  options: StreamAgentChatOptions
): Promise<string> {
  const { appId, sessionId, apiKey, message, onText } = options;
  const response = await fetch(
    `${API_BASE_URL}/v1/apps/${encodeURIComponent(appId)}/sessions/${encodeURIComponent(sessionId)}/responses`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        messages: [{ role: "user", content: message }],
        stream: true,
      }),
    }
  );

  if (!response.ok) {
    let messageText = `Request failed (${response.status})`;
    try {
      const payload = (await response.json()) as unknown;
      const detail = parseErrorDetail(payload);
      if (detail) {
        messageText = detail;
      }
    } catch {
      // Keep fallback status-based message.
    }
    throw new Error(messageText);
  }

  if (!response.body) {
    throw new Error("Streaming response is not available.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  let latestText = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffered += decoder.decode(value, { stream: true });

    let splitIndex = buffered.indexOf("\n\n");
    while (splitIndex >= 0) {
      const eventBlock = buffered.slice(0, splitIndex);
      buffered = buffered.slice(splitIndex + 2);
      splitIndex = buffered.indexOf("\n\n");

      const lines = eventBlock.split("\n");
      for (const rawLine of lines) {
        const line = rawLine.trim();
        if (!line.startsWith("data:")) {
          continue;
        }
        const payloadRaw = line.slice(5).trim();
        if (!payloadRaw) {
          continue;
        }
        let payload: unknown;
        try {
          payload = JSON.parse(payloadRaw);
        } catch {
          continue;
        }
        const nextText =
          typeof (payload as { output?: { text?: unknown } })?.output?.text === "string"
            ? ((payload as { output: { text: string } }).output.text as string)
            : "";
        if (nextText !== latestText) {
          latestText = nextText;
          onText(latestText);
        }
      }
    }
  }

  return latestText;
}

