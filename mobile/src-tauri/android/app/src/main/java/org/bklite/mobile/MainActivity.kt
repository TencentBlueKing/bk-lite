package org.bklite.mobile

import android.os.Bundle
import android.view.View
import android.view.WindowManager
import androidx.activity.enableEdgeToEdge
import androidx.core.view.ViewCompat
import androidx.core.view.WindowInsetsCompat

class MainActivity : TauriActivity() {
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
  }
}