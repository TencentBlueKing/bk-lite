import type { FormSchema } from '../types';
import type { FlowDesign } from '../constants/demo-flow';
interface PublishApi {
  publishForm: (id: number, schema: unknown) => Promise<unknown>;
  saveDesign: (id: number, design: FlowDesign) => Promise<unknown>;
  publishWorkflow: (id: number) => Promise<unknown>;
}
/** 联合设计页的发布必须先固定当前表单，避免流程继续引用旧选项。 */
export async function publishDesignedWorkflow(api: PublishApi, workflowId: number, formId: number, schema: FormSchema, design: FlowDesign) {
  await api.publishForm(formId, schema);
  // 后端为已发布流程创建新草稿，不能覆盖历史版本的表单快照。
  await api.saveDesign(workflowId, design);
  await api.publishWorkflow(workflowId);
}
