export function parseInputs(text: string): Record<string, unknown> {
  const value: unknown = JSON.parse(text);
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('参数必须为 JSON 对象');
  return value as Record<string, unknown>;
}

export async function readPythonFile(file: { name: string; size: number; text: () => Promise<string> }) {
  if (!file.name.toLowerCase().endsWith('.py') || file.size > 100000) throw new Error('请选择不超过 100KB 的 .py 文件');
  const script = await file.text();
  if (script.includes('\uFFFD') || script.includes('\0')) throw new Error('请选择 UTF-8 编码的 Python 文件');
  return script;
}

export type IntegrationKind = 'api' | 'python' | 'todo';
export interface IntegrationItem {
  id: number; name: string; kind: IntegrationKind; is_enabled: boolean; updated_by: string;
  config: { transport?: 'gateway' | 'external'; request_schema?: { type?: string; properties?: Record<string, { type: string; description?: string }>; required?: string[] }; path?: string; method?: string; script?: string; filename?: string; url?: string; token?: string };
  has_token?: boolean;
  runs?: { id: number; status: string; code: string; duration_ms: number; created_by: string; created_at: string }[];
  deliveries?: { id: number; task_id: number; status: string; code: string; attempts: number }[];
}
export interface IntegrationResult { status: string; output: unknown; code: string; duration_ms: number; run_id: number }
export const PYTHON_EXAMPLE = 'def transform(rows, params):\n    return [{**row, "result": row.get("amount", 0) * params.get("rate", 1)} for row in rows]\n';
