# Photo Group Picker

本地照片分组与初筛工具：适用于数百张照片、每个场景连续拍摄多张的情况。原图不会被修改、移动或删除，照片不会上传。

## 运行

目标运行平台是 Windows 10/11，开发与测试可在 Linux 进行。程序没有 Linux 专用路径或 shell 依赖。

安装 Python 3.10+ 和 [uv](https://docs.astral.sh/uv/)，然后运行：

```bash
uv sync
uv run photo-group-picker /path/to/photos --output output
```

打开 `output/index.html` 查看每组照片和推荐结果，点击缩略图查看原图。结构化结果位于 `output/results.json`。支持 JPEG、PNG、WebP、TIFF 和 BMP；HEIC、相机 RAW 需要先转换。

### Windows / PowerShell

安装 uv（官方安装脚本），重新打开 PowerShell，进入项目目录：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
uv python install 3.10
uv sync --python 3.10
uv run photo-group-picker "D:\Photos\Trip" --output output
Start-Process .\output\index.html
```

也可以双击 `run-windows.cmd` 输入照片目录，或将照片文件夹拖到该脚本上。脚本使用 uv 安装依赖并运行，成功后打开报告。Windows 中的 Codex 可以在项目目录执行相同的 `uv run` 命令，并阅读 `results.json`；它不会因此自动获得视觉判断能力。

### Ubuntu 18 开发

系统默认 Python 3.6 不满足要求；请使用 Python 3.10。已限制 OpenCV 版本，以使用兼容较旧 glibc 的发行包。首次安装依赖需要联网，筛选本身离线运行。

```bash
uv run photo-group-picker /path/to/photos --threshold 0.65 --gap 300 --top 3
uv run python -m unittest discover -s tests -v
```

`--threshold` 越低，同场景照片越容易合并；`--gap` 限制相邻照片的 EXIF 拍摄时间间隔；`--top` 是每组每类推荐数量。默认每组分别推荐最多两张合影、两张未检测到人脸的照片。如果全部照片都有 EXIF 拍摄时间，则按时间排序，否则按路径排序。文件名应尽量反映拍摄顺序。

## 当前算法与限制

- 分组：默认使用感知哈希 + HSV 颜色直方图；可选 DINOv2 特征，并比较相邻照片和组内第一张照片，限制场景逐渐漂移。
- 质量：拉普拉斯方差估计清晰度，灰度分布估计曝光；这些是启发式指标，不是审美评分。
- 人像：OpenCV 正脸检测器估计人数与各个人脸清晰度。合影优先覆盖最多检测人脸，并考虑最不清晰的人脸；导入复核后，闭眼和不佳表情降低对应人脸分数。
- 人脸检测可能漏检侧脸、小脸或遮挡，把合影误判为风景；算法尚不能识别人物身份、闭眼、自然表情，也不能保证推荐照片中每个人表现最佳。噪点可能抬高清晰度评分。
- 报告是人工复核的候选集，可以修改场景编号和选片、人脸判断，导出并重新导入 JSON。基础检测器仍可能漏检；页面目前不能手动画出遗漏的人脸。

## 两阶段复核流程

1. 运行扫描，打开 `output/index.html`。将需要合并的照片设置为相同场景编号；要拆开的照片设置为新的场景编号。
2. 为合影中的同一个人填写相同人物编号（例如 `person-1`）。编号只在同一个场景内比较，不能直接按左右位置假定身份。
3. 记录睁眼/闭眼和表情，或让能够查看图片的 AI 根据 `output/AI_REVIEW.md` 完成判断。没有可靠判断时保留“未知”。可手动选中或排除照片。
4. 点击“导出复核文件”，把浏览器下载的 JSON 路径传给命令行。页面导入会更新编辑内容；评分、推荐和合成方案需要重新运行计算：

```powershell
uv run photo-group-picker "D:\Photos\Trip" --review "$env:USERPROFILE\Downloads\review.json" --output output
```

`results.json` 包含评分和坐标；坐标对应 `analyzed_size` 的 EXIF 校正后图像。`faces/` 保存从全尺寸原图裁剪的人脸，`sheets/` 保存场景联系表，`ai-tasks.json` 列出照片与人脸供本地 AI 查看，`review-template.json` 是可填写的复核模板。

`composite-plans.json` 在已标记同一人物且来源评分明显更好时提出替换方案，包含底图、目标人脸和来源人脸编号。它只是建议，不执行换脸；图像对齐、姿态检查和融合尚未实现。没有人物编号时不会猜测身份或生成替换方案。

页面修改只在当前内存中保存，关闭前需要导出。换到另一台电脑后应重新扫描照片并生成新的复核文件，因为文件包含当前电脑的绝对路径。

## RTX 4060 / DINOv2 场景分组

DINOv2-small 用于提取场景向量，不是聊天模型，也不负责判断表情。默认批次 8；显存不足时使用 `--batch-size 2`。已有其他本地大模型不代表 PyTorch 环境已安装或支持 CUDA。

Windows PowerShell 中先安装基础环境，再单独安装 GPU 依赖（首次需要联网）：

```powershell
uv sync --python 3.10
uv pip install "torch>=2.7,<3" --index-url https://download.pytorch.org/whl/cu128
uv pip install -r requirements-ml.txt
uv run --no-sync python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
uv run --no-sync photo-group-picker "D:\Photos\Trip" --backend dinov2 --device cuda --batch-size 8 --output output
```

CUDA 检查应输出 `True`。这里安装的是带 CUDA 12.8 运行库的 PyTorch，需要兼容的 NVIDIA 驱动；仅安装开发者套件不保证可用。安装命令可按 [PyTorch 官方选择器](https://pytorch.org/get-started/locally/) 调整，保留 Python 3.10 环境。GPU 模式使用 `--no-sync`，避免 uv 在常规同步时移除额外安装的模型依赖。

首次加载 `facebook/dinov2-small` 会下载模型。也可使用本地目录：

```powershell
uv run --no-sync photo-group-picker "D:\Photos\Trip" --backend dinov2 --model "D:\Models\dinov2-small" --offline --device cuda
```

模型目录需要匹配的配置、图像预处理配置及 safetensors 权重。DINOv2 默认相似度阈值为 `0.85`，需用实际照片校准；它仍然只比较拍摄顺序中相邻的候选，不会把相隔很久的同场景自动归到一起。

本地视觉模型目前通过任务文件参与复核，尚未接入自动 HTTP 调用。纯文本模型不能直接查看照片。处理这些文件与人脸裁剪时继续保持本地存储。

## 后续机器学习方案

1. **场景聚类**：用 DINOv2 或 CLIP 提取图像向量，结合时间窗口做聚类。对有人/无人、构图变化较大的同一场景更稳健，需要额外模型与校准。
2. **人物匹配**：用人脸检测与 embedding 对齐同组中的人物，维护每个人的评分；人脸向量涉及隐私，优先本地运行。
3. **闭眼与姿态**：MediaPipe Face Landmarker 提取眼部关键点，用眼睛纵横比辅助闭眼检测，用头部姿态与遮挡信息降低不合适照片的排名。微笑程度并不等于自然或好看。
4. **质量与审美**：接入 MUSIQ、NIMA 等模型评估画质和审美，实际旅游照片仍需要验证模型偏好。
5. **视觉大模型复核**：对每组少量候选图以及人脸裁剪进行比较，输出具体原因。适合表情判断，但可能漏看小脸或作出错误判断；上传照片需明确授权。

最终评分宜结合每个人的最低分与平均分，并保留几张互补候选。当所有照片都有人闭眼时，单张选择无法解决，需要人工决定是否接受或另做合成；本项目目前不合成人脸。

## 项目结构

`src/photo_group_picker/cli.py` 实现扫描、分组与评分，`embeddings.py` 提供可选 DINOv2 特征，`review.py` 校验复核文件并生成合成建议，`report.py` 与 `report.html` 生成本地交互报告。`tests/` 保存合成数据测试。私有照片放在被忽略的 `photos/` 或仓库外；输出目录默认也被忽略。
