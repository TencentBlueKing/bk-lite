package org.bklite.mobile

import android.Manifest
import android.content.pm.PackageManager
import android.os.Bundle
import android.util.Log
import android.view.View
import android.view.WindowManager
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

class MainActivity : TauriActivity() {
  companion object {
    private const val TAG = "BKLiteMainActivity"
    private val AUDIO_CAPTURE_RESOURCES = arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE)
  }

  private var pendingWebPermissionRequest: PermissionRequest? = null

  // 注册权限请求回调
  private val requestPermissionLauncher = registerForActivityResult(
    ActivityResultContracts.RequestPermission()
  ) { isGranted: Boolean ->
    if (isGranted) {
      pendingWebPermissionRequest?.grant(AUDIO_CAPTURE_RESOURCES)
    } else {
      // 权限被拒绝，拒绝 WebView 的权限请求
      pendingWebPermissionRequest?.deny()
    }
    pendingWebPermissionRequest = null
  }

  override fun onCreate(savedInstanceState: Bundle?) {
    // 启用边缘到边缘显示
    enableEdgeToEdge()
    super.onCreate(savedInstanceState)
    
    // 关键设置：确保键盘弹出时调整布局
    window.setSoftInputMode(WindowManager.LayoutParams.SOFT_INPUT_ADJUST_RESIZE)
    
    // 获取根视图
    val rootView = window.decorView.findViewById<View>(android.R.id.content)
    
    // 设置 WindowInsets 监听器
    ViewCompat.setOnApplyWindowInsetsListener(rootView) { view, insets ->
      // 获取系统栏和键盘的 insets
      val systemBars = insets.getInsets(WindowInsetsCompat.Type.systemBars())
      val ime = insets.getInsets(WindowInsetsCompat.Type.ime())
      
      // 计算底部 padding：键盘弹出时用键盘高度，否则用系统栏高度
      val bottomPadding = if (ime.bottom > 0) ime.bottom else systemBars.bottom
      
      // 应用 padding
      view.setPadding(0, systemBars.top, 0, bottomPadding)
      
      // 返回 CONSUMED 表示我们已经处理了这个 insets
      WindowInsetsCompat.CONSUMED
    }

    // 配置 WebView 以处理麦克风权限请求
    setupWebViewPermissions()
  }

  private fun setupWebViewPermissions() {
    // 获取 WebView 并设置 WebChromeClient 来处理权限请求
    runOnUiThread {
      try {
        val webView = getWebView()
        webView?.webChromeClient = object : WebChromeClient() {
          override fun onPermissionRequest(request: PermissionRequest) {
            // 检查是否是麦克风权限请求
            if (request.resources.contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) {
              // 检查是否已经有权限
              if (ContextCompat.checkSelfPermission(
                  this@MainActivity,
                  Manifest.permission.RECORD_AUDIO
              ) == PackageManager.PERMISSION_GRANTED
              ) {
                request.grant(AUDIO_CAPTURE_RESOURCES)
              } else {
                pendingWebPermissionRequest?.deny()
                pendingWebPermissionRequest = request
                requestPermissionLauncher.launch(Manifest.permission.RECORD_AUDIO)
              }
            } else {
              // 其他权限请求
              super.onPermissionRequest(request)
            }
          }

          override fun onPermissionRequestCanceled(request: PermissionRequest) {
            if (pendingWebPermissionRequest === request) {
              pendingWebPermissionRequest = null
            }
            super.onPermissionRequestCanceled(request)
          }
        }
      } catch (e: Exception) {
        Log.e(TAG, "Unable to configure WebView microphone permissions")
      }
    }
  }

  private fun getWebView(): android.webkit.WebView? {
    // Tauri 的 WebView 获取方法
    try {
      val webViewField = TauriActivity::class.java.getDeclaredField("appWebView")
      webViewField.isAccessible = true
      return webViewField.get(this) as? android.webkit.WebView
    } catch (e: Exception) {
      Log.e(TAG, "Unable to access the Tauri WebView")
      return null
    }
  }

  override fun onDestroy() {
    pendingWebPermissionRequest?.deny()
    pendingWebPermissionRequest = null
    super.onDestroy()
  }
}
