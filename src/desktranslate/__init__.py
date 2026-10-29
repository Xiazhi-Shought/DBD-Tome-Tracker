"""DBD 古书任务追踪器：截图识别与进度悬浮窗。"""

import os

# Apply process-local policy before native runtime import (including OCR spawn
# children). This never changes the user's persistent environment. ONNX uses
# this switch for its non-Windows telemetry provider; its API is disabled too.
os.environ["ORT_DISABLE_TELEMETRY"] = "1"

__version__ = "1.0.0"
