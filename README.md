# 多机位同步预监（multi-camera sync preview）

按演示时间线 `T` 同步预监多路自制摄像机素材：内核只依据各流自己的
呈现时间戳（pts）取帧，画面合成到一张多宫格图，缺帧、停滞、缺段都显式
标注而不是悄悄丢弃。本目录的 `sync_demo/` 是一套含**非等距帧、起点偏移、
机位缺段和共同事件**的真实素材工程包，可直接被面板加载。

## 图形入口（主要使用方式）

启动面板（HTTP，多终端/多浏览器可同时连接）：

```bash
python3 run_panel.py
# 或直接预载同步示范工程
python3 run_panel.py --project sync_demo
```

打开打印的地址（默认 http://127.0.0.1:8765/ ），在页面顶部：

1. “预监工程包”下拉框会列出 `--package-roots`（默认当前目录）下所有含
   `project.json` 的工程；
2. 点“载入工程”，经严格加载器校验后，多路画面出现在预览区；
3. “参考时钟”可选择 `virtual` 虚拟钟或任意一路机位（跟随该路呈现位置）；
4. 播放后可在预览区同时看到多路画面，以及每路的目标 pts、选中 pts、
   取帧误差（ms）、停滞/缺段计数等取帧差异；
5. 缺段中的机位显示品红 `GAP` 徽章并保持缺段前末帧，误差栏对超过
   100ms 的取帧差异高亮。

面板上的每个按钮都调用 `multicam` 真实实现（`/api/control`、
`/api/load_project`），多路画面来自实际解码线程，没有固定占位数据。

## 命令行（仅辅助）

命令行只用于离线导出与核验，不能替代面板的共同时间验证：

```bash
# 离线合成预监并导出 mp4 + 逐帧取帧报告
python3 run_panel.py --project sync_demo \
    --render out/sync_composite.mp4 --duration 14 --fps 10

# 独立核验：取帧、缺段状态、共同事件画面与 ground_truth 逐条比对
python3 tools/verify_sync.py sync_demo
```

## 重建同步素材

```bash
python3 tools/make_sync_media.py --out sync_demo
```

生成器是确定性的（固定随机种子），产出：

| 文件 | 内容 |
| --- | --- |
| `sync_demo/media/cam{A..D}.mp4` | 自制片段：帧号条、事件条、事件横幅、每路独立正弦音 |
| `sync_demo/ground_truth.json` | 每帧本地时刻、偏移、缺段、共同事件、构建参数与来源、文件 sha256 |
| `sync_demo/project.json` | 严格加载的预监工程配置（无默认值兜底） |

素材特性：

- **多帧率**：camA 30、camB 25、camC 24、camD 名义 20fps；每路都带
  亚帧抖动，camD 为真正的可变帧率（相邻间隔在 ~0.0275/~0.0725s 间交替）；
- **起点偏移**：四路偏移分别为 0、+0.8、-1.2、+1.5 秒；
- **机位缺段**：camB 在生产时间 5.9–7.4s 无帧，camC 在 3.1–4.6s 与
  9.2–10.6s 无帧，缺段区间内没有任何帧；
- **共同事件**：T=2/5/8/11s 四个事件，每个覆盖机位都把同一事件 id
  烧录进画面（绿色 6 位事件条 + 横幅），用于“同一事件画面”核验。

## 共同时间如何被验证（不是开多个窗口同时播）

`tools/verify_sync.py` 不相信预监自己的数字，而是从 `ground_truth.json`
独立计算期望值，再与真实合成产物比对：

1. 对每个生产时刻 `T`，独立计算每路最近帧、NOT_STARTED/ENDED 边界；
2. 落在缺段且取帧误差超阈值的时刻必须报 `GAP`；
3. 从渲染出的合成图里读回事件条，确认同一事件 id 出现在每个覆盖机位
   的格子里（画面级同步证据），并读回帧号条与真值帧表比对；
4. 校验 mp4 的 sha256 与生成时记录一致。

## 严格加载（不以默认值遮错）

`multicam/project.py` 的 `load_project` 会拒绝：未知 schema、缺必填键、
媒体文件不存在、非法缺段区间、未知参考时钟/音频源等。任何一项不符都抛
`ProjectError`，面板把错误回显到页面，而不是用默认配置顶替。

## 测试

```bash
python3 -m unittest discover -s tests
```

- `tests/test_kernel.py`：原有 14 项，覆盖时间基、B 帧解码序、跨帧率
  策略、早停、负偏移、有界等待、音频单选、合成读回（旧样例仍运行到底）；
- `tests/test_sync_package.py`：新增 16 项，覆盖非等距帧、缺段 GAP、
  严格加载器、共同事件画面、面板真实帧端点。
