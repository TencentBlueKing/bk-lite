import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import DistributeFileButton from '../DistributeFileButton';
import { renderJobOutputHtml } from '../jobOutput';

describe('job distribute entry', () => {
  it('stays hidden until the job tool is enabled', () => {
    const hidden = render(<DistributeFileButton enabled={false} label="分发文件" onFile={() => undefined} />);
    expect(hidden.queryByRole('button', { name: '分发文件' })).toBeNull();
    hidden.unmount();

    render(<DistributeFileButton enabled label="分发文件" onFile={() => undefined} />);
    expect(screen.getByRole('button', { name: '分发文件' })).toBeTruthy();
  });

  it('renders script output without letting it become markup', () => {
    const html = renderJobOutputHtml({
      task_id: 7,
      status: '成功',
      targets: [{ name: 'web-1', ip: '10.0.0.8', stdout: '<script>alert(1)</script>', timed_out: true }],
    });
    expect(html).toContain('作业 7：成功');
    expect(html).toContain('该目标执行超时');
    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
  });

  it('links to the job record when the script produced no output', () => {
    const html = renderJobOutputHtml({
      task_id: 7,
      status: '仍在执行',
      waited_seconds: 300,
      result_url: '/job/execution/job-record?id=7',
      targets: [{ name: '10.10.40.117', ip: '10.10.40.117', stdout: '', stderr: '' }],
    });
    expect(html).toContain('已等待 5 分钟，还没有脚本输出。');
    expect(html).toContain('href="/job/execution/job-record?id=7"');
    expect(html).toContain('查看作业 7 的结果');
    expect(html).not.toContain('stdout:');
  });

  it('points an unfinished file job at the job record', () => {
    const html = renderJobOutputHtml({
      task_id: 10,
      status: '仍在执行',
      kind: 'file',
      waited_seconds: 300,
      result_url: '/job/execution/job-record?id=10',
      targets: [],
    });
    expect(html).toContain('作业 10：仍在执行。已等待 5 分钟。到作业管理查看任务状态。');
    expect(html).toContain('href="/job/execution/job-record?id=10"');
    expect(html).not.toContain('脚本输出');
  });

  it('shows script output without a job-record link', () => {
    const html = renderJobOutputHtml({
      task_id: 7,
      status: '成功',
      result_url: '/job/execution/job-record?id=7',
      targets: [{ name: 'web-1', stdout: 'Windows IP Configuration' }],
    });
    expect(html).toContain('Windows IP Configuration');
    expect(html).not.toContain('href=');
  });
});
