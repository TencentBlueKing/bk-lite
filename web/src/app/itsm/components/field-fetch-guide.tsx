'use client';

interface Props { mode: 'options' | 'value' | 'table'; source?: string; number?: boolean; tree?: boolean; advanced?: boolean; fill?: boolean }
export function FieldFetchGuide({ mode, source, number, tree, advanced, fill }: Props) {
  if (advanced) return <details className="rounded bg-[var(--color-fill-1)] p-3 text-xs leading-6">
    <summary className="cursor-pointer font-medium">高级设置怎么填？</summary>
    <dl className="mt-2 space-y-2">
      <div><dt className="font-medium">输入行数据与脚本参数</dt><dd>Python 的 rows 是待处理的表格行；只计算金额等结果时，保留“空数据”。params 是脚本需要的参数，例如 amount。参数名要与脚本约定一致，值可选择表单里的“申请金额”。</dd></div>
      <div><dt className="font-medium">完整输入参数（JSON）</dt><dd>这是发送给接口或脚本的参数，不是接口返回结果。一般使用参数选择器即可；只有需要对象、数组等复杂输入时才编辑这里。</dd><dd className="mt-1 break-all font-mono">{'Python 示例：{"rows":[],"params":{"amount":100}}'}</dd></div>
      <div><dt className="font-medium">手动路径</dt><dd>用点号逐层找到返回数据里的字段，数字 0 表示第一条记录。列表路径例如 data.items；名称路径例如 title；数值填充值例如 data.total 或 0.amount。名称和值的路径相对于列表中的每一条记录。</dd></div>
      <div><dt className="font-medium">手动列映射</dt><dd>左边是本表格的列标识，右边是返回行里的字段路径。例如 {'{"name":"title","amount":"count"}'}。列标识必须已在表格中定义。</dd></div>
      <div><dt className="font-medium">结果加工</dt><dd>已有返回结果需要重新整理时，再选一个 Python 动作。它接收列表路径指向的数据作为 rows，返回结果供下方映射使用。修改加工动作后请重新测试。</dd></div>
      <div><dt className="font-medium">取数时机</dt><dd>通常选“首次加载及依赖变化”。例如接口参数引用了部门字段，部门改变后重新取数。“手动刷新”则等待用户点击字段旁的刷新按钮。</dd></div>
      <div><dt className="font-medium">测试表单值（JSON）</dt><dd>用于模拟用户填写的值，不会创建工单。键使用字段标识而非显示名称，例如 {'{"department":"运维","amount":100}'}。只有参数引用了表单字段时才需要填写。</dd></div>
    </dl>
  </details>;
  const example = mode === 'options'
    ? source === 'dictionary' && !tree ? '[{"value":"high","label":"高优先级"}]' : tree ? '[{"value":"bj","label":"北京","children":[{"value":"room1","label":"一号机房"}]}]' : source === 'python' || source === 'table' ? '[{"id":"device1","name":"数据库服务器"}]' : '{"data":{"items":[{"id":"device1","name":"数据库服务器"}]}}'
    : mode === 'table' ? '[{"name":"数据库服务器","amount":2}]' : source === 'python' || source === 'table' ? number ? '[{"amount":100}]' : '[{"name":"数据库服务器"}]' : number ? '{"data":{"total":100}}' : '{"data":{"name":"数据库服务器"}}';
  return <details className="rounded bg-[var(--color-fill-1)] p-3 text-xs leading-6">
    <summary className="cursor-pointer font-medium">不会配置？查看操作指引</summary>
    <ol className="mt-2 list-decimal space-y-1 pl-4">
      <li>选择数据来源和具体资源。{source === 'dictionary' ? '字典已经定义了名称和值，无需额外配置映射。' : source === 'table' ? '选择数据表后，可展开“筛选条件”限定查询范围。多个条件需要同时满足。' : 'API 选择已有查询接口，Python 选择已有计算动作；先确认必填参数。'}</li>
      <li>点击“测试并选择返回字段”。如果参数引用了其他表单字段，在“高级设置 → 测试表单值”里提供测试值。</li>
      <li>{source === 'dictionary' ? '字典直接使用预设名称和值，跳过映射选择。' : mode === 'options' ? '选择“显示名称”（用户看到的文字）和“选项值”（系统保存的唯一标识）。' : mode === 'table' ? '为每一列选择对应返回字段，例如名称列选 name，数量列选 amount。' : `选择“填充值”。这里只列出${number ? '数值' : '文本'}类型的结果。`}{source !== 'dictionary' && source !== 'table' && mode !== 'value' && '如果返回结果包含多组列表，先选“返回列表”。'}</li>
      <li>点击“验证映射”，看到成功结果后保存。需要让服务使用新配置时，再按流程发布；测试本身不会提交或发布工单。</li>
    </ol>
    <p className="mt-3 font-medium">参考示例（不会修改当前配置）</p>
    <pre className="max-h-36 overflow-auto whitespace-pre-wrap break-all rounded bg-[var(--color-bg)] p-2 leading-5">{example}</pre>
    <p>{source === 'dictionary' ? '选择字典后直接测试和验证；层级字典使用其父子关系。' : mode === 'options' ? tree ? '名称选 label，选项值选 value；children 表示下一层节点。' : source === 'python' ? '返回列表选“整个返回值”，显示名称选 name，选项值选 id。' : source === 'table' ? '显示名称选 name 列，选项值选 id 列。' : '返回列表选 data.items，显示名称选 name，选项值选 id。' : mode === 'table' ? '返回列表选“整个返回值”，名称列选 name，数量列选 amount。' : `填充值选 ${source === 'table' ? number ? 'amount 列' : 'name 列' : source === 'python' ? number ? '0.amount' : '0.name' : number ? 'data.total' : 'data.name'}。保留“允许手动修改”，用户可以调整自动填入的内容。`}</p>
    {mode === 'options' && fill && <p className="mt-2">需要选设备后自动填写其他内容？展开“选中后填充其他字段”，先选目标字段，再选返回值来源。此能力仅用于单选字段，目标为文本或数值字段。</p>}
    <details className="mt-3"><summary className="cursor-pointer font-medium">测试失败怎么处理？</summary>
      <ul className="list-disc space-y-1 pl-4">
        <li>提示缺少参数或依赖字段：补齐接口参数及“测试表单值”，然后重新测试。</li>
        <li>返回列表为空：调整筛选条件；数据表仍可按列配置。没有样本的 API 可在高级设置填写已知路径。</li>
        <li>提示路径不存在：重新测试，改用返回字段下拉选择；不要把示例路径直接套到不同接口。</li>
        <li>提示类型不匹配：文本选文字、数值选数字，表格返回值应为行数组。</li>
        <li>无权限或集成停用：确认当前账号有接口访问权限，并检查所选集成是否启用。</li>
      </ul>
    </details>
  </details>;
}
