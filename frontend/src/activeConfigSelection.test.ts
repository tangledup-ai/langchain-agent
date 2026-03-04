import { describe, expect, it } from "vitest";

import { chooseActiveConfigItem, chooseDisplayItemsByPipeline } from "./activeConfigSelection";
import type { GraphConfigListItem } from "./types";

const mk = (patch: Partial<GraphConfigListItem>): GraphConfigListItem => ({
  graph_id: "routing",
  pipeline_id: "agent-a",
  prompt_set_id: "set-1",
  name: "default",
  description: "",
  is_active: false,
  tool_keys: [],
  api_key: "",
  created_at: null,
  updated_at: null,
  ...patch,
});

describe("chooseActiveConfigItem", () => {
  it("prefers active item over newer inactive items", () => {
    const items = [
      mk({
        pipeline_id: "agent-a",
        prompt_set_id: "old-active",
        is_active: true,
        updated_at: "2025-01-01T00:00:00Z",
      }),
      mk({
        pipeline_id: "agent-a",
        prompt_set_id: "new-inactive",
        is_active: false,
        updated_at: "2025-03-01T00:00:00Z",
      }),
    ];
    const selected = chooseActiveConfigItem(items, "agent-a");
    expect(selected?.prompt_set_id).toBe("old-active");
  });

  it("falls back to latest updated_at when no active item exists", () => {
    const items = [
      mk({
        pipeline_id: "agent-b",
        prompt_set_id: "set-1",
        updated_at: "2025-01-01T00:00:00Z",
      }),
      mk({
        pipeline_id: "agent-b",
        prompt_set_id: "set-2",
        updated_at: "2025-02-01T00:00:00Z",
      }),
    ];
    const selected = chooseActiveConfigItem(items, "agent-b");
    expect(selected?.prompt_set_id).toBe("set-2");
  });
});

describe("chooseDisplayItemsByPipeline", () => {
  it("returns one selected item per pipeline_id", () => {
    const items = [
      mk({ pipeline_id: "agent-b", prompt_set_id: "set-1", updated_at: "2025-01-01T00:00:00Z" }),
      mk({
        pipeline_id: "agent-b",
        prompt_set_id: "set-2",
        is_active: true,
        updated_at: "2025-02-01T00:00:00Z",
      }),
      mk({
        pipeline_id: "agent-a",
        prompt_set_id: "set-3",
        updated_at: "2025-03-01T00:00:00Z",
      }),
    ];
    const selected = chooseDisplayItemsByPipeline(items);
    expect(selected.map((x) => x.pipeline_id)).toEqual(["agent-a", "agent-b"]);
    expect(selected.find((x) => x.pipeline_id === "agent-b")?.prompt_set_id).toBe("set-2");
  });
});

