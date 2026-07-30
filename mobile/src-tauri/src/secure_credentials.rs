use tauri::command;

#[cfg(target_os = "android")]
use serde::{Deserialize, Serialize};
#[cfg(not(target_os = "android"))]
use tauri::AppHandle;
#[cfg(not(target_os = "android"))]
use tauri_plugin_keyring_store::KeyringExt;

#[cfg(target_os = "android")]
use tauri::{plugin::PluginHandle, Manager, State};

const KEY_PREFIX: &str = "mobile-auth";
const TOKEN_KEY: &str = "auth_token";
const REFRESH_TOKEN_KEY: &str = "refresh_token";
#[cfg(target_os = "android")]
const ANDROID_PLUGIN_NAME: &str = "secureCredentials";

#[cfg(target_os = "android")]
pub struct AndroidSecureCredentials(pub PluginHandle<tauri::Wry>);

#[cfg(target_os = "android")]
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct CredentialSetRequest<'a> {
    key: &'a str,
    value: &'a str,
}

#[cfg(target_os = "android")]
#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct CredentialKeyRequest<'a> {
    key: &'a str,
}

#[cfg(target_os = "android")]
#[derive(Deserialize)]
#[serde(rename_all = "camelCase")]
struct CredentialGetResponse {
    value: Option<String>,
}

fn credential_account(key: &str) -> Result<String, String> {
    match key {
        TOKEN_KEY | REFRESH_TOKEN_KEY => Ok(format!("{KEY_PREFIX}.{key}")),
        _ => Err("unsupported credential key".to_string()),
    }
}

#[cfg(target_os = "android")]
pub fn init_android_secure_credentials() -> tauri::plugin::TauriPlugin<tauri::Wry> {
    tauri::plugin::Builder::new(ANDROID_PLUGIN_NAME)
        .setup(|app, api| {
            let handle =
                api.register_android_plugin("org.bklite.mobile", "SecureCredentialsPlugin")?;
            app.manage(AndroidSecureCredentials(handle));
            Ok(())
        })
        .build()
}

#[cfg(target_os = "android")]
#[command]
pub fn secure_credential_set(
    credentials: State<'_, AndroidSecureCredentials>,
    key: String,
    value: String,
) -> Result<(), String> {
    credential_account(&key)?;
    credentials
        .0
        .run_mobile_plugin::<()>(
            "secureCredentialSet",
            CredentialSetRequest {
                key: &key,
                value: &value,
            },
        )
        .map_err(|error| error.to_string())
}

#[cfg(not(target_os = "android"))]
#[command]
pub fn secure_credential_set(app: AppHandle, key: String, value: String) -> Result<(), String> {
    let account = credential_account(&key)?;
    app.keyring()
        .store
        .set_password(&account, &value)
        .map_err(|error| error.to_string())
}

#[cfg(target_os = "android")]
#[command]
pub fn secure_credential_get(
    credentials: State<'_, AndroidSecureCredentials>,
    key: String,
) -> Result<Option<String>, String> {
    credential_account(&key)?;
    credentials
        .0
        .run_mobile_plugin::<CredentialGetResponse>(
            "secureCredentialGet",
            CredentialKeyRequest { key: &key },
        )
        .map(|response| response.value)
        .map_err(|error| error.to_string())
}

#[cfg(not(target_os = "android"))]
#[command]
pub fn secure_credential_get(app: AppHandle, key: String) -> Result<Option<String>, String> {
    let account = credential_account(&key)?;
    app.keyring()
        .store
        .get_password(&account)
        .map_err(|error| error.to_string())
}

#[cfg(target_os = "android")]
#[command]
pub fn secure_credential_remove(
    credentials: State<'_, AndroidSecureCredentials>,
    key: String,
) -> Result<(), String> {
    credential_account(&key)?;
    credentials
        .0
        .run_mobile_plugin::<()>("secureCredentialRemove", CredentialKeyRequest { key: &key })
        .map_err(|error| error.to_string())
}

#[cfg(not(target_os = "android"))]
#[command]
pub fn secure_credential_remove(app: AppHandle, key: String) -> Result<(), String> {
    let account = credential_account(&key)?;
    app.keyring()
        .store
        .delete(&account)
        .map_err(|error| error.to_string())
}

#[cfg(test)]
mod tests {
    use super::credential_account;

    #[test]
    fn credential_accounts_only_accept_auth_tokens() {
        assert_eq!(
            credential_account("auth_token").as_deref(),
            Ok("mobile-auth.auth_token")
        );
        assert_eq!(
            credential_account("refresh_token").as_deref(),
            Ok("mobile-auth.refresh_token")
        );
        assert!(credential_account("user_info").is_err());
    }
}
