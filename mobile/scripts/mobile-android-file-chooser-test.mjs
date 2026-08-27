import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';


const projectRoot = new URL('../', import.meta.url);


async function readProjectFile(path) {
  return readFile(new URL(path, projectRoot), 'utf8');
}


test('Android WebChromeClient 同时保留麦克风和文件选择生命周期', async () => {
  const activity = await readProjectFile(
    'src-tauri/android/app/src/main/java/org/bklite/mobile/MainActivity.kt',
  );

  assert.match(activity, /override fun onPermissionRequest\(/);
  assert.match(activity, /pendingWebPermissionRequest\?\.deny\(\)/);
  assert.match(activity, /grant\(AUDIO_CAPTURE_RESOURCES\)/);
  assert.match(activity, /override fun onPermissionRequestCanceled\(/);
  assert.match(activity, /override fun onShowFileChooser\(/);
  assert.match(activity, /ActivityResultContracts\.StartActivityForResult\(\)/);
  assert.match(activity, /fileChooserParams\.createIntent\(\)/);
  assert.match(activity, /MODE_OPEN_MULTIPLE/);
  assert.match(activity, /Intent\.EXTRA_ALLOW_MULTIPLE/);
  assert.match(activity, /fileChooserParams\.isCaptureEnabled/);
  assert.match(activity, /MediaStore\.ACTION_IMAGE_CAPTURE/);
  assert.match(activity, /MediaStore\.ACTION_VIDEO_CAPTURE/);
  assert.match(activity, /MediaStore\.EXTRA_OUTPUT/);
  assert.match(activity, /FileProvider\.getUriForFile/);
  assert.match(activity, /pendingCaptureFile = imageFile[\s\S]*FileProvider\.getUriForFile/);
  assert.match(activity, /cacheDir/);
  assert.match(activity, /pendingCaptureFile\?\.delete\(\)/);
  assert.match(activity, /retainedCaptureFiles\.forEach\(File::delete\)/);
  assert.match(activity, /file\.name\.startsWith\("bk_lite_capture_"\)/);
  assert.match(activity, /result\.data\?\.clipData/);
  assert.match(activity, /val selectedUris: Array<Uri\?>\?/);
  assert.match(activity, /arrayOfNulls<Uri>\(clipData\.itemCount\)/);
  assert.match(activity, /FileChooserParams\.parseResult/);
  assert.match(activity, /if \(pendingFilePathCallback != null\)[\s\S]*filePathCallback\.onReceiveValue\(null\)[\s\S]*return true/);
  assert.match(activity, /return true[\s\S]*pendingFilePathCallback = filePathCallback/);
  assert.match(activity, /override fun onDestroy\(\)[\s\S]*cancelPendingFileChooser\(\)/);
});


test('四个生产文件入口仍覆盖相机、相册、普通文件和动态表单', async () => {
  const [customInput, applicationForm] = await Promise.all([
    readProjectFile('src/app/conversation/components/custom-input.tsx'),
    readProjectFile('src/app/conversation/components/custom-components/application-form.tsx'),
  ]);

  assert.match(customInput, /type="file"[\s\S]*accept="image\/\*"[\s\S]*capture="environment"/);
  assert.match(customInput, /ref=\{photoInputRef\}[\s\S]*type="file"[\s\S]*multiple/);
  assert.match(customInput, /ref=\{fileInputRef\}[\s\S]*type="file"[\s\S]*multiple/);
  assert.match(applicationForm, /type="file"/);
});
