export type GraphConfigListItem = {
  graph_id?: string | null;
  pipeline_id: string;
  prompt_set_id: string;
  name: string;
  description: string;
  is_active: boolean;
  tool_keys: string[];
  api_key: string;
  created_at?: string | null;
  updated_at?: string | null;
};

export type GraphConfigListResponse = {
  items: GraphConfigListItem[];
  count: number;
};

export type GraphConfigReadResponse = {
  graph_id?: string | null;
  pipeline_id: string;
  prompt_set_id: string;
  tool_keys: string[];
  prompt_dict: Record<string, string>;
  api_key: string;
};

export type GraphConfigUpsertRequest = {
  graph_id: string;
  pipeline_id: string;
  prompt_set_id?: string;
  tool_keys: string[];
  prompt_dict: Record<string, string>;
  api_key?: string;
};

export type GraphConfigUpsertResponse = {
  graph_id: string;
  pipeline_id: string;
  prompt_set_id: string;
  tool_keys: string[];
  prompt_keys: string[];
  api_key: string;
};

export type AvailableGraphsResponse = {
  available_graphs: string[];
};

export type PipelineCreateRequest = {
  graph_id: string;
  pipeline_id: string;
  prompt_set_id: string;
  tool_keys: string[];
  port: number;
  api_key: string;
  entry_point: string;
  llm_name: string;
};

export type PipelineRunInfo = {
  run_id: string;
  pid: number;
  graph_id: string;
  pipeline_id: string;
  prompt_set_id: string;
  url: string;
  port: number;
  auth_type: string;
  auth_header_name: string;
  auth_key_masked: string;
};

export type PipelineCreateResponse = PipelineRunInfo & {
  auth_key_once: string;
};

export type PipelineListResponse = {
  items: PipelineRunInfo[];
  count: number;
};

export type PipelineStopResponse = {
  run_id: string;
  status: string;
};

