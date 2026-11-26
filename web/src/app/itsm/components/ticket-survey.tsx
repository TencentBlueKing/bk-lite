'use client';

import { Alert, Button, Empty, Form, Input, Rate } from 'antd';
import { useState } from 'react';
import type { SurveyResult, SurveySubmission, SurveyTemplateSnapshot } from '../types';

export function TicketSurveyPanel({ result, template, canSurvey, onSubmit }: {
  result?: SurveyResult | null;
  template?: SurveyTemplateSnapshot | null;
  canSurvey: boolean;
  onSubmit: (answers: SurveySubmission) => Promise<void>;
}) {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  if (result) {
    return <div className="flex flex-col gap-3 py-3">
      <Rate disabled value={result.score} aria-label="满意度评分" />
      <p className="break-words whitespace-pre-wrap">{result.comment || '已完成评价'}</p>
      {!!result.answers?.length && <dl className="flex flex-col gap-3">
        {result.answers.map(answer => <div key={answer.id}>
          <dt className="text-xs text-[var(--color-text-3)]">{answer.title}</dt>
          <dd className="mt-1 break-words whitespace-pre-wrap">{answer.value}</dd>
        </div>)}
      </dl>}
    </div>;
  }

  if (!canSurvey) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="工单完成后由提单人评价" />;
  }

  const submit = async (submission: SurveySubmission) => {
    setSubmitting(true);
    setError('');
    try {
      await onSubmit(submission);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : '评价失败');
    } finally {
      setSubmitting(false);
    }
  };

  return <Form<SurveySubmission> layout="vertical" disabled={submitting} initialValues={{ score: 5, comment: '' }}
    onFinish={submit} className="max-w-xl py-3">
    {template?.name && <h3 className="mb-4 text-sm font-medium">{template.name}</h3>}
    {error && <Alert className="mb-3" type="error" showIcon message={error} />}
    <Form.Item name="score" label="满意度评分" rules={[{ required: true, message: '请选择评分' }]}>
      <Rate allowClear={false} aria-label="满意度评分" />
    </Form.Item>
    {template?.questions.map(question => <Form.Item key={question.id} name={['answers', question.id]} label={question.title}
      rules={question.required ? [{ required: true, whitespace: true, message: '请填写答复' }] : []}>
      <Input.TextArea maxLength={1000} rows={2} />
    </Form.Item>)}
    <Form.Item name="comment" label="评价意见">
      <Input.TextArea placeholder="请填写评价意见（选填）" maxLength={500} rows={3} />
    </Form.Item>
    <Button type="primary" htmlType="submit" loading={submitting}>提交评价</Button>
  </Form>;
}
