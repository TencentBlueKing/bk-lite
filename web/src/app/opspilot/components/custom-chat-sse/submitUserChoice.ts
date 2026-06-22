/**
 * 提交用户对 request_user_choice 提问的回答（共享给选择卡片与主对话框）。
 *
 * 后端 submit_choice 把 selected 写入选择 cache，正在等待的智能体节点的 wait_for_choice
 * 轮询会立即命中并续跑（在原 SSE 流上）。selected 可以是预设选项 key，也可以是自由文本。
 */
export interface SubmitUserChoiceParams {
  execution_id: string;
  node_id: string;
  choice_id: string;
  selected: string[];
}

export async function postUserChoice(token: string, params: SubmitUserChoiceParams): Promise<void> {
  const response = await fetch('/api/proxy/opspilot/bot_mgmt/submit_choice/', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(params),
  });
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
}
