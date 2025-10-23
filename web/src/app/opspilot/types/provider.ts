export interface ModelConfig {
    openai_api_key?: string;
    api_key?: string;
    openai_base_url?: string;
    base_url?: string;
    model?: string;
}

export interface Model {
    id: number;
    name: string;
    enabled: boolean;
    is_build_in?: boolean;
    team?: boolean;
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
