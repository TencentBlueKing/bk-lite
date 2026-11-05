export interface JobOutputTarget {
  name?: string;
  ip?: string;
  stdout?: string;
  stderr?: string;
  exit_code?: number | null;
  timed_out?: boolean;
}

export interface JobOutputValue {
  task_id?: number | string;
  status?: string;
  targets?: JobOutputTarget[];
  result_url?: string;
  waited_seconds?: number;
  kind?: string;
}

const JOB_RESULT_URL = /^\/job\/execution\/job-record\?id=\d+$/;

const escapeHtml = (value: string) =>
  value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');

const waitedPrefix = (seconds: number | undefined) => {
  if (typeof seconds !== 'number' || !Number.isFinite(seconds) || seconds <= 0) {
    return '';
  }
  if (seconds >= 60) {
    return `已等待 ${Math.floor(seconds / 60)} 分钟`;
  }
  return `已等待 ${Math.floor(seconds)} 秒`;
};

const waitText = (seconds: number | undefined) => {
  const waited = waitedPrefix(seconds);
  return waited ? `${waited}，还没有脚本输出。` : '还没有脚本输出。';
};

const fileWaitText = (seconds: number | undefined) => {
  const waited = waitedPrefix(seconds);
  const action = '到作业管理查看任务状态。';
  return waited ? `${waited}。${action}` : action;
};

export const renderJobOutputHtml = (value: JobOutputValue | null | undefined) => {
  if (!value) return '';
  const targets = Array.isArray(value.targets) ? value.targets : [];
  const produced = targets.some((target) => Boolean(target.stdout || target.stderr || target.timed_out));
  const heading = `作业 ${escapeHtml(String(value.task_id || ''))}：${escapeHtml(value.status || '')}`;
  if (!produced) {
    const url = typeof value.result_url === 'string' && JOB_RESULT_URL.test(value.result_url) ? value.result_url : '';
    const link = url
      ? `<p><a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">查看作业 ${escapeHtml(String(value.task_id || ''))} 的结果</a></p>`
      : '';
    const detail = value.kind === 'file' ? fileWaitText(value.waited_seconds) : waitText(value.waited_seconds);
    return `<div class="job-script-output"><p>${heading}。${escapeHtml(detail)}</p>${link}</div>`;
  }
  const blocks = targets.map((target) => {
    const title = [target.name, target.ip].filter(Boolean).join(' ');
    const timeout = target.timed_out ? '\n该目标执行超时' : '';
    const body = `stdout:\n${target.stdout || ''}\nstderr:\n${target.stderr || ''}${timeout}`;
    return `<p>${escapeHtml(title || '目标')}</p><pre>${escapeHtml(body)}</pre>`;
  }).join('');
  return `<div class="job-script-output"><p>${heading}</p>${blocks}</div>`;
};
