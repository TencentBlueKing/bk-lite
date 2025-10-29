#!/bin/bash
# 跨平台 Android 构建脚本
# 自动处理 MainActivity 复制和环境配置

set -e

# 解析参数
BUILD_TYPE="debug"
BUILD_TARGET="aarch64"
AUTO_INSTALL="false"

while [[ $# -gt 0 ]]; do
  case $1 in
    --release)
      BUILD_TYPE="release"
      shift
      ;;
    --all-targets)
      BUILD_TARGET="all"
      shift
      ;;
    --aab)
      BUILD_AAB="true"
      shift
      ;;
    --install)
      AUTO_INSTALL="true"
      shift
      ;;
    *)
      shift
      ;;
  esac
done

echo "📱 构建 Android APK ($BUILD_TYPE)"
echo ""

# 1. 构建 Next.js
pnpm run build

# 2. 加载环境变量（仅在 Unix 系统）
if [ -f ".android-env.sh" ]; then
  source .android-env.sh
fi

# 3. 初始化 Android 项目（如果不存在）
if [ ! -d "src-tauri/gen/android" ]; then
  echo ""
  echo "⚙️  初始化 Android 项目..."
  pnpm tauri android init
fi

# 4. 复制自定义 MainActivity（核心修复）
CUSTOM_MAIN="src-tauri/android/app/src/main/java/org/bklite/mobile/MainActivity.kt"
TARGET_MAIN="src-tauri/gen/android/app/src/main/java/org/bklite/mobile/MainActivity.kt"

if [ -f "$CUSTOM_MAIN" ]; then
  mkdir -p "$(dirname "$TARGET_MAIN")"
  cp "$CUSTOM_MAIN" "$TARGET_MAIN"
  echo "✅ MainActivity 已更新"
fi

# 5. 构建 APK
if [ "$BUILD_AAB" == "true" ]; then
  # 构建 AAB
  pnpm tauri android build --aab
elif [ "$BUILD_TYPE" == "release" ]; then
  if [ "$BUILD_TARGET" == "all" ]; then
    pnpm tauri android build
  else
    pnpm tauri android build --target "$BUILD_TARGET"
  fi
else
  # Debug 构建
  if [ "$BUILD_TARGET" == "all" ]; then
    pnpm tauri android build --debug
  else
    pnpm tauri android build --debug --target "$BUILD_TARGET"
  fi
fi

echo ""
echo "✅ 构建完成！"
if [ "$BUILD_AAB" == "true" ]; then
  echo "📦 AAB 位置: src-tauri/gen/android/app/build/outputs/bundle/"
else
  echo "📦 APK 位置: src-tauri/gen/android/app/build/outputs/apk/"
fi

# 6. 自动安装（如果指定了 --install 参数）
if [ "$AUTO_INSTALL" == "true" ] && [ "$BUILD_AAB" != "true" ]; then
  echo ""
  echo "📲 开始安装到设备..."
  
  # 确定 APK 路径
  if [ "$BUILD_TYPE" == "release" ]; then
    APK_DIR="src-tauri/gen/android/app/build/outputs/apk/universal/release"
    APK_NAME="app-universal-release.apk"
  else
    APK_DIR="src-tauri/gen/android/app/build/outputs/apk/universal/debug"
    APK_NAME="app-universal-debug.apk"
  fi
  
  APK_PATH="$APK_DIR/$APK_NAME"
  
  if [ -f "$APK_PATH" ]; then
    # 检查设备连接
    if adb devices | grep -q "device$"; then
      echo "🔌 检测到设备，开始安装..."
      adb install -r "$APK_PATH"
      
      if [ $? -eq 0 ]; then
        echo ""
        echo "✅ 安装成功！"
        echo "🚀 启动应用: adb shell am start -n org.bklite.mobile/.MainActivity"
        
        # 询问是否启动
        read -p "是否立即启动应用？(y/n) " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
          adb shell am start -n org.bklite.mobile/.MainActivity
          echo "✅ 应用已启动！"
        fi
      else
        echo "❌ 安装失败"
        exit 1
      fi
    else
      echo "❌ 未检测到设备，请确保:"
      echo "   1. 设备已通过 USB 连接或网络连接"
      echo "   2. 已开启 USB 调试"
      echo "   3. 已授权调试权限"
      echo ""
      echo "💡 可以手动安装: adb install -r $APK_PATH"
    fi
  else
    echo "❌ APK 文件不存在: $APK_PATH"
    exit 1
  fi
elif [ "$AUTO_INSTALL" == "true" ] && [ "$BUILD_AAB" == "true" ]; then
  echo ""
  echo "⚠️  AAB 文件无法直接安装，需要上传到 Google Play 或使用 bundletool 转换"
fi
