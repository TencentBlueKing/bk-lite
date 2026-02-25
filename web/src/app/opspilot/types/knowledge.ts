export interface KnowledgeValues {
  id: number,
  name: string;
  team: string[];
  introduction: string;
  embed_model: number;
  is_training?: boolean;
  [key: string]: unknown;
}

export interface Card {
  id: number;
  name: string;
  introduction: string;
  created_by?: string;
  team_name?: string;
  team: string[];
  embed_model: number;
  permissions?: string[];
  [key: string]: unknown;
}

export interface ModifyKnowledgeModalProps {
  visible: boolean;
  onCancel: () => void;
  onConfirm: (values: KnowledgeValues) => void;
  initialValues?: KnowledgeValues | null;
  isTraining?: boolean;
}

export interface PreviewData {
  id: number;
  content: string;
  characters: number;
}

export interface ModelOption {
  id: number;
  name: string;
  enabled: boolean;
}

export interface ConfigDataProps {
  rerankModel: boolean;
  selectedRerankModel: string | null;
  selectedEmbedModel: string | null;
  resultCount: number | null;
  rerankTopK: number;
  enableNaiveRag: boolean;
  enableQaRag: boolean;
  enableGraphRag: boolean;
  ragSize: number;
  qaSize: number;
  graphSize: number;
  // New retrieval strategy fields
  searchType: 'similarity_score_threshold' | 'mmr';
  scoreThreshold: number;
  ragRecallMode?: 'chunk' | 'segment';
}

export interface TableData {
  id: string | number;
  name: string;
  chunk_size: number;
  created_by: string;
  created_at: string;
  train_status: number;
  train_status_display: string;
  [key: string]: any
}

export interface QAPairData {
  id: number;
  permissions: string[];
  created_at: string;
  updated_at: string;
  created_by: string;
  updated_by: string;
  domain: string;
  updated_by_domain: string;
  name: string;
  description: string | null;
  qa_count: number;
  document_id: number;
  document_source: string;
  knowledge_base: number;
  llm_model: number;
  status: string;
  create_type: string;
}

// 知识图谱相关类型定义
export interface GraphNode {
  id: string;
  label: string;
  labels: string[];
  node_id?: number;
  group_id?: string;
  name?: string;
  uuid?: string;
  fact?: string | null;
  summary?: string | null;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  type: 'relation' | 'reference';
  relation_type?: string;
  source_name?: string;
  target_name?: string;
  source_id?: number;
  target_id?: number;
  fact?: string | null;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface KnowledgeGraphViewProps {
  data: GraphData;
  loading?: boolean;
  height?: number | string;
  onNodeClick?: (node: GraphNode) => void;
  onEdgeClick?: (edge: GraphEdge) => void;
  useMockData?: boolean;
}

// 测试相关类型定义
export interface QAPair {
  id: string;
  question: string;
  answer: string;
  score?: number;
  base_chunk_id?: string;
}

export interface GraphDataItem {
  name: string;
  uuid: number | string | undefined;
  group_id: string;
  node_id: number;
  edges: Array<{
    relation_type: string;
    source: string;
    target: string;
    source_name: string;
    target_name: string;
    source_id: number;
    target_id: number;
  }>;
}

export interface TestKnowledgeResponse {
  docs: any[]; // 可以根据实际的ResultItem类型进行更具体的定义
  qa_docs: QAPair[];
  graph_data: GraphDataItem[];
}

export interface ConfigProps {
  configData: ConfigDataProps;
  setConfigData: React.Dispatch<React.SetStateAction<ConfigDataProps>>;
}

export interface DocumentInfo {
  knowledge_id: number;
  name: string;
  knowledge_base_id: number;
  knowledge_source_type: string;
}

export interface FormData {
  llmModel: number;
  qaCount: number;
}

export interface ChunkItem {
  id: string;
  content: string;
}

// QAPairForm 相关类型定义
export interface QAPairFormData {
  questionLlmModel: number;
  answerLlmModel: number;
  qaCount: number;
  questionPrompt: string;
  answerPrompt: string;
  selectedDocuments: string[];
}

export interface DocumentItem {
  key: string;
  title: string;
  description?: string;
  type?: string;
  status?: string;
  chunk_size?: number;
  [key: string]: unknown;
}

export interface QAPairFormProps {
  initialData?: Partial<QAPairFormData>;
  onFormChange?: (isValid: boolean) => void;
  onFormDataChange?: (data: QAPairFormData) => void;
}

export interface PreviewQAPair {
  question: string;
  answer?: string;
  content: string;
}

export interface EmbeddingModel {
  id: number;
  name: string;
  enabled: boolean;
}

export interface RerankModel {
  id: number;
  name: string;
  enabled: boolean;
}

export interface OcrModel {
  id: number;
  name: string;
  enabled?: boolean;
}

export interface KnowledgeBaseListParams {
  page?: number;
  page_size?: number;
  name?: string;
  team?: string;
  search?: string;
}

// 分页响应格式
export interface KnowledgeBaseListPaginatedResponse {
  count: number;
  items: Card[];
}

// 接口返回类型：无分页参数时返回列表，有分页参数时返回分页格式
export type KnowledgeBaseListResponse = Card[] | KnowledgeBaseListPaginatedResponse;

export interface DocumentListParams {
  page?: number;
  page_size?: number;
  name?: string;
  knowledge_source_type?: string;
  knowledge_base_id?: string | number | null;
}

export interface DocumentListResponse {
  count: number;
  items: TableData[];
}

export interface QAPairListParams {
  page?: number;
  page_size?: number;
  name?: string;
  knowledge_base_id?: string | null;
}

export interface QAPairListResponse {
  count: number;
  items: QAPairData[];
}

export interface KnowledgeBaseDetails {
  id: number;
  name: string;
  introduction: string;
  permissions: string[];
  file_count: number;
  web_page_count: number;
  manual_count: number;
  qa_count: number;
  graph_count: number;
  document_count: number;
  [key: string]: unknown;
}

export interface DocumentDetail {
  id: number;
  name: string;
  chunk_size: number;
  chunk_overlap: number;
  knowledge_source_type: string;
  content?: string;
  url?: string;
  max_depth?: number;
  sync_enabled?: boolean;
  sync_time?: string;
  [key: string]: unknown;
}

export interface KnowledgeSettings {
  embed_model?: number | string;
  rerank_model?: number | string | null;
  result_count?: number;
  rerank_top_k?: number;
  enable_naive_rag?: boolean;
  enable_qa_rag?: boolean;
  enable_graph_rag?: boolean;
  rag_size?: number;
  qa_size?: number;
  graph_size?: number;
  search_type?: 'similarity_score_threshold' | 'mmr';
  score_threshold?: number;
  rag_recall_mode?: 'chunk' | 'segment';
  [key: string]: unknown;
}

export interface TestKnowledgeParams {
  knowledge_base_id: number | string;
  query: string;
  top_k?: number;
  enable_naive_rag?: boolean;
  enable_qa_rag?: boolean;
  enable_graph_rag?: boolean;
  [key: string]: unknown;
}

export interface AnnotationPayload {
  history_id?: string | number;
  tag_type?: string;
  tag_value?: string;
  question?: string;
  knowledge_base_id?: number;
  answer_id?: string;
  content?: string;
  tag_id?: string | number;
  [key: string]: unknown;
}

export interface ParseContentParams {
  knowledge_document_ids?: number[];
  knowledge_document_list?: Array<{
    id: number;
    name?: string;
    enable_ocr_parse?: boolean;
    ocr_model?: string | null;
    parse_type?: string;
  }>;
  knowledge_source_type?: string;
  parse_type?: string;
  ocr_model?: number | null;
}

export interface WebPageKnowledgeParams {
  name: string;
  url: string;
  selector?: string;
  [key: string]: unknown;
}

export interface ManualKnowledgeParams {
  name: string;
  content: string;
  [key: string]: unknown;
}

export interface DocumentConfigResponse {
  id: number;
  name: string;
  chunk_size: number;
  chunk_overlap: number;
  chunk_type: string;
  parse_type: string;
  ocr_model: number | null;
  semantic_embedding_model: number | null;
  general_parse_chunk_size?: number;
  general_parse_chunk_overlap?: number;
  semantic_chunk_parse_embedding_model?: number | null;
  [key: string]: unknown;
}

export interface TaskItem {
  id: number;
  document_id?: number;
  document_name?: string;
  status?: string;
  created_at?: string;
  task_name: string;
  train_progress: number;
  is_qa_task: boolean;
}

export interface QAPairTaskStatus {
  id?: number;
  status: string;
  progress?: number;
  process: string | number;
}

export interface ChunkDetail {
  id: string;
  content: string;
  metadata?: Record<string, unknown>;
  question?: string;
  answer?: string;
  doc_name?: string;
  [key: string]: unknown;
}

export interface KnowledgeGraphDetails {
  graph_id?: number;
  is_exists: boolean;
  graph?: GraphData;
  status?: string;
}

export interface KnowledgeGraphConfig {
  knowledge_base: number;
  llm_model: number;
  rerank_model: number;
  embed_model: number;
  rebuild_community: boolean;
  doc_list: Array<{
    id: number;
    source: string;
  }>;
}

export interface QAPairDetailResponse {
  id: number;
  name: string;
  llm_model: number;
  answer_llm_model: number;
  qa_count: number;
  question_prompt: string;
  answer_prompt: string;
  document_id: number;
  document_source: string;
}

export interface GeneratedQuestion {
  question: string;
  content: string;
}

export interface GeneratedAnswer {
  answer: string;
  question: string;
}

