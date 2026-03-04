import type { GraphConfigListItem } from "./types";

function toTimestamp(value?: string | null): number {
  if (!value) {
    return 0;
  }
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? 0 : parsed;
}

export function chooseActiveConfigItem(
  items: GraphConfigListItem[],
  pipelineId: string
): GraphConfigListItem | null {
  const candidates = items.filter((item) => item.pipeline_id === pipelineId);
  if (candidates.length === 0) {
    return null;
  }
  const active = candidates.find((item) => item.is_active);
  if (active) {
    return active;
  }
  return [...candidates].sort((a, b) => toTimestamp(b.updated_at) - toTimestamp(a.updated_at))[0];
}

export function chooseDisplayItemsByPipeline(
  items: GraphConfigListItem[]
): GraphConfigListItem[] {
  const byPipeline = new Map<string, GraphConfigListItem[]>();
  for (const item of items) {
    const list = byPipeline.get(item.pipeline_id) || [];
    list.push(item);
    byPipeline.set(item.pipeline_id, list);
  }

  const out: GraphConfigListItem[] = [];
  for (const [pipelineId, list] of byPipeline.entries()) {
    const selected = chooseActiveConfigItem(list, pipelineId);
    if (selected) {
      out.push(selected);
    }
  }
  return out.sort((a, b) => a.pipeline_id.localeCompare(b.pipeline_id));
}

