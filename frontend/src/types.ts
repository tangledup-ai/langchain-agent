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
  graph_params?: Record<string, unknown>;
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
  api_key?: string;
  llm_name: string;
  enabled?: boolean;
  graph_params?: Record<string, unknown>;
};

export type PipelineSpec = {
  pipeline_id: string;
  graph_id: string;
  enabled: boolean;
  config_file: string;
  llm_name: string;
};

export type PipelineCreateResponse = {
  pipeline_id: string;
  prompt_set_id: string;
  graph_id: string;
  config_file: string;
  llm_name: string;
  enabled: boolean;
  reload_required: boolean;
  registry_path: string;
};

export type PipelineListResponse = {
  items: PipelineSpec[];
  count: number;
};

export type PipelineStopResponse = {
  pipeline_id: string;
  status: string;
  enabled: boolean;
  reload_required: boolean;
};

export type ConversationListItem = {
  conversation_id: string;
  pipeline_id: string;
  message_count: number;
  last_updated?: string | null;
};

export type PipelineConversationListResponse = {
  pipeline_id: string;
  items: ConversationListItem[];
  count: number;
};

export type ConversationMessageItem = {
  message_type: string;
  content: string;
  sequence_number: number;
  created_at: string;
};

export type PipelineConversationMessagesResponse = {
  pipeline_id: string;
  conversation_id: string;
  items: ConversationMessageItem[];
  count: number;
};

export type RuntimeAuthInfoResponse = {
  fast_api_key: string;
  source: string;
};

export type McpToolConfigResponse = {
  path: string;
  raw_content: string;
  tool_keys: string[];
};

export type McpToolConfigUpdateRequest = {
  raw_content: string;
};

export type McpToolConfigUpdateResponse = {
  status: string;
  path: string;
  tool_keys: string[];
};

export type McpAvailableToolsResponse = {
  available_tools: string[];
  errors: string[];
  servers: Record<
    string,
    {
      tools: string[];
      error?: string | null;
    }
  >;
};

