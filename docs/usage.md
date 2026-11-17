# 多机位同步预监 — 使用说明

本系统在**一条制作时间线 T（参考时钟）**上对齐多路不同帧率、不同起点偏移、
存在缺段的摄像机素材，并把每路“按呈现时间戳选中的帧”合成到同一预监画面。
全部功能仅依赖 Python 标准库即可运行（PNG/WAV/GIF 均为自带实现）；旧的 mp4
样例在安装了可选 PyAV 依赖时仍可使用。

## 1. 图形入口（主要使用方式）

图形界面是一个浏览器面板，由本地 HTTP 服务提供，支持**多终端同时连接**。
启动方式（命令行只负责拉起服务，不是播放窗口）：

```bash
python3 run_panel.py --pack demo_pack
# 可选参数：--host 127.0.0.1  --port 8765
```

启动后终端会打印入口地址，例如：

```
图形入口(浏览器) / graphical entry:  http://127.0.0.1:8765/
```

在任意浏览器打开该 URL 即可，多个浏览器/工位可同时访问同一个面板。

页面上的每个按钮、下拉框都通过 `POST /api/control` 调用真实的
`MultiCamApp.control` → 同步内核实现，没有任何写死的演示数据：

- **播放 / 暂停 / 跳转**：驱动参考时钟与全部解码线程；
- **参考时钟**：可在“virtual 虚拟钟”和任意机位时钟之间切换
  （由 `project.json` 的 `reference_options` 提供）；
- **取帧策略**：`nearest`（最近帧）/ `hold`（保持不晚于目标的最后一帧）；
- **有界等待、速度、停滞显示、慢解码模拟**：真实作用于内核；
- **音频监听**：一次只选一路，来自该机位自己的 WAV，不做混音；
- 预览区每 ~150ms 拉取一次真实合成 PNG（`/frame.png`），下方表格给出每路
  的状态、共同事件、目标/选中 pts、**取帧误差(ms)**、停滞与缺段计数。

界面能直接看到多路画面以及它们之间的**取帧差异**：不同帧率/偏移的机位在同一
T 下选中各自最近的帧，误差列与状态色（OK / STALLED / GAP / NOT_STARTED /
ENDED）实时反映差异。

## 2. 命令行（仅辅助）

命令行不承担“多窗口同时播放”这种验证方式，只用于构建素材、跑核验、
拉起面板服务、以及生成确定性离线导出：

```bash
# 重建同步素材包（源文件 + 时刻真值 + 工程配置 + 来源参数）
python3 tools/make_synced_media.py demo_pack

# 用真实内核 + 真实解码器对照真值核验，输出执行证据
python3 tools/verify_sync.py demo_pack

# 确定性离线合成导出（PNG 序列 + GIF + 逐帧取帧报告）
python3 run_panel.py --pack demo_pack \
        --render demo_pack/exports/run1 --duration 12 --fps 10

# 旧样例（stdlib 包后端，无第三方依赖）
python3 run_panel.py --config demo_stdlib.json --render /tmp/legacy --duration 6

# 旧 mp4 样例（需要可选 PyAV；未安装时会给出明确报错而非静默降级）
python3 run_panel.py --config demo.json
```

## 3. 离线导出与共同时间验证

“共同时间是否对齐”不靠同时开多个播放窗口目测，而是用同一制作时间 T 下的
**同事件画面对应**来核验：

- 素材帧内烧录了共同事件色带（CLAP-1…CLAP-5 / E1…E5）和 24 位帧号二进制条；
- `tools/verify_sync.py` 在 11 个审计时刻 × 2 种策略下运行真实内核，逐机位
  比对 状态 / 帧号 / 事件标签，并把合成图里烧录的帧号条**读回**核对；
- 共同事件证据图 `exports/verify/event_<id>.png` 要求所有正在录制的机位显示
  同一个事件 id；处于缺段的机位必须显示 GAP/STALLED 等真实状态，不能用黑场
  或默认值掩盖；
- 结论写入 `exports/verify/verdict.json` 与 `evidence.md`
  （当前为 **384 项检查全部通过**）。

## 4. 严格加载，不以默认值遮错

`multicam/package.py` 的 `load_project()` 为严格加载：缺少必填字段、机位路径
不存在、策略非法、参考时钟未知等情况会**直接抛出 ValueError**，而不是用默认
值顶替。界面的非法控制请求（如未知参考时钟）返回 HTTP 400 并带回错误信息。

## 5. 运行测试

```bash
python3 -m unittest discover -s tests -v
```

共 18 个后端无关测试，覆盖时间基、按 pts 选帧、跨帧率策略、有界等待、
缺段/非等距帧/迟到机位、音频、离线渲染与帧号读回、参考时钟控制、严格加载。
