export interface AuthSource {
  id: number;
  name: string;
  source_type: string;
  app_id?: string;
  app_secret?: string;
  other_config: {
    callback_url?: string;
    redirect_uri?: string;
    namespace?: string;
    root_group?: string;
    domain?: string;
    url?: string;
    default_roles?: number[];
    sync?: boolean;
    sync_time?: string;
    bk_url?: string;
    app_token?: string;
    app_id?: string;
  };
  enabled: boolean;
  is_build_in: boolean;
  icon?: string;
  description?: string;
}

export interface AuthSourceTypeConfig {
  icon: string;
  description: string;
}

export interface SystemSettings {
  enable_otp: string;
  login_expired_time: string;
  portal_name?: string;
  portal_logo_url?: string;
  portal_favicon_url?: string;
  watermark_enabled?: string;
  watermark_text?: string;
  pwd_set_validity_period?: string;
  pwd_set_required_char_types?: string;
  pwd_set_min_length?: string;
  pwd_set_max_length?: string;
  pwd_set_max_retry_count?: string;
  pwd_set_lock_duration?: string;
  pwd_set_expiry_reminder_days?: string;
  user_create_initial_password_configured?: string;
  user_create_initial_password_mode?: 'fixed' | 'random' | 'none' | string;
  user_create_initial_password_random_email_channel_id?: string;
  otp_whitelist?: string | number[];
  otp_recommended_apps?: string;
}
