<p align="center"><img src="assets/tome-logo-v1.png" width="140" alt="Logo"></p>

# DBD 古书任务追踪器

作者 **Lohick** · Windows 桌面工具 · MIT 开源

识别《黎明杀机》古书任务，将名称、详情和进度显示在磨砂悬浮窗中。非官方玩家工具，与游戏官方无关联。

## 功能
- 快捷键冻结画面，框选任务卡并识别中文文字及数字进度。
- 固定右侧区域追踪局内分数或百分比提示。
- 可编辑任务，停止输入约 0.5 秒后自动保存。
- 快捷键直接按键录入，支持单键或组合键，Esc 取消。
- 悬浮窗支持透明度、拖动、锁定、关闭及重新显示。
- 保存任务、快捷键、阵营和透明度；不保存窗口位置。

## 源码运行
建议 Windows 11 x64、Python 3.12。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe run_tome_tracker.py
```

首次运行需要联网下载中文 OCR 模型，之后在本地识别。可从 [Releases](https://github.com/Xiazhi-Shought/DBD-Tome-Tracker/releases/latest) 下载 Windows 完整运行包，解压后双击 EXE 即可使用。

## 使用教程

### 1. 下载并打开

前往 [最新版下载](https://github.com/Xiazhi-Shought/DBD-Tome-Tracker/releases/latest)，下载 `win64.zip`。
完整解压后双击 `DBD-Tome-Tracker.exe`，不要删除 `_internal` 文件夹。第一次打开请等待中文 OCR 模型准备完成。

### 2. 识别任务卡

在游戏古书页面，把鼠标停在任务上，让详情显示出来。按默认 **Ctrl+Shift+T** 冻结画面，框选包含 **任务名称、任务详情、进度数字** 的区域，再按回车或双击确认。

例如任务详情显示 `工程师协会`、`与其他逃生者协同修理累计10台发电机`、`2/10`，应把这些文字一起框进去，不必单独框选进度条。

### 3. 检查识别结果

识别后会直接显示悬浮窗。若文字或数字有误，可在主界面修改任务名称、详情、当前进度和目标进度；停止输入约 **0.5 秒自动保存**。

### 4. 开始局内追踪

点击 **③ 开始自动追踪**。局内右侧出现任务进度提示时，软件读取提示中的数字并更新悬浮窗；提示消失后保留上次进度。

> **② 使用固定右侧任务进度区域是什么？**
>
> 它把监控区域设置为主显示器右侧预设位置，不是识别任务详情，也不会单独启动追踪。它读取的是带任务名称和进度的提示卡，不是右上角“修理 / MAX”等得分提示。
>
> **通常可以跳过这个按钮**：点击“③ 开始自动追踪”时，程序已经自动执行相同的区域设置。该按钮目前主要用于手动重设并查看区域坐标；它不是自动寻找或校准提示框。
>
> 游戏窗口位置、主显示器或 HUD 缩放变化后，提示卡可能落在预设区域之外。重复点击②也不会自动适配这种偏移。

### 5. 调整与关闭

- **改快捷键**：点击“更改快捷键”，按下并松开新按键即保存，Esc 取消。
- **移动悬浮窗**：在未锁定时拖动，点击锁按钮固定位置。
- **调整透明度**：拖动主界面的透明度滑块。
- **关闭悬浮窗**：点击右下角 `×`，主界面“显示悬浮窗”可以恢复。
- **停止识别**：点击“停止自动追踪”；关闭悬浮窗本身不会停止后台追踪。
- **下次打开**：恢复任务及保存的设置；需手动开始追踪，不保存悬浮窗位置。

## 已知限制
固定区域按主显示器比例定位，游戏窗口位置、HUD 缩放和分辨率变化可能影响识别。百分比与任务数量的换算可能是近似值。OCR 结果需核对。磨砂效果依赖 Windows 桌面合成。建议仅运行一个实例，避免快捷键或任务文件冲突。

## 配置
为兼容旧版本，数据保留在 `%LOCALAPPDATA%\DeskTranslate\dbd-tome-tracker`，`config.json` 存设置，`active-task.json` 存任务。OCR 模型在同级 `models` 目录。`DESKTRANSLATE_DATA_DIR` 可覆盖数据根目录。

本仓库不包含个人配置或用户截图；软件通过屏幕图像识别，不读取游戏进程内存。

## 测试
```powershell
python -m unittest tests.test_tome tests.test_tome_service
python tools/test_task_autosave.py
```

## 构建 EXE
```powershell
python -m pip install pyinstaller==6.22.3
python tools/build.py
```
生成 `dist/DBD-Tome-Tracker/DBD-Tome-Tracker.exe`。须保留整个文件夹。当前构建未签名；新电脑可能需下载 OCR 模型。

## 许可证与致谢
[MIT License](LICENSE)。原创新增和修改 © 2026 Lohick，保留 DeskTranslate contributors 上游声明。

基于 [DeskTranslate](https://github.com/DeskTranslate/DeskTranslate) 截图、OCR 基础组件。PySide6、RapidOCR、ONNX Runtime 等依赖遵循各自许可证。界面参考 Fluent 风格，未分发 FluentFlyout 源码。游戏名称与商标归各自权利人所有。

欢迎通过 Issues 反馈或 Pull Request 贡献，详见 [贡献指南](CONTRIBUTING.md)。
