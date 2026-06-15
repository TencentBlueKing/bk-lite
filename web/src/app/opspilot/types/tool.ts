/** 工具变量参数 */
export interface ToolVariable {
  key: string;
  value: unknown;
  description?: string;
  type?: string;
  isRequired?: boolean;
}

/** MCP 工具定义 */
export interface MCPToolDefinition {
  name: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
}

/** 工具请求中的 params 结构 */
export interface ToolParams {
  name: string;
  url: string;
  kwargs: ToolVariable[];
  enable_auth: boolean;
  auth_token: string;
  transport?: string;
}

/** 工具创建/更新请求参数 */
export interface ToolPayload {
  name: string;
  description?: string;
  tags?: string[];
  team?: string[];
  url?: string;
  icon?: string;
  params?: ToolParams;
  tools?: MCPToolDefinition[];
  variables?: ToolVariable[];
  enable_auth?: boolean;
  auth_token?: string;
}

export interface Tool {
  id: string;
  name: string;
  /** 翻译后的展示名称（内置工具按当前语言返回，自定义工具回退为 name） */
  display_name?: string;
  description: string;
  icon: string;
  team: string[];
  tags: string[];
  tagList: string[];
  is_build_in: boolean;
  params: ToolParams;
  tools?: MCPToolDefinition[];
  permissions?: string[];
  enable_auth?: boolean;
  auth_token?: string;
}

export interface FormValues {
  name: string;
  description: string;
  group: string[];
}

export interface SelectTool {
  id: number;
  name: string;
  rawName?: string;
  icon: string;
  description?: string;
  kwargs?: ToolVariable[];
}

export interface TagOption {
  value: string;
  label: string;
}
