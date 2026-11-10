# 文件与运行说明

工具：scripts/cull_review.py；Python 3.9+，仅依赖 Pillow。先检查当前环境是否已有；没有时在用户同意的软件环境安装 `python -m pip install Pillow`，不要求外部AI API或账号。Windows命令可用 `py -3`，macOS/Linux常用 `python3`，以本机实际为准。

## 1. 建立工程

```text
python3 scripts/cull_review.py prepare --source 原片目录 --output 新工程目录
```

输入与输出不能互为父子，也不能相同；工程输出必须不存在。只读输入，递归处理JPEG/PNG/WebP/TIFF；RAW、HEIC和其他不支持文件列入未处理清单，不判坏片。符号链接跳过。预览按EXIF旋正，转换为JPEG，不携带EXIF；原图不变。跨设备时间偏差不自动校正，顺序必须结合画面复核。

生成 manifest.json、预览、联系表、review.html 和 decisions-template.json。联系表用编号/ID对照清单，网页始终显示原文件名。中文文件名完整保留在清单和网页。预览是缩小图，不能单靠它判断原片细节。脚本不自动提名任何照片。

## 2. AI完成视觉判断后回写

读取联系表并核对原图，按 decisions-template.json 的数组字段填写 id、status、reason、group。status 为 unreviewed / priority / candidate / defer / exclude。group 是场景或动作段，不需真实人物名。缺少条目保持原状态；未知ID、非法字段或重复ID报错，不能默默丢失。

```text
python3 scripts/cull_review.py review --project 工程目录 --decisions 本轮决定.json
```

保存更新前的清单和网页快照，沿用项目ID和用户勾选存储键。不会自动复制照片。需要原片局部时：

```text
python3 scripts/cull_review.py detail --project 工程目录 --source 原片目录 --id 文件ID --box 0.1 0.1 0.5 0.5
```

box为EXIF旋正后的归一化左、上、宽、高。需先视觉核实目标区域，不做人脸识别。输出不放大小原片，长边最多1600px，并在重新生成的网页显示局部+全图。使用100%源文件检查精细锐度，网页大预览仅辅助比较。

## 3. 保存初筛或用户明确选择

```text
python3 scripts/cull_review.py copy --project 工程目录 --source 原片目录 --output 新副本目录 --scope candidates
python3 scripts/cull_review.py copy --project 工程目录 --source 原片目录 --output 新副本目录 --scope selected --selection 选片名单.json
```

candidates把priority复制到优先看，其余candidate进其他候选；两者互斥。selected只取本次JSON中明确勾选项，进用户选择，不自动称最终精选。工具仅复制JPEG，其他格式明确写入跳过报告；要其他格式或RAW由AI另按授权处理，不能把此工具输出称为全部格式均完成。

输出必须是新目录，保留相对子目录避免同名冲突；拒绝源或工程范围内及其父级输出。所有待复制源文件先核对相对路径和SHA-256，再创建副本。独立复制，不用硬链接；复制后哈希核验，并保存copy-report.json。失败保留已生成部分和报告以便核查，不声称全量成功。XMP不自动复制或修改，配对关系可在原目录查阅。

## 续作

这是保守的新目录工具，不提供原地增量覆盖。用户要增量补选时AI先扫描已有两候选目录，只对明确缺失项复制并逐个校验，保护已改文件；也可以新建本轮完整选择目录。不要删除旧目录后重跑以绕过保护。

RAW预览：本工具不解码RAW。可使用用户已有软件导出对应JPEG供审核，但最终匹配须核原文件与同目录关系，不能只凭尾号。未解析项单列，未完成全格式查看就如实说明。
