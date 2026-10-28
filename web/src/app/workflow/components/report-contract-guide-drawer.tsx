'use client';

import { Button, Typography } from 'antd';
import { useState, type ReactNode } from 'react';

import OperateDrawer from '@/components/operate-drawer';
import { useTranslation } from '@/utils/i18n';

export type ReportContractGuideMode = 'template' | 'structure';
export type ReportContractGuideAudience = 'job' | 'document';

const OUTPUT_CONTRACT_SAMPLE = `{
  "summary": { "total": 2, "succeeded": 2, "failed": 0 },
  "data": [
    {
      "target": { "name": "job-web3", "ip": "10.10.90.120" },
      "status": "SUCCESS",
      "exit_code": 0,
      "error": "",
      "result": { "collected_at": "...", "conclusion": "健康", "metrics": [] }
    }
  ]
}`;

function GuideSection({ title, children }: { title: string; children: ReactNode }) {
  return <section className="space-y-2">
    <Typography.Title level={5} className="!mb-0 !text-sm !text-[var(--color-text-1)]">{title}</Typography.Title>
    <div className="space-y-2 text-sm leading-6 text-[var(--color-text-2)]">{children}</div>
  </section>;
}

function CodeBlock({ children }: { children: string }) {
  return <pre className="overflow-x-auto rounded-md border border-[var(--color-border-1)] bg-[var(--color-fill-1)] px-3 py-2 text-xs leading-5 text-[var(--color-text-1)] whitespace-pre-wrap">{children}</pre>;
}

function StructureGuide({ audience }: { audience: ReportContractGuideAudience }) {
  const { t } = useTranslation();
  return <div className="flex flex-col gap-5 pb-4">
    <GuideSection title={t('workflowOrchestration.editor.reportFixedContractTitle', '平台字段')}>
      <p className="m-0">{t('workflowOrchestration.editor.reportFixedContractBody', '平台填写 summary、data、target、status、exit_code、error。脚本不要打印这些字段。data 是主机列表。每台主机的 result 由脚本定义，例如结论和指标。根必须是 JSON 对象，嵌套不超过 10 层。')}</p>
    </GuideSection>
    <GuideSection title={t('workflowOrchestration.editor.reportScriptMarkerTitle', '脚本输出')}>
      <p className="m-0">{t('workflowOrchestration.editor.reportScriptMarkerBody', '每台主机在标准输出单独打印一行，行首固定为 result=，等号后是一个 JSON 对象。平台把它写入该主机的 result。没有这一行时，result 为 {}。')}</p>
      <CodeBlock>{`result={"collected_at":"...","conclusion":"健康","metrics":[]}`}</CodeBlock>
    </GuideSection>
    {audience === 'document' ? (
      <GuideSection title={t('workflowOrchestration.editor.reportDataToTemplateTitle', '数据如何进模板')}>
        <p className="m-0">{t('workflowOrchestration.editor.reportDataToTemplateBody', '文档生成节点在进程内渲染：Word 用 docxtpl，Excel 用 xlsxjinja。模板根数据就是上述 JSON，没有额外的 d 包装：summary 是汇总，data 是主机数组，data[n].result 是该主机脚本返回的业务字段。')}</p>
        <ul className="m-0 list-disc space-y-1 pl-5">
          <li>{t('workflowOrchestration.editor.reportDataToTemplateHost', '跑了几台主机，data 就有几条；表格循环行数由数组长度决定。')}</li>
          <li>{t('workflowOrchestration.editor.reportDataToTemplateMetric', '每台主机内部的 metrics / critical 等数组，可用嵌套循环再展开。')}</li>
        </ul>
      </GuideSection>
    ) : null}
    <GuideSection title={t('workflowOrchestration.editor.reportStructureSampleTitle', '下游结构')}>
      <p className="m-0">{t('workflowOrchestration.editor.reportStructureSampleCaption', 'data 有几台主机就有几条。每条里的 result 就是该主机打印的对象。')}</p>
      <CodeBlock>{OUTPUT_CONTRACT_SAMPLE}</CodeBlock>
    </GuideSection>
  </div>;
}

function TemplateGuide() {
  const { t } = useTranslation();
  return <div className="flex flex-col gap-5 pb-4">
    <GuideSection title={t('workflowOrchestration.editor.reportHowItWorksTitle', '怎么工作')}>
      <p className="m-0">{t('workflowOrchestration.editor.reportHowItWorksBody', '在 Word / Excel 里按最终报告排版，需要灌数据的地方写入 Jinja 占位符。Word 与 Excel 都是 Jinja 风格，但循环写法不同，请按下面两章分别制作。版式、字体、颜色以你在 Office 里画的为准。')}</p>
    </GuideSection>

    <GuideSection title={t('workflowOrchestration.editor.reportWordSyntaxTitle', 'Word（docxtpl）')}>
      <p className="m-0">{t('workflowOrchestration.editor.reportWordSyntaxBody', '字段用 {{ }}。跨段落或表格行循环时，必须用 {%p ... %} / {%tr ... %} 这类特殊标签，普通 {% for %} 不能跨越段落或表格行。')}</p>
      <CodeBlock>{`总数：{{ summary.total }}

{%tr for r in data %}
{{ r.target.name }} | {{ r.target.ip }} | {{ r.result.conclusion }}
{%tr endfor %}`}</CodeBlock>
      <p className="m-0">{t('workflowOrchestration.editor.reportWordLoopHint', '开始/结束标签各自独占一行（表格行）。中间行写 {{ r.字段 }}；引擎按数组长度复制中间行。')}</p>
      <CodeBlock>{`{%tr for r in data %}
主机 {{ r.target.name }}
{%tr for m in r.result.metrics %}
{{ m.category }}  {{ m.metric_name }}  {{ m.value }}
{%tr endfor %}
{%tr endfor %}`}</CodeBlock>
    </GuideSection>

    <GuideSection title={t('workflowOrchestration.editor.reportExcelSyntaxTitle', 'Excel（xlsxjinja）')}>
      <p className="m-0">{t('workflowOrchestration.editor.reportExcelSyntaxBody', '字段同样用 {{ }}。循环用普通 {% for %} / {% endfor %}，放在单元格里；多工作表时每张表各自写循环。')}</p>
      <CodeBlock>{`B1 = {{ summary.total }}
A2 = {% for r in data %}
A3 = {{ r.target.name }}
B3 = {{ r.target.ip }}
C3 = {{ r.result.conclusion }}
A4 = {% endfor %}`}</CodeBlock>
      <CodeBlock>{`A1 = {% for r in data %}
A2 = {% for m in r.result.metrics %}
A3 = {{ r.target.name }}
B3 = {{ m.metric_name }}
C3 = {{ m.value }}
A4 = {% endfor %}
A5 = {% endfor %}`}</CodeBlock>
    </GuideSection>

    <GuideSection title={t('workflowOrchestration.editor.reportWordNotesTitle', 'Word 版式')}>
      <ul className="m-0 list-disc space-y-1 pl-5">
        <li>{t('workflowOrchestration.editor.reportWordNoteLayout', '标题、说明段落、多张独立表格都可以自由排版；像审计报告那样「概览表 + 按严重级别分表」是推荐写法。')}</li>
        <li>{t('workflowOrchestration.editor.reportWordNoteStaticMerge', '非循环区域的静态合并单元格（标题跨列、表头说明）支持，会按模板原样保留。')}</li>
        <li>{t('workflowOrchestration.editor.reportWordNoteNestedTable', '单元格内再嵌套表格，引擎可以处理；更稳妥的做法是像常见巡检报告一样用多张并列普通表，而不是深层表中表。')}</li>
        <li>{t('workflowOrchestration.editor.reportWordNoteEmptyChapter', '数组为空时循环区不会生成数据行，但章节标题等静态文字仍会留下。需要「没数据就整章消失」时，请先用示例模板实测条件写法，当前产品不把条件隐藏章节列为已验证能力。')}</li>
      </ul>
    </GuideSection>

    <GuideSection title={t('workflowOrchestration.editor.reportExcelNotesTitle', 'Excel 注意')}>
      <ul className="m-0 list-disc space-y-1 pl-5">
        <li>{t('workflowOrchestration.editor.reportExcelNotePerSheet', '每张需要循环的工作表都要有自己的 {% for %} / {% endfor %} 成对标记。')}</li>
        <li>{t('workflowOrchestration.editor.reportExcelNoteMerge', '标题等静态合并单元格放在循环区之外；不支持循环标记跨越或切开已有合并区。')}</li>
        <li>{t('workflowOrchestration.editor.reportExcelNoteVertical', '优先使用纵向重复行。不要依赖运行时按数据动态合并单元格，也不要依赖动态图表。')}</li>
        <li>{t('workflowOrchestration.editor.reportExcelNoteStaticOk', '表头、封面区预先合并好的单元格可以保留，只要它们不落在循环区间内。')}</li>
      </ul>
    </GuideSection>

    <GuideSection title={t('workflowOrchestration.editor.reportSupportedTitle', '明确支持')}>
      <ul className="m-0 list-disc space-y-1 pl-5">
        <li>{t('workflowOrchestration.editor.reportSupportedReplace', '单值字段替换（汇总、主机名、IP、脚本 result 字段）')}</li>
        <li>{t('workflowOrchestration.editor.reportSupportedLoop', '按数组纵向循环扩行 / 扩段，以及一层嵌套循环')}</li>
        <li>{t('workflowOrchestration.editor.reportSupportedStaticMerge', '循环外的静态合并单元格与常规 Word/Excel 样式')}</li>
        <li>{t('workflowOrchestration.editor.reportSupportedMultiTable', '同一文档内多张独立表格、多个工作表分别循环')}</li>
      </ul>
    </GuideSection>

    <GuideSection title={t('workflowOrchestration.editor.reportUnsupportedTitle', '明确不做')}>
      <ul className="m-0 list-disc space-y-1 pl-5">
        <li>{t('workflowOrchestration.editor.reportUnsupportedDynamicMerge', '不支持循环内按数据动态合并单元格')}</li>
        <li>{t('workflowOrchestration.editor.reportUnsupportedLoopAcrossMerge', '不支持循环标记跨越已有合并区')}</li>
        <li>{t('workflowOrchestration.editor.reportUnsupportedCharts', '不支持动态图表与任意二维扩展')}</li>
        <li>{t('workflowOrchestration.editor.reportUnsupportedLegacyCarbone', '不支持旧的 Carbone {d.} / [i] 占位符写法')}</li>
      </ul>
    </GuideSection>

    <GuideSection title={t('workflowOrchestration.editor.reportExampleFilesTitle', '对照示例')}>
      <p className="m-0">{t('workflowOrchestration.editor.reportExampleFilesBody', '参数区可下载 Word / Excel 示例模板。建议先下载示例，对着占位符改标题和列，再换成自己的字段路径。')}</p>
    </GuideSection>
  </div>;
}

export function ReportContractGuideDrawer({
  mode,
  audience = 'document',
  triggerLabel,
}: {
  mode: ReportContractGuideMode;
  audience?: ReportContractGuideAudience;
  triggerLabel?: string;
}) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const title = mode === 'template'
    ? t('workflowOrchestration.editor.viewTemplateSyntaxGuide', '模板语法说明')
    : audience === 'job'
      ? t('workflowOrchestration.editor.viewJobOutputContractGuide', '脚本输出说明')
      : t('workflowOrchestration.editor.viewDocumentDataGuide', '数据结构说明');

  return <>
    <Button type="link" size="small" className="h-auto px-0" onClick={() => setOpen(true)}>
      {triggerLabel || title}
    </Button>
    <OperateDrawer
      title={title}
      width={560}
      open={open}
      onClose={() => setOpen(false)}
      destroyOnClose
    >
      {mode === 'template' ? <TemplateGuide /> : <StructureGuide audience={audience} />}
    </OperateDrawer>
  </>;
}
