import type {
  AvailableGraphsResponse,
  GraphConfigListResponse,
  GraphConfigReadResponse,
  GraphConfigUpsertRequest,
  GraphConfigUpsertResponse,
  PipelineCreateRequest,
  PipelineCreateResponse,
  PipelineListResponse,
  PipelineStopResponse,
} from "../types";

const API_BASE_URL =
  import.meta.env.VITE_FRONT_API_BASE_URL?.trim() || "http://127.0.0.1:8001";

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

export function stopPipeline(runId: string): Promise<PipelineStopResponse> {
  return fetchJson(`/v1/pipelines/${runId}`, {
    method: "DELETE",
  });
}

