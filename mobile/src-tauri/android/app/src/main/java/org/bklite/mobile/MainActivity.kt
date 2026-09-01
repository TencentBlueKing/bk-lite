package org.bklite.mobile

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.provider.MediaStore
import android.util.Log
import android.view.View
import android.view.WindowManager
import android.webkit.PermissionRequest
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebView
import androidx.activity.enableEdgeToEdge
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat
import androidx.activity.result.contract.ActivityResultContracts
import androidx.core.content.ContextCompat
import androidx.core.content.FileProvider
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

class MainActivity : TauriActivity() {
  companion object {
    private const val TAG = "BKLiteMainActivity"
    private val AUDIO_CAPTURE_RESOURCES = arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE)
  }

  private var pendingWebPermissionRequest: PermissionRequest? = null
  private var pendingFilePathCallback: ValueCallback<Array<Uri?>?>? = null
  private var pendingCaptureUri: Uri? = null
  private var pendingCaptureFile: File? = null
  private val retainedCaptureFiles = mutableSetOf<File>()

  private val requestPermissionLauncher = registerForActivityResult(
    ActivityResultContracts.RequestPermission()
  ) { isGranted: Boolean ->
    if (isGranted) {
      pendingWebPermissionRequest?.grant(AUDIO_CAPTURE_RESOURCES)
    } else {
      pendingWebPermissionRequest?.deny()
    }
    pendingWebPermissionRequest = null
  }

  private val fileChooserLauncher = registerForActivityResult(
    ActivityResultContracts.StartActivityForResult()
  ) { result ->
    val callback = pendingFilePathCallback
    pendingFilePathCallback = null
    val captureFile = pendingCaptureFile

    val selectedUris: Array<Uri?>? = when {
      result.resultCode != Activity.RESULT_OK -> null
      pendingCaptureUri != null && result.data?.data == null -> {
        arrayOf(pendingCaptureUri)
      }
      result.data?.clipData != null -> {
        val clipData = result.data!!.clipData!!
        arrayOfNulls<Uri>(clipData.itemCount).apply {
          for (index in indices) {
            this[index] = clipData.getItemAt(index).uri
          }
        }
      }
      else -> WebChromeClient.FileChooserParams.parseResult(
        result.resultCode,
        result.data,
      )
    }

    if (selectedUris?.contains(pendingCaptureUri) == true) {
      captureFile?.let(retainedCaptureFiles::add)
    } else {
      captureFile?.delete()
    }
    pendingCaptureUri = null
    pendingCaptureFile = null
    callback?.onReceiveValue(selectedUris)
  }

  override fun onCreate(savedInstanceState: Bundle?) {
    // 启用边缘到边缘显示
    enableEdgeToEdge()
    super.onCreate(savedInstanceState)

    cacheDir.listFiles { file -> file.name.startsWith("bk_lite_capture_") }
      ?.forEach(File::delete)
    
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

    setupWebViewPermissions()
  }

  private fun setupWebViewPermissions() {
    runOnUiThread {
      try {
        val webView = getWebView()
        webView?.webChromeClient = object : WebChromeClient() {
          override fun onPermissionRequest(request: PermissionRequest) {
            if (request.resources.contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) {
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
              super.onPermissionRequest(request)
            }
          }

          override fun onPermissionRequestCanceled(request: PermissionRequest) {
            if (pendingWebPermissionRequest === request) {
              pendingWebPermissionRequest = null
            }
            super.onPermissionRequestCanceled(request)
          }

          override fun onShowFileChooser(
            webView: WebView,
            filePathCallback: ValueCallback<Array<Uri?>?>,
            fileChooserParams: FileChooserParams,
          ): Boolean {
            if (pendingFilePathCallback != null) {
              filePathCallback.onReceiveValue(null)
              return true
            }
            pendingFilePathCallback = filePathCallback

            val acceptTypes = fileChooserParams.acceptTypes
            val captureIntent = when {
              !fileChooserParams.isCaptureEnabled -> null
              acceptTypes.any { it.startsWith("image/") } -> createImageCaptureIntent()
              acceptTypes.any { it.startsWith("video/") } -> {
                Intent(MediaStore.ACTION_VIDEO_CAPTURE)
              }
              else -> null
            }

            return launchFileChooser(captureIntent, fileChooserParams)
          }
        }
      } catch (error: Exception) {
        Log.e(TAG, "Unable to configure WebView permissions", error)
      }
    }
  }

  private fun launchFileChooser(
    captureIntent: Intent?,
    fileChooserParams: WebChromeClient.FileChooserParams,
  ): Boolean {
    return try {
      val intent = if (
        captureIntent != null && captureIntent.resolveActivity(packageManager) != null
      ) {
        captureIntent
      } else {
        discardPendingCapture()
        fileChooserParams.createIntent().apply {
          if (fileChooserParams.mode == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE) {
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
          }
        }
      }
      fileChooserLauncher.launch(intent)
      true
    } catch (error: Exception) {
      Log.e(TAG, "Unable to launch Android file chooser", error)
      cancelPendingFileChooser()
      true
    }
  }

  private fun createImageCaptureIntent(): Intent? {
    return try {
      val timestamp = SimpleDateFormat("yyyyMMdd_HHmmss", Locale.US).format(Date())
      val imageFile = File.createTempFile(
        "bk_lite_capture_${timestamp}_",
        ".jpg",
        cacheDir,
      )
      pendingCaptureFile = imageFile
      val imageUri = FileProvider.getUriForFile(
        this,
        "${packageName}.fileprovider",
        imageFile,
      )
      pendingCaptureUri = imageUri

      Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply {
        putExtra(MediaStore.EXTRA_OUTPUT, imageUri)
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
        addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
      }
    } catch (error: Exception) {
      Log.e(TAG, "Unable to prepare Android image capture", error)
      discardPendingCapture()
      null
    }
  }

  private fun discardPendingCapture() {
    pendingCaptureFile?.delete()
    pendingCaptureFile = null
    pendingCaptureUri = null
  }

  private fun cancelPendingFileChooser() {
    pendingFilePathCallback?.onReceiveValue(null)
    pendingFilePathCallback = null
    discardPendingCapture()
  }

  private fun getWebView(): android.webkit.WebView? {
    return try {
      val webViewField = TauriActivity::class.java.getDeclaredField("appWebView")
      webViewField.isAccessible = true
      webViewField.get(this) as? android.webkit.WebView
    } catch (error: Exception) {
      Log.e(TAG, "Unable to access the Tauri WebView", error)
      null
    }
  }

  override fun onDestroy() {
    pendingWebPermissionRequest?.deny()
    pendingWebPermissionRequest = null
    cancelPendingFileChooser()
    retainedCaptureFiles.forEach(File::delete)
    retainedCaptureFiles.clear()
    super.onDestroy()
  }
}
