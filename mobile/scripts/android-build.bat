@echo off
REM 跨平台 Android 构建脚本 (Windows 版本)
REM 自动处理 MainActivity 复制和环境配置
setlocal enabledelayedexpansion

REM 解析参数
set "BUILD_TYPE=debug"
set "BUILD_TARGET=aarch64"
set "BUILD_AAB="
set "AUTO_INSTALL="

:parse_args
if "%~1"=="" goto end_parse
if "%~1"=="--release" set "BUILD_TYPE=release"
if "%~1"=="--all-targets" set "BUILD_TARGET=all"
if "%~1"=="--aab" set "BUILD_AAB=true"
if "%~1"=="--install" set "AUTO_INSTALL=true"
shift
goto parse_args
:end_parse

echo 📱 构建 Android APK (%BUILD_TYPE%)
echo.

REM 1. 加载环境变量（从 .android-env.sh 解析）
if exist ".android-env.sh" (
  for /f "usebackq tokens=1,2 delims== " %%a in (".android-env.sh") do (
    set line=%%a
    if "!line:~0,6!"=="export" (
      set "var=%%a"
      set "var=!var:export =!"
      set "val=%%b"
      REM 移除引号
      set "val=!val:"=!"
      set "!var!=!val!"
    )
  )
)

REM 2. 初始化 Android 项目（如果不存在）
if not exist "src-tauri\gen\android" (
  echo.
  echo ⚙️  初始化 Android 项目...
  call pnpm tauri android init
  if errorlevel 1 exit /b 1
)

REM 3. 复制自定义 Android 原生源（gen 目录会被重新生成）
set "CUSTOM_JAVA_SRC=src-tauri\android\app\src\main\java"
set "TARGET_JAVA_SRC=src-tauri\gen\android\app\src\main\java"

if exist "%CUSTOM_JAVA_SRC%" (
  if not exist "%TARGET_JAVA_SRC%" (
    mkdir "%TARGET_JAVA_SRC%"
  )
  if exist "%TARGET_JAVA_SRC%\io\crates\keyring" (
    rmdir /S /Q "%TARGET_JAVA_SRC%\io\crates\keyring"
  )
  xcopy /Y /E /I "%CUSTOM_JAVA_SRC%\*" "%TARGET_JAVA_SRC%\" >nul
  echo ✅ Android 原生源已更新
)

REM 4. 修正 Tauri Android 生成源的 Activity 初始化链路
node scripts\patch-android-generated-sources.mjs
if errorlevel 1 exit /b 1
echo ✅ Android Tauri 启动源已更新

REM 5. 固化权限、备份与软键盘配置（gen 目录会被重新生成）
node scripts\patch-android-manifest.mjs
if errorlevel 1 exit /b 1
echo ✅ Android 平台配置已更新

REM 6. 复制自定义 Android 图标
set "CUSTOM_ICONS=src-tauri\icons\android\res"
set "TARGET_RES=src-tauri\gen\android\app\src\main\res"

if exist "%CUSTOM_ICONS%" (
  echo.
  echo 📱 更新 Android 应用图标...
  xcopy /Y /E /I "%CUSTOM_ICONS%\*" "%TARGET_RES%\" >nul 2>&1
  if errorlevel 0 (
    echo ✅ Android 图标已更新
  )
)

REM 7. 构建 APK
if "%BUILD_AAB%"=="true" (
  call pnpm tauri android build --aab
) else if "%BUILD_TYPE%"=="release" (
  if "%BUILD_TARGET%"=="all" (
    call pnpm tauri android build
  ) else (
    call pnpm tauri android build --target %BUILD_TARGET%
  )
) else (
  if "%BUILD_TARGET%"=="all" (
    call pnpm tauri android build --debug
  ) else (
    call pnpm tauri android build --debug --target %BUILD_TARGET%
  )
)

if errorlevel 1 exit /b 1

echo.
echo ✅ 构建完成！
if "%BUILD_AAB%"=="true" (
  echo 📦 AAB 位置: src-tauri\gen\android\app\build\outputs\bundle\
) else (
  echo 📦 APK 位置: src-tauri\gen\android\app\build\outputs\apk\
)

REM 8. 自动安装（如果指定了 --install 参数）
if "%AUTO_INSTALL%"=="true" (
  if not "%BUILD_AAB%"=="true" (
    echo.
    echo 📲 开始安装到设备...
    
    REM 确定 APK 路径
    if "%BUILD_TYPE%"=="release" (
      set "APK_DIR=src-tauri\gen\android\app\build\outputs\apk\universal\release"
      set "APK_NAME=app-universal-release.apk"
    ) else (
      set "APK_DIR=src-tauri\gen\android\app\build\outputs\apk\universal\debug"
      set "APK_NAME=app-universal-debug.apk"
    )
    
    set "APK_PATH=!APK_DIR!\!APK_NAME!"
    
    if exist "!APK_PATH!" (
      REM 检查设备连接
      adb devices | findstr /C:"device" >nul
      if !errorlevel! equ 0 (
        echo 🔌 检测到设备，开始安装...
        adb install -r "!APK_PATH!"
        
        if !errorlevel! equ 0 (
          echo.
          echo ✅ 安装成功！
          echo 🚀 启动应用: adb shell am start -n org.bklite.mobile/.MainActivity
          
          set /p "LAUNCH=是否立即启动应用？(y/n) "
          if /i "!LAUNCH!"=="y" (
            adb shell am start -n org.bklite.mobile/.MainActivity
            echo ✅ 应用已启动！
          )
        ) else (
          echo ❌ 安装失败
          exit /b 1
        )
      ) else (
        echo ❌ 未检测到设备，请确保:
        echo    1. 设备已通过 USB 连接或网络连接
        echo    2. 已开启 USB 调试
        echo    3. 已授权调试权限
        echo.
        echo 💡 可以手动安装: adb install -r !APK_PATH!
      )
    ) else (
      echo ❌ APK 文件不存在: !APK_PATH!
      exit /b 1
    )
  ) else (
    echo.
    echo ⚠️  AAB 文件无法直接安装，需要上传到 Google Play 或使用 bundletool 转换
  )
)

endlocal
