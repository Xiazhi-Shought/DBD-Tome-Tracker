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

首次运行需要联网下载中文 OCR 模型，之后在本地识别。暂未发布 Release。

## 使用
1. 在游戏中悬停显示任务详情。
2. 按默认 `Ctrl+Shift+T`，框选名称、详情和进度数字，回车或双击识别。
3. 在主界面检查并修改结果，修改自动保存。
4. 点击开始自动追踪，读取局内右侧任务进度提示。
5. 悬浮窗 `×` 仅关闭显示，主界面可重新显示；停止追踪需点击停止按钮。

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
