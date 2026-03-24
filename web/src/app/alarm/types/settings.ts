export interface AlertAssignListItem {
    id: number;
    created_at: string;
    updated_at: string;
    created_by: string;
    updated_by: string;
    name: string;
    match_type: string;
    match_rules: Record<string, any>;
    personnel: string[];
    notify_channels: string;
    notification_scenario: string;
    config: {
        type: string;
        end_time: string;
        start_time: string;
        week_month: string;
    };
    notification_frequency: Record<
        string,
        { max_count: number; interval_minutes: number }
    >;
    is_active: boolean;
}

export interface AlertShieldListItem {
    id: number;
    created_at: string;
    updated_at: string;
    created_by: string;
    updated_by: string;
    name: string;
    match_type: string;
    match_rules: Array<Array<{
        key: string;
        value: string;
        operator: string;
    }>>;
    suppression_time: {
        type: string;
        end_time: string;
        start_time: string;
        week_month: string[];
    };
    is_active: boolean;
}

export interface AggregationRule {
    id: number;
    created_at: string;
    updated_at: string;
    created_by: string;
    updated_by: string;
    rule_id: string;
    name: string;
    description: { en: string; zh: string };
    image: string;
    [key: string]: any;
}

export interface FilterRule {
    key: string;
    operator: string;
    value: string | number;
}

export interface AlarmStrategyParams {
    policy?: 'service' | 'location' | 'resource_name' | 'other';
    group_by?: Array<'service' | 'location' | 'resource_name' | 'item'>;
    window_size?: number;
    time_out?: boolean;
    time_minutes?: number;
}

export interface HeartbeatAlertTemplate {
    title: string;
    level: string;
    description: string;
}

export interface HeartbeatParams {
    check_mode: 'cron';
    cron_expr: string;
    grace_period: number;
    activation_mode: 'first_heartbeat' | 'immediate';
    auto_recovery: boolean;
    heartbeat_status?: 'waiting' | 'monitoring' | 'alerting';
    last_heartbeat_time?: string | null;
    last_heartbeat_context?: Record<string, string | null> | null;
    alert_template: HeartbeatAlertTemplate;
}

export interface CorrelationRule {
    id: number;
    created_at: string;
    updated_at: string;
    created_by: string;
    updated_by: string;
    name: string;
    strategy_type?: 'smart_denoise' | 'missing_detection';
    team?: string[];
    dispatch_team?: string[];
    match_rules?: FilterRule[][];
    params?: AlarmStrategyParams | HeartbeatParams;
    auto_close?: boolean;
    close_minutes?: number;
    last_execute_time?: string;
}



export interface Config {
  notify_every: number;
  notify_people: string[];
  notify_channel: string[];
}

export interface GlobalConfig {
  id: string | number;
  key: string;
  value: Config;
  description: string;
  is_activate: boolean;
  is_build: boolean;
}


export interface ChannelItem {
  id: number;
  name: string;
  channel_type: string;
}

export interface NotifyOption {
  label: string;
  value: string;
}
