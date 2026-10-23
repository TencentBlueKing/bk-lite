'use client';

import { Button, Typography } from 'antd';
import { useState, type ReactNode } from 'react';

import OperateDrawer from '@/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';

function GuideSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="space-y-2">
    <Typography.Title level={5} className="!mb-0 !text-sm !text-[var(--color-text-1)]">{title}</Typography.Title>
    <div className="space-y-2 text-sm leading-6 text-[var(--color-text-2)]">{children}</div>
  </section>;
}

function CodeBlock({ children }: { children: string }) {
  return <pre className="overflow-x-auto rounded-md border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3 py-2 text-xs leading-5 text-[var(--color-text-1)] whitespace-pre-wrap">{children}</pre>;
}

export function DataTransformSqlGuideDrawer() {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const title = t('workflowOrchestration.editor.viewDataTransformSqlGuide', 'SQL 写法说明');

  return <>
    <Button type="link" size="small" className="h-auto px-0" onClick={() => setOpen(true)}>
      {title}
    </Button>
    <OperateDrawer title={title} width={560} open={open} onClose={() => setOpen(false)} destroyOnClose>
      <div className="flex flex-col gap-5 pb-4">
        <GuideSection title={t('workflowOrchestration.editor.dataTransformSqlWhereTitle', '输入位置')}>
          <p className="m-0">{t('workflowOrchestration.editor.dataTransformSqlWhereBody', '输入必须是 JSON 对象。平台将整份对象写入临时表 input 的 payload 列。查询使用 SQLite JSON 函数读取该列，不能引用前面查询写出的结果名。')}</p>
        </GuideSection>
        <GuideSection title={t('workflowOrchestration.editor.dataTransformSqlStatementTitle', '语句约束')}>
          <p className="m-0">{t('workflowOrchestration.editor.dataTransformSqlStatementBody', '每条查询只能是一条 SELECT，也可以以 WITH 开头。结果名写入输出 JSON 的同名字段，并覆盖原有同名字段。结果名由字母、数字和下划线组成，不能以数字开头，不能重复，最多 20 条。')}</p>
        </GuideSection>
        <GuideSection title={t('workflowOrchestration.editor.dataTransformSqlReadTitle', '读取字段')}>
          <p className="m-0">{t('workflowOrchestration.editor.dataTransformSqlReadBody', '路径以 $ 开头。对象用点号，数组用下标。')}</p>
          <CodeBlock>{`SELECT json_extract(input.payload, '$.summary.total') AS total`}</CodeBlock>
        </GuideSection>
        <GuideSection title={t('workflowOrchestration.editor.dataTransformSqlObjectTitle', '构造对象')}>
          <p className="m-0">{t('workflowOrchestration.editor.dataTransformSqlObjectBody', '查询只返回一行一列，且单元格是 JSON 对象或数组文本时，输出直接采用解析后的 JSON。需要构造对象时，使用 json_object。')}</p>
          <CodeBlock>{`SELECT json_object(
  'total', json_extract(input.payload, '$.summary.total'),
  'failed', json_extract(input.payload, '$.summary.failed')
)`}</CodeBlock>
        </GuideSection>
        <GuideSection title={t('workflowOrchestration.editor.dataTransformSqlArrayTitle', '展开数组')}>
          <p className="m-0">{t('workflowOrchestration.editor.dataTransformSqlArrayBody', 'json_each 将数组拆成多行。多行结果整理为对象数组。需要返回 JSON 数组时，使用 json_group_array。')}</p>
          <CodeBlock>{`SELECT
  json_extract(item.value, '$.target.name') AS name,
  json_extract(item.value, '$.result.conclusion') AS conclusion
FROM input, json_each(json_extract(input.payload, '$.data')) AS item`}</CodeBlock>
        </GuideSection>
        <GuideSection title={t('workflowOrchestration.editor.dataTransformSqlShapeTitle', '结果形态')}>
          <ul className="m-0 list-disc space-y-1 pl-5">
            <li>{t('workflowOrchestration.editor.dataTransformSqlShapeEmpty', '零行：[]')}</li>
            <li>{t('workflowOrchestration.editor.dataTransformSqlShapeColumns', '一行多列：一个对象，列名即字段名')}</li>
            <li>{t('workflowOrchestration.editor.dataTransformSqlShapeRows', '多行：对象数组')}</li>
            <li>{t('workflowOrchestration.editor.dataTransformSqlShapeJson', '一行一列，且单元格为 JSON 对象或数组：解析后的 JSON')}</li>
          </ul>
        </GuideSection>
        <GuideSection title={t('workflowOrchestration.editor.dataTransformSqlLimitsTitle', '写入限制')}>
          <p className="m-0">{t('workflowOrchestration.editor.dataTransformSqlLimitsBody', '不允许 INSERT、UPDATE、建表和 PRAGMA，也不能访问 input 以外的数据库。输入不超过 5 MiB。')}</p>
        </GuideSection>
      </div>
    </OperateDrawer>
  </>;
}
