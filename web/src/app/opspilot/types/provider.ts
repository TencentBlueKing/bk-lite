export interface ModelConfig {
    openai_api_key?: string;
    api_key?: string;
    openai_base_url?: string;
    base_url?: string;
    model?: string;
}

export type ProviderResourceType = 'llm_model' | 'embed_provider' | 'rerank_provider' | 'ocr_provider';

export type VendorType = 'openai' | 'azure' | 'aliyun' | 'zhipu' | 'baidu' | 'anthropic' | 'deepseek' | 'other';

export interface Model {
    id: number;
    name: string;
    model?: string;
    enabled: boolean;
    is_build_in?: boolean;
    team?: number[];
    team_name?: string[];
    vendor?: number;
    llm_model_type?: string;
    model_type?: string;
    model_type_name?: string;
    icon?: string;
    llm_config?: ModelConfig;
    embed_config?: ModelConfig;
    rerank_config?: ModelConfig;
    ocr_config?: ModelConfig;
    permissions?: string[];
    // 新增分组相关字段
    group_id?: string;
    group_name?: string;
    label?: string;
}

export interface ModelVendor {
    id: number;
    name: string;
    vendor_type: VendorType;
    api_base: string;
    api_key?: string;
    description?: string;
    enabled?: boolean;
    team: number[];
    team_name?: string[];
    permissions?: string[];
    model_count?: number;
    is_build_in?: boolean;
    llm_model_count?: number;
    embed_model_count?: number;
    rerank_model_count?: number;
    ocr_model_count?: number;
}

export interface ModelVendorPayload {
    name: string;
    vendor_type: VendorType;
    api_base: string;
    api_key: string;
    team: number[];
    description?: string;
    enabled?: boolean;
}

export interface TabConfig {
    key: string;
    label: string;
    type: string;
}

// 新增模型分组相关接口
export interface ModelGroup {
    id: number;
    name: string;
    display_name: string;
    icon?: string;
    count?: number;
    is_build_in?: boolean;
    index?: number;
    models?: Model[];
    tags?: string[];
}

export interface TreeNode {
    key: string;
    title: string;
    count?: number;
    is_build_in?: boolean;
    order?: number;
    selectable?: boolean;
    children?: TreeNode[];
}

export interface ModelGroupModalProps {
    visible: boolean;
    mode: 'add' | 'edit';
    group?: ModelGroup | null;
    onOk: (values: { name: string; display_name: string; tags?: string[]; icon?: string }) => Promise<void>;
    onCancel: () => void;
    confirmLoading: boolean;
}

export interface ModelTreeProps {
    filterType: string;
    groups: ModelGroup[];
    selectedGroupId: string;
    onGroupSelect: (groupId: string) => void;
    onGroupAdd: () => void;
    onGroupEdit: (group: ModelGroup) => void;
    onGroupDelete: (groupId: number) => void;
    onGroupOrderChange?: (updateData: { id: number; index: number }[]) => void;
    loading: boolean;
}

export interface ModelGroupPayload {
    name: string;
    display_name: string;
    provider_type?: string;
    icon?: string;
    tags?: string[];
}

export interface GroupOrderPayload {
    id: number;
    index: number;
}
