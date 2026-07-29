package org.bklite.mobile

import android.app.Activity
import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import app.tauri.annotation.Command
import app.tauri.annotation.InvokeArg
import app.tauri.annotation.TauriPlugin
import app.tauri.plugin.Invoke
import app.tauri.plugin.JSObject
import app.tauri.plugin.Plugin
import java.nio.charset.StandardCharsets
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import android.util.Base64

private const val SECURE_CREDENTIALS_PREFS = "bk_lite_secure_credentials"
private const val SECURE_CREDENTIALS_KEY_ALIAS = "bk_lite_mobile_auth_key_v1"
private const val ANDROID_KEYSTORE = "AndroidKeyStore"
private const val AES_GCM_TRANSFORMATION = "AES/GCM/NoPadding"
private const val GCM_TAG_BITS = 128

@InvokeArg
class SecureCredentialSetArgs {
  lateinit var key: String
  lateinit var value: String
}

@InvokeArg
class SecureCredentialKeyArgs {
  lateinit var key: String
}

@TauriPlugin
class SecureCredentialsPlugin(private val activity: Activity) : Plugin(activity) {
  private val storage = AndroidSecureCredentials(activity.applicationContext)

  @Command
  fun secureCredentialSet(invoke: Invoke) {
    try {
      val args = invoke.parseArgs(SecureCredentialSetArgs::class.java)
      storage.set(args.key, args.value)
      invoke.resolve()
    } catch (error: Exception) {
      invoke.reject(error.message ?: error.toString())
    }
  }

  @Command
  fun secureCredentialGet(invoke: Invoke) {
    try {
      val args = invoke.parseArgs(SecureCredentialKeyArgs::class.java)
      val result = JSObject()
      result.put("value", storage.get(args.key))
      invoke.resolve(result)
    } catch (error: Exception) {
      invoke.reject(error.message ?: error.toString())
    }
  }

  @Command
  fun secureCredentialRemove(invoke: Invoke) {
    try {
      val args = invoke.parseArgs(SecureCredentialKeyArgs::class.java)
      storage.remove(args.key)
      invoke.resolve()
    } catch (error: Exception) {
      invoke.reject(error.message ?: error.toString())
    }
  }
}

private class AndroidSecureCredentials(context: Context) {
  private val appContext = context.applicationContext
  private val preferences = appContext.getSharedPreferences(
    SECURE_CREDENTIALS_PREFS,
    Context.MODE_PRIVATE,
  )

  fun set(key: String, value: String) {
    validateCredentialKey(key)

    val cipher = Cipher.getInstance(AES_GCM_TRANSFORMATION)
    cipher.init(Cipher.ENCRYPT_MODE, getOrCreateSecretKey())
    val iv = cipher.iv
    cipher.updateAAD(key.toByteArray(StandardCharsets.UTF_8))
    val ciphertext = cipher.doFinal(value.toByteArray(StandardCharsets.UTF_8))

    val committed = preferences.edit()
      .putString(ciphertextPreferenceKey(key), encode(ciphertext))
      .putString(ivPreferenceKey(key), encode(iv))
      .commit()
    if (!committed) {
      throw IllegalStateException("failed to persist credential")
    }
  }

  fun get(key: String): String? {
    validateCredentialKey(key)

    val ciphertext = preferences.getString(ciphertextPreferenceKey(key), null) ?: return null
    val iv = preferences.getString(ivPreferenceKey(key), null) ?: return null

    val cipher = Cipher.getInstance(AES_GCM_TRANSFORMATION)
    cipher.init(
      Cipher.DECRYPT_MODE,
      getOrCreateSecretKey(),
      GCMParameterSpec(GCM_TAG_BITS, decode(iv)),
    )
    cipher.updateAAD(key.toByteArray(StandardCharsets.UTF_8))
    val plaintext = cipher.doFinal(decode(ciphertext))
    return String(plaintext, StandardCharsets.UTF_8)
  }

  fun remove(key: String) {
    validateCredentialKey(key)
    val committed = preferences.edit()
      .remove(ciphertextPreferenceKey(key))
      .remove(ivPreferenceKey(key))
      .commit()
    if (!committed) {
      throw IllegalStateException("failed to remove credential")
    }
  }

  private fun getOrCreateSecretKey(): SecretKey {
    val keyStore = KeyStore.getInstance(ANDROID_KEYSTORE)
    keyStore.load(null)
    val existingKey = keyStore.getKey(SECURE_CREDENTIALS_KEY_ALIAS, null)
    if (existingKey is SecretKey) {
      return existingKey
    }

    val keyGenerator = KeyGenerator.getInstance(
      KeyProperties.KEY_ALGORITHM_AES,
      ANDROID_KEYSTORE,
    )
    val keySpec = KeyGenParameterSpec.Builder(
      SECURE_CREDENTIALS_KEY_ALIAS,
      KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
    )
      .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
      .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
      .setKeySize(256)
      .setRandomizedEncryptionRequired(true)
      .build()

    keyGenerator.init(keySpec)
    return keyGenerator.generateKey()
  }

  private fun validateCredentialKey(key: String) {
    if (key != "auth_token" && key != "refresh_token") {
      throw IllegalArgumentException("unsupported credential key")
    }
  }

  private fun ciphertextPreferenceKey(key: String): String = "$key.ciphertext"

  private fun ivPreferenceKey(key: String): String = "$key.iv"

  private fun encode(value: ByteArray): String = Base64.encodeToString(value, Base64.NO_WRAP)

  private fun decode(value: String): ByteArray = Base64.decode(value, Base64.NO_WRAP)
}
