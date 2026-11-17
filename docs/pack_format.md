# 同步素材包结构与重建

`demo_pack/` 是一个自包含、可被多机预监**直接加载**的示范工程包，纯标准库
即可解码。它由 `tools/make_synced_media.py` 一次性生成，重建方式：

```bash
python3 tools/make_synced_media.py demo_pack     # 可传第二个参数覆盖随机种子
```

## 目录结构

```
demo_pack/
  project.json            # 工程配置（严格加载，缺字段即报错）
  sources.json            # 来源与参数：生成器、种子、Python 版本、每机位参数
  truth/
    events.json           # 主时间线上的共同事件（时刻、颜色）
    ground_truth.json     # 审计时刻 × 策略下每机位的期望选帧（真值预言机）
  cameras/<cam>/
    camera.json           # fps、偏移、时间基、逐帧记录、缺段区间、非等距标记
    frames/f_00000.png    # 每个“真实存在”的帧一个 PNG（缺段即无文件/无记录）
    audio.wav             # 该机位独立的正弦监听声（s16le 单声道）
  exports/
    verify/               # 核验执行证据：verdict.json、evidence.md、证据图
    run1/                 # 离线合成导出：comp_*.png、composite.gif、报告
  runtime/                # 运行期音频缓存（不入库，见 .gitignore）
```

## 素材条件（覆盖题目要求的各种情况）

| 机位 | 帧率 | 起点偏移 | 帧间距 | 缺段（主时间线） | 帧数 |
|---|---|---|---|---|---|
| camA | 30 fps | 0.0 | 等距 | 无（基准机位） | 348 |
| camB | 25 fps | +0.35s | 等距 | 5.0–6.8s（盖住共同事件 E3） | 227 |
| camC | 24 fps | −0.8s | **非等距**（drift 1.012 + jitter 0.004） | 7.4–7.9s | 254 |
| camD | 15 fps | +1.2s | 等距 | 迟到 1.2s、早退 9.5s；3.1–3.9s 缺段 | 113 |

- **多帧率**：30 / 25 / 24 / 15 fps 共存；
- **起点偏移**：含负偏移（camC，主时间线起点时它已在录制）与正偏移
  （camB/camD，主时间线开始后才出现，对应 NOT_STARTED）；
- **非等距帧**：camC 每帧时间由漂移系数与确定性抖动产生，相邻帧间隔不固定；
- **机位缺段**：缺段通过“帧记录缺失”表达，解码器在该呈现时间根本没有帧，
  内核据此报告 GAP（离线预载）或 STALLED（实时有界等待），而非伪造黑场；
- **共同事件**：主时间线 T = 2.0 / 4.0 / 6.0 / 8.2 / 10.5s 各有一次打板
  （E1–E5），事件窗口 0.25s，落在窗口内的帧烧录事件 id 与专属颜色色带。

## 来源与参数留存

`sources.json` 记录生成器脚本名、随机种子（默认 `20261117`，LCG 确定性
随机）、Python 版本、`third_party=[]`（无第三方依赖），以及每个机位的
fps / offset / drift / jitter / 覆盖区间 / 缺段 / 背景色 / 音频频率。
每个 `camera.json` 也独立留存该机位的时间基、漂移、抖动与缺段区间，因此
重建结果可复现、可审计。

## 真值与重建结果的约定

`truth/ground_truth.json` 由生成脚本内的预言机 `build_truth` 产出，其 GAP
判定规则与内核 `Kernel._pick_one` 完全一致。重建后运行
`tools/verify_sync.py` 必须得到 `verdict.ok = true`（当前 384/384 通过），
否则说明重建结果不符合约定。
