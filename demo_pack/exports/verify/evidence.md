# 同步核验证据 / sync verification evidence

pack: `/workspace/demo_pack`
seed: `20261117`
result: **PASS** (384 passed, 0 failed)

## 共同事件画面对应 / shared-event correspondence

### E1 @ T=2.000s — `event_E1.png`

| 机位 | 状态 | 事件 | 帧号 | 误差ms |
|---|---|---|---|---|
| camA | OK | E1 | 60 | 0.0 |
| camB | OK | E1 | 41 | -10.002 |
| camC | OK | E1 | 66 | -15.633 |
| camD | OK | E1 | 12 | 0.0 |

### E2 @ T=4.000s — `event_E2.png`

| 机位 | 状态 | 事件 | 帧号 | 误差ms |
|---|---|---|---|---|
| camA | OK | E2 | 120 | 0.0 |
| camB | OK | E2 | 91 | -10.002 |
| camC | OK | E2 | 114 | 4.574 |
| camD | OK | E2 | 42 | 0.0 |

### E3 @ T=6.000s — `event_E3.png`

| 机位 | 状态 | 事件 | 帧号 | 误差ms |
|---|---|---|---|---|
| camA | OK | E3 | 180 | 0.0 |
| camB | OK | - | 162 | 829.997 |
| camC | OK | E3 | 161 | -7.568 |
| camD | OK | E3 | 72 | 0.0 |

### E4 @ T=8.200s — `event_E4.png`

| 机位 | 状态 | 事件 | 帧号 | 误差ms |
|---|---|---|---|---|
| camA | OK | E4 | 246 | 0.0 |
| camB | OK | E4 | 196 | -10.002 |
| camC | OK | E4 | 213 | -19.377 |
| camD | OK | E4 | 105 | 0.0 |

### E5 @ T=10.500s — `event_E5.png`

| 机位 | 状态 | 事件 | 帧号 | 误差ms |
|---|---|---|---|---|
| camA | OK | E5 | 315 | 0.0 |
| camB | OK | E5 | 254 | 10.002 |
| camC | OK | E5 | 268 | 2.889 |
| camD | ENDED | - | 124 | -1033.333 |

## 取帧差异 / frame-pick divergence (ms)

| T | policy | spread_ms | per-camera err_ms |
|---|---|---|---|
| 2.000 | nearest | 15.633 | {"camA": 0.0, "camB": -10.002, "camC": -15.633, "camD": 0.0} |
| 3.500 | nearest | 443.335 | {"camA": 0.0, "camB": 10.002, "camC": -1.408, "camD": -433.333} |
| 4.000 | nearest | 14.576 | {"camA": 0.0, "camB": -10.002, "camC": 4.574, "camD": 0.0} |
| 5.900 | nearest | 913.42 | {"camA": 0.0, "camB": -910.002, "camC": 3.418, "camD": -33.333} |
| 6.000 | nearest | 837.565 | {"camA": 0.0, "camB": 829.997, "camC": -7.568, "camD": 0.0} |
| 6.100 | nearest | 763.33 | {"camA": 0.0, "camB": 729.997, "camC": 17.806, "camD": -33.333} |
| 7.600 | nearest | 217.578 | {"camA": 0.0, "camB": -10.002, "camC": -217.578, "camD": 0.0} |
| 8.200 | nearest | 19.377 | {"camA": 0.0, "camB": -10.002, "camC": -19.377, "camD": 0.0} |
| 10.000 | nearest | 533.333 | {"camA": 0.0, "camB": -10.002, "camC": -1.652, "camD": -533.333} |
| 10.500 | nearest | 1043.335 | {"camA": 0.0, "camB": 10.002, "camC": 2.889, "camD": -1033.333} |
| 11.000 | nearest | 1541.626 | {"camA": 0.0, "camB": -10.002, "camC": 8.293, "camD": -1533.333} |
| 2.000 | hold | 15.633 | {"camA": 0.0, "camB": -10.002, "camC": -15.633, "camD": 0.0} |
| 3.500 | hold | 433.333 | {"camA": 0.0, "camB": -29.997, "camC": -1.408, "camD": -433.333} |
| 4.000 | hold | 32.007 | {"camA": 0.0, "camB": -10.002, "camC": -32.007, "camD": 0.0} |
| 5.900 | hold | 910.002 | {"camA": 0.0, "camB": -910.002, "camC": -37.907, "camD": -33.333} |
| 6.000 | hold | 1010.002 | {"camA": 0.0, "camB": -1010.002, "camC": -7.568, "camD": 0.0} |
| 6.100 | hold | 1110.002 | {"camA": 0.0, "camB": -1110.002, "camC": -26.31, "camD": -33.333} |
| 7.600 | hold | 217.578 | {"camA": 0.0, "camB": -10.002, "camC": -217.578, "camD": 0.0} |
| 8.200 | hold | 19.377 | {"camA": 0.0, "camB": -10.002, "camC": -19.377, "camD": 0.0} |
| 10.000 | hold | 533.333 | {"camA": 0.0, "camB": -10.002, "camC": -1.652, "camD": -533.333} |
| 10.500 | hold | 1033.333 | {"camA": 0.0, "camB": -29.997, "camC": -44.637, "camD": -1033.333} |
| 11.000 | hold | 1533.333 | {"camA": 0.0, "camB": -10.002, "camC": -35.148, "camD": -1533.333} |

## 检查明细 / checks

- [x] nearest T=2.000 camA state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=2.000 camA frame `{"expected": 60, "got": 60}`
- [x] nearest T=2.000 camA event tag `{"expected": "E1", "got": "E1"}`
- [x] nearest T=2.000 camA strip readback `{"picked": 60, "readback": 60}`
- [x] nearest T=2.000 camB state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=2.000 camB frame `{"expected": 41, "got": 41}`
- [x] nearest T=2.000 camB event tag `{"expected": "E1", "got": "E1"}`
- [x] nearest T=2.000 camB strip readback `{"picked": 41, "readback": 41}`
- [x] nearest T=2.000 camC state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=2.000 camC frame `{"expected": 66, "got": 66}`
- [x] nearest T=2.000 camC event tag `{"expected": "E1", "got": "E1"}`
- [x] nearest T=2.000 camC strip readback `{"picked": 66, "readback": 66}`
- [x] nearest T=2.000 camD state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=2.000 camD frame `{"expected": 12, "got": 12}`
- [x] nearest T=2.000 camD event tag `{"expected": "E1", "got": "E1"}`
- [x] nearest T=2.000 camD strip readback `{"picked": 12, "readback": 12}`
- [x] nearest T=3.500 camA state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=3.500 camA frame `{"expected": 105, "got": 105}`
- [x] nearest T=3.500 camA event tag `{"expected": null, "got": null}`
- [x] nearest T=3.500 camA strip readback `{"picked": 105, "readback": 105}`
- [x] nearest T=3.500 camB state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=3.500 camB frame `{"expected": 79, "got": 79}`
- [x] nearest T=3.500 camB event tag `{"expected": null, "got": null}`
- [x] nearest T=3.500 camB strip readback `{"picked": 79, "readback": 79}`
- [x] nearest T=3.500 camC state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=3.500 camC frame `{"expected": 102, "got": 102}`
- [x] nearest T=3.500 camC event tag `{"expected": null, "got": null}`
- [x] nearest T=3.500 camC strip readback `{"picked": 102, "readback": 102}`
- [x] nearest T=3.500 camD state `{"expected": "GAP", "got": "GAP"}`
- [x] nearest T=3.500 camD frame `{"expected": 28, "got": 28}`
- [x] nearest T=3.500 camD event tag `{"expected": null, "got": null}`
- [x] nearest T=3.500 camD strip readback `{"picked": 28, "readback": 28}`
- [x] nearest T=4.000 camA state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=4.000 camA frame `{"expected": 120, "got": 120}`
- [x] nearest T=4.000 camA event tag `{"expected": "E2", "got": "E2"}`
- [x] nearest T=4.000 camA strip readback `{"picked": 120, "readback": 120}`
- [x] nearest T=4.000 camB state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=4.000 camB frame `{"expected": 91, "got": 91}`
- [x] nearest T=4.000 camB event tag `{"expected": "E2", "got": "E2"}`
- [x] nearest T=4.000 camB strip readback `{"picked": 91, "readback": 91}`
- [x] nearest T=4.000 camC state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=4.000 camC frame `{"expected": 114, "got": 114}`
- [x] nearest T=4.000 camC event tag `{"expected": "E2", "got": "E2"}`
- [x] nearest T=4.000 camC strip readback `{"picked": 114, "readback": 114}`
- [x] nearest T=4.000 camD state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=4.000 camD frame `{"expected": 42, "got": 42}`
- [x] nearest T=4.000 camD event tag `{"expected": "E2", "got": "E2"}`
- [x] nearest T=4.000 camD strip readback `{"picked": 42, "readback": 42}`
- [x] nearest T=5.900 camA state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=5.900 camA frame `{"expected": 177, "got": 177}`
- [x] nearest T=5.900 camA event tag `{"expected": "E3", "got": "E3"}`
- [x] nearest T=5.900 camA strip readback `{"picked": 177, "readback": 177}`
- [x] nearest T=5.900 camB state `{"expected": "GAP", "got": "GAP"}`
- [x] nearest T=5.900 camB frame `{"expected": 116, "got": 116}`
- [x] nearest T=5.900 camB event tag `{"expected": null, "got": null}`
- [x] nearest T=5.900 camB strip readback `{"picked": 116, "readback": 116}`
- [x] nearest T=5.900 camC state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=5.900 camC frame `{"expected": 159, "got": 159}`
- [x] nearest T=5.900 camC event tag `{"expected": "E3", "got": "E3"}`
- [x] nearest T=5.900 camC strip readback `{"picked": 159, "readback": 159}`
- [x] nearest T=5.900 camD state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=5.900 camD frame `{"expected": 70, "got": 70}`
- [x] nearest T=5.900 camD event tag `{"expected": "E3", "got": "E3"}`
- [x] nearest T=5.900 camD strip readback `{"picked": 70, "readback": 70}`
- [x] nearest T=6.000 camA state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=6.000 camA frame `{"expected": 180, "got": 180}`
- [x] nearest T=6.000 camA event tag `{"expected": "E3", "got": "E3"}`
- [x] nearest T=6.000 camA strip readback `{"picked": 180, "readback": 180}`
- [x] nearest T=6.000 camB state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=6.000 camB frame `{"expected": 162, "got": 162}`
- [x] nearest T=6.000 camB event tag `{"expected": null, "got": null}`
- [x] nearest T=6.000 camB strip readback `{"picked": 162, "readback": 162}`
- [x] nearest T=6.000 camC state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=6.000 camC frame `{"expected": 161, "got": 161}`
- [x] nearest T=6.000 camC event tag `{"expected": "E3", "got": "E3"}`
- [x] nearest T=6.000 camC strip readback `{"picked": 161, "readback": 161}`
- [x] nearest T=6.000 camD state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=6.000 camD frame `{"expected": 72, "got": 72}`
- [x] nearest T=6.000 camD event tag `{"expected": "E3", "got": "E3"}`
- [x] nearest T=6.000 camD strip readback `{"picked": 72, "readback": 72}`
- [x] nearest T=6.100 camA state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=6.100 camA frame `{"expected": 183, "got": 183}`
- [x] nearest T=6.100 camA event tag `{"expected": "E3", "got": "E3"}`
- [x] nearest T=6.100 camA strip readback `{"picked": 183, "readback": 183}`
- [x] nearest T=6.100 camB state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=6.100 camB frame `{"expected": 162, "got": 162}`
- [x] nearest T=6.100 camB event tag `{"expected": null, "got": null}`
- [x] nearest T=6.100 camB strip readback `{"picked": 162, "readback": 162}`
- [x] nearest T=6.100 camC state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=6.100 camC frame `{"expected": 164, "got": 164}`
- [x] nearest T=6.100 camC event tag `{"expected": "E3", "got": "E3"}`
- [x] nearest T=6.100 camC strip readback `{"picked": 164, "readback": 164}`
- [x] nearest T=6.100 camD state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=6.100 camD frame `{"expected": 73, "got": 73}`
- [x] nearest T=6.100 camD event tag `{"expected": "E3", "got": "E3"}`
- [x] nearest T=6.100 camD strip readback `{"picked": 73, "readback": 73}`
- [x] nearest T=7.600 camA state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=7.600 camA frame `{"expected": 228, "got": 228}`
- [x] nearest T=7.600 camA event tag `{"expected": null, "got": null}`
- [x] nearest T=7.600 camA strip readback `{"picked": 228, "readback": 228}`
- [x] nearest T=7.600 camB state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=7.600 camB frame `{"expected": 181, "got": 181}`
- [x] nearest T=7.600 camB event tag `{"expected": null, "got": null}`
- [x] nearest T=7.600 camB strip readback `{"picked": 181, "readback": 181}`
- [x] nearest T=7.600 camC state `{"expected": "GAP", "got": "GAP"}`
- [x] nearest T=7.600 camC frame `{"expected": 194, "got": 194}`
- [x] nearest T=7.600 camC event tag `{"expected": null, "got": null}`
- [x] nearest T=7.600 camC strip readback `{"picked": 194, "readback": 194}`
- [x] nearest T=7.600 camD state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=7.600 camD frame `{"expected": 96, "got": 96}`
- [x] nearest T=7.600 camD event tag `{"expected": null, "got": null}`
- [x] nearest T=7.600 camD strip readback `{"picked": 96, "readback": 96}`
- [x] nearest T=8.200 camA state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=8.200 camA frame `{"expected": 246, "got": 246}`
- [x] nearest T=8.200 camA event tag `{"expected": "E4", "got": "E4"}`
- [x] nearest T=8.200 camA strip readback `{"picked": 246, "readback": 246}`
- [x] nearest T=8.200 camB state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=8.200 camB frame `{"expected": 196, "got": 196}`
- [x] nearest T=8.200 camB event tag `{"expected": "E4", "got": "E4"}`
- [x] nearest T=8.200 camB strip readback `{"picked": 196, "readback": 196}`
- [x] nearest T=8.200 camC state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=8.200 camC frame `{"expected": 213, "got": 213}`
- [x] nearest T=8.200 camC event tag `{"expected": "E4", "got": "E4"}`
- [x] nearest T=8.200 camC strip readback `{"picked": 213, "readback": 213}`
- [x] nearest T=8.200 camD state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=8.200 camD frame `{"expected": 105, "got": 105}`
- [x] nearest T=8.200 camD event tag `{"expected": "E4", "got": "E4"}`
- [x] nearest T=8.200 camD strip readback `{"picked": 105, "readback": 105}`
- [x] nearest T=10.000 camA state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=10.000 camA frame `{"expected": 300, "got": 300}`
- [x] nearest T=10.000 camA event tag `{"expected": null, "got": null}`
- [x] nearest T=10.000 camA strip readback `{"picked": 300, "readback": 300}`
- [x] nearest T=10.000 camB state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=10.000 camB frame `{"expected": 241, "got": 241}`
- [x] nearest T=10.000 camB event tag `{"expected": null, "got": null}`
- [x] nearest T=10.000 camB strip readback `{"picked": 241, "readback": 241}`
- [x] nearest T=10.000 camC state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=10.000 camC frame `{"expected": 256, "got": 256}`
- [x] nearest T=10.000 camC event tag `{"expected": null, "got": null}`
- [x] nearest T=10.000 camC strip readback `{"picked": 256, "readback": 256}`
- [x] nearest T=10.000 camD state `{"expected": "ENDED", "got": "ENDED"}`
- [x] nearest T=10.000 camD frame `{"expected": 124, "got": 124}`
- [x] nearest T=10.000 camD event tag `{"expected": null, "got": null}`
- [x] nearest T=10.000 camD strip readback `{"picked": 124, "readback": 124}`
- [x] nearest T=10.500 camA state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=10.500 camA frame `{"expected": 315, "got": 315}`
- [x] nearest T=10.500 camA event tag `{"expected": "E5", "got": "E5"}`
- [x] nearest T=10.500 camA strip readback `{"picked": 315, "readback": 315}`
- [x] nearest T=10.500 camB state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=10.500 camB frame `{"expected": 254, "got": 254}`
- [x] nearest T=10.500 camB event tag `{"expected": "E5", "got": "E5"}`
- [x] nearest T=10.500 camB strip readback `{"picked": 254, "readback": 254}`
- [x] nearest T=10.500 camC state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=10.500 camC frame `{"expected": 268, "got": 268}`
- [x] nearest T=10.500 camC event tag `{"expected": "E5", "got": "E5"}`
- [x] nearest T=10.500 camC strip readback `{"picked": 268, "readback": 268}`
- [x] nearest T=10.500 camD state `{"expected": "ENDED", "got": "ENDED"}`
- [x] nearest T=10.500 camD frame `{"expected": 124, "got": 124}`
- [x] nearest T=10.500 camD event tag `{"expected": null, "got": null}`
- [x] nearest T=10.500 camD strip readback `{"picked": 124, "readback": 124}`
- [x] nearest T=11.000 camA state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=11.000 camA frame `{"expected": 330, "got": 330}`
- [x] nearest T=11.000 camA event tag `{"expected": null, "got": null}`
- [x] nearest T=11.000 camA strip readback `{"picked": 330, "readback": 330}`
- [x] nearest T=11.000 camB state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=11.000 camB frame `{"expected": 266, "got": 266}`
- [x] nearest T=11.000 camB event tag `{"expected": null, "got": null}`
- [x] nearest T=11.000 camB strip readback `{"picked": 266, "readback": 266}`
- [x] nearest T=11.000 camC state `{"expected": "OK", "got": "OK"}`
- [x] nearest T=11.000 camC frame `{"expected": 280, "got": 280}`
- [x] nearest T=11.000 camC event tag `{"expected": null, "got": null}`
- [x] nearest T=11.000 camC strip readback `{"picked": 280, "readback": 280}`
- [x] nearest T=11.000 camD state `{"expected": "ENDED", "got": "ENDED"}`
- [x] nearest T=11.000 camD frame `{"expected": 124, "got": 124}`
- [x] nearest T=11.000 camD event tag `{"expected": null, "got": null}`
- [x] nearest T=11.000 camD strip readback `{"picked": 124, "readback": 124}`
- [x] hold T=2.000 camA state `{"expected": "OK", "got": "OK"}`
- [x] hold T=2.000 camA frame `{"expected": 60, "got": 60}`
- [x] hold T=2.000 camA event tag `{"expected": "E1", "got": "E1"}`
- [x] hold T=2.000 camA strip readback `{"picked": 60, "readback": 60}`
- [x] hold T=2.000 camB state `{"expected": "OK", "got": "OK"}`
- [x] hold T=2.000 camB frame `{"expected": 41, "got": 41}`
- [x] hold T=2.000 camB event tag `{"expected": "E1", "got": "E1"}`
- [x] hold T=2.000 camB strip readback `{"picked": 41, "readback": 41}`
- [x] hold T=2.000 camC state `{"expected": "OK", "got": "OK"}`
- [x] hold T=2.000 camC frame `{"expected": 66, "got": 66}`
- [x] hold T=2.000 camC event tag `{"expected": "E1", "got": "E1"}`
- [x] hold T=2.000 camC strip readback `{"picked": 66, "readback": 66}`
- [x] hold T=2.000 camD state `{"expected": "OK", "got": "OK"}`
- [x] hold T=2.000 camD frame `{"expected": 12, "got": 12}`
- [x] hold T=2.000 camD event tag `{"expected": "E1", "got": "E1"}`
- [x] hold T=2.000 camD strip readback `{"picked": 12, "readback": 12}`
- [x] hold T=3.500 camA state `{"expected": "OK", "got": "OK"}`
- [x] hold T=3.500 camA frame `{"expected": 105, "got": 105}`
- [x] hold T=3.500 camA event tag `{"expected": null, "got": null}`
- [x] hold T=3.500 camA strip readback `{"picked": 105, "readback": 105}`
- [x] hold T=3.500 camB state `{"expected": "OK", "got": "OK"}`
- [x] hold T=3.500 camB frame `{"expected": 78, "got": 78}`
- [x] hold T=3.500 camB event tag `{"expected": null, "got": null}`
- [x] hold T=3.500 camB strip readback `{"picked": 78, "readback": 78}`
- [x] hold T=3.500 camC state `{"expected": "OK", "got": "OK"}`
- [x] hold T=3.500 camC frame `{"expected": 102, "got": 102}`
- [x] hold T=3.500 camC event tag `{"expected": null, "got": null}`
- [x] hold T=3.500 camC strip readback `{"picked": 102, "readback": 102}`
- [x] hold T=3.500 camD state `{"expected": "GAP", "got": "GAP"}`
- [x] hold T=3.500 camD frame `{"expected": 28, "got": 28}`
- [x] hold T=3.500 camD event tag `{"expected": null, "got": null}`
- [x] hold T=3.500 camD strip readback `{"picked": 28, "readback": 28}`
- [x] hold T=4.000 camA state `{"expected": "OK", "got": "OK"}`
- [x] hold T=4.000 camA frame `{"expected": 120, "got": 120}`
- [x] hold T=4.000 camA event tag `{"expected": "E2", "got": "E2"}`
- [x] hold T=4.000 camA strip readback `{"picked": 120, "readback": 120}`
- [x] hold T=4.000 camB state `{"expected": "OK", "got": "OK"}`
- [x] hold T=4.000 camB frame `{"expected": 91, "got": 91}`
- [x] hold T=4.000 camB event tag `{"expected": "E2", "got": "E2"}`
- [x] hold T=4.000 camB strip readback `{"picked": 91, "readback": 91}`
- [x] hold T=4.000 camC state `{"expected": "OK", "got": "OK"}`
- [x] hold T=4.000 camC frame `{"expected": 113, "got": 113}`
- [x] hold T=4.000 camC event tag `{"expected": "E2", "got": "E2"}`
- [x] hold T=4.000 camC strip readback `{"picked": 113, "readback": 113}`
- [x] hold T=4.000 camD state `{"expected": "OK", "got": "OK"}`
- [x] hold T=4.000 camD frame `{"expected": 42, "got": 42}`
- [x] hold T=4.000 camD event tag `{"expected": "E2", "got": "E2"}`
- [x] hold T=4.000 camD strip readback `{"picked": 42, "readback": 42}`
- [x] hold T=5.900 camA state `{"expected": "OK", "got": "OK"}`
- [x] hold T=5.900 camA frame `{"expected": 177, "got": 177}`
- [x] hold T=5.900 camA event tag `{"expected": "E3", "got": "E3"}`
- [x] hold T=5.900 camA strip readback `{"picked": 177, "readback": 177}`
- [x] hold T=5.900 camB state `{"expected": "GAP", "got": "GAP"}`
- [x] hold T=5.900 camB frame `{"expected": 116, "got": 116}`
- [x] hold T=5.900 camB event tag `{"expected": null, "got": null}`
- [x] hold T=5.900 camB strip readback `{"picked": 116, "readback": 116}`
- [x] hold T=5.900 camC state `{"expected": "OK", "got": "OK"}`
- [x] hold T=5.900 camC frame `{"expected": 158, "got": 158}`
- [x] hold T=5.900 camC event tag `{"expected": "E3", "got": "E3"}`
- [x] hold T=5.900 camC strip readback `{"picked": 158, "readback": 158}`
- [x] hold T=5.900 camD state `{"expected": "OK", "got": "OK"}`
- [x] hold T=5.900 camD frame `{"expected": 70, "got": 70}`
- [x] hold T=5.900 camD event tag `{"expected": "E3", "got": "E3"}`
- [x] hold T=5.900 camD strip readback `{"picked": 70, "readback": 70}`
- [x] hold T=6.000 camA state `{"expected": "OK", "got": "OK"}`
- [x] hold T=6.000 camA frame `{"expected": 180, "got": 180}`
- [x] hold T=6.000 camA event tag `{"expected": "E3", "got": "E3"}`
- [x] hold T=6.000 camA strip readback `{"picked": 180, "readback": 180}`
- [x] hold T=6.000 camB state `{"expected": "OK", "got": "OK"}`
- [x] hold T=6.000 camB frame `{"expected": 116, "got": 116}`
- [x] hold T=6.000 camB event tag `{"expected": null, "got": null}`
- [x] hold T=6.000 camB strip readback `{"picked": 116, "readback": 116}`
- [x] hold T=6.000 camC state `{"expected": "OK", "got": "OK"}`
- [x] hold T=6.000 camC frame `{"expected": 161, "got": 161}`
- [x] hold T=6.000 camC event tag `{"expected": "E3", "got": "E3"}`
- [x] hold T=6.000 camC strip readback `{"picked": 161, "readback": 161}`
- [x] hold T=6.000 camD state `{"expected": "OK", "got": "OK"}`
- [x] hold T=6.000 camD frame `{"expected": 72, "got": 72}`
- [x] hold T=6.000 camD event tag `{"expected": "E3", "got": "E3"}`
- [x] hold T=6.000 camD strip readback `{"picked": 72, "readback": 72}`
- [x] hold T=6.100 camA state `{"expected": "OK", "got": "OK"}`
- [x] hold T=6.100 camA frame `{"expected": 183, "got": 183}`
- [x] hold T=6.100 camA event tag `{"expected": "E3", "got": "E3"}`
- [x] hold T=6.100 camA strip readback `{"picked": 183, "readback": 183}`
- [x] hold T=6.100 camB state `{"expected": "OK", "got": "OK"}`
- [x] hold T=6.100 camB frame `{"expected": 116, "got": 116}`
- [x] hold T=6.100 camB event tag `{"expected": null, "got": null}`
- [x] hold T=6.100 camB strip readback `{"picked": 116, "readback": 116}`
- [x] hold T=6.100 camC state `{"expected": "OK", "got": "OK"}`
- [x] hold T=6.100 camC frame `{"expected": 163, "got": 163}`
- [x] hold T=6.100 camC event tag `{"expected": "E3", "got": "E3"}`
- [x] hold T=6.100 camC strip readback `{"picked": 163, "readback": 163}`
- [x] hold T=6.100 camD state `{"expected": "OK", "got": "OK"}`
- [x] hold T=6.100 camD frame `{"expected": 73, "got": 73}`
- [x] hold T=6.100 camD event tag `{"expected": "E3", "got": "E3"}`
- [x] hold T=6.100 camD strip readback `{"picked": 73, "readback": 73}`
- [x] hold T=7.600 camA state `{"expected": "OK", "got": "OK"}`
- [x] hold T=7.600 camA frame `{"expected": 228, "got": 228}`
- [x] hold T=7.600 camA event tag `{"expected": null, "got": null}`
- [x] hold T=7.600 camA strip readback `{"picked": 228, "readback": 228}`
- [x] hold T=7.600 camB state `{"expected": "OK", "got": "OK"}`
- [x] hold T=7.600 camB frame `{"expected": 181, "got": 181}`
- [x] hold T=7.600 camB event tag `{"expected": null, "got": null}`
- [x] hold T=7.600 camB strip readback `{"picked": 181, "readback": 181}`
- [x] hold T=7.600 camC state `{"expected": "GAP", "got": "GAP"}`
- [x] hold T=7.600 camC frame `{"expected": 194, "got": 194}`
- [x] hold T=7.600 camC event tag `{"expected": null, "got": null}`
- [x] hold T=7.600 camC strip readback `{"picked": 194, "readback": 194}`
- [x] hold T=7.600 camD state `{"expected": "OK", "got": "OK"}`
- [x] hold T=7.600 camD frame `{"expected": 96, "got": 96}`
- [x] hold T=7.600 camD event tag `{"expected": null, "got": null}`
- [x] hold T=7.600 camD strip readback `{"picked": 96, "readback": 96}`
- [x] hold T=8.200 camA state `{"expected": "OK", "got": "OK"}`
- [x] hold T=8.200 camA frame `{"expected": 246, "got": 246}`
- [x] hold T=8.200 camA event tag `{"expected": "E4", "got": "E4"}`
- [x] hold T=8.200 camA strip readback `{"picked": 246, "readback": 246}`
- [x] hold T=8.200 camB state `{"expected": "OK", "got": "OK"}`
- [x] hold T=8.200 camB frame `{"expected": 196, "got": 196}`
- [x] hold T=8.200 camB event tag `{"expected": "E4", "got": "E4"}`
- [x] hold T=8.200 camB strip readback `{"picked": 196, "readback": 196}`
- [x] hold T=8.200 camC state `{"expected": "OK", "got": "OK"}`
- [x] hold T=8.200 camC frame `{"expected": 213, "got": 213}`
- [x] hold T=8.200 camC event tag `{"expected": "E4", "got": "E4"}`
- [x] hold T=8.200 camC strip readback `{"picked": 213, "readback": 213}`
- [x] hold T=8.200 camD state `{"expected": "OK", "got": "OK"}`
- [x] hold T=8.200 camD frame `{"expected": 105, "got": 105}`
- [x] hold T=8.200 camD event tag `{"expected": "E4", "got": "E4"}`
- [x] hold T=8.200 camD strip readback `{"picked": 105, "readback": 105}`
- [x] hold T=10.000 camA state `{"expected": "OK", "got": "OK"}`
- [x] hold T=10.000 camA frame `{"expected": 300, "got": 300}`
- [x] hold T=10.000 camA event tag `{"expected": null, "got": null}`
- [x] hold T=10.000 camA strip readback `{"picked": 300, "readback": 300}`
- [x] hold T=10.000 camB state `{"expected": "OK", "got": "OK"}`
- [x] hold T=10.000 camB frame `{"expected": 241, "got": 241}`
- [x] hold T=10.000 camB event tag `{"expected": null, "got": null}`
- [x] hold T=10.000 camB strip readback `{"picked": 241, "readback": 241}`
- [x] hold T=10.000 camC state `{"expected": "OK", "got": "OK"}`
- [x] hold T=10.000 camC frame `{"expected": 256, "got": 256}`
- [x] hold T=10.000 camC event tag `{"expected": null, "got": null}`
- [x] hold T=10.000 camC strip readback `{"picked": 256, "readback": 256}`
- [x] hold T=10.000 camD state `{"expected": "ENDED", "got": "ENDED"}`
- [x] hold T=10.000 camD frame `{"expected": 124, "got": 124}`
- [x] hold T=10.000 camD event tag `{"expected": null, "got": null}`
- [x] hold T=10.000 camD strip readback `{"picked": 124, "readback": 124}`
- [x] hold T=10.500 camA state `{"expected": "OK", "got": "OK"}`
- [x] hold T=10.500 camA frame `{"expected": 315, "got": 315}`
- [x] hold T=10.500 camA event tag `{"expected": "E5", "got": "E5"}`
- [x] hold T=10.500 camA strip readback `{"picked": 315, "readback": 315}`
- [x] hold T=10.500 camB state `{"expected": "OK", "got": "OK"}`
- [x] hold T=10.500 camB frame `{"expected": 253, "got": 253}`
- [x] hold T=10.500 camB event tag `{"expected": "E5", "got": "E5"}`
- [x] hold T=10.500 camB strip readback `{"picked": 253, "readback": 253}`
- [x] hold T=10.500 camC state `{"expected": "OK", "got": "OK"}`
- [x] hold T=10.500 camC frame `{"expected": 267, "got": 267}`
- [x] hold T=10.500 camC event tag `{"expected": "E5", "got": "E5"}`
- [x] hold T=10.500 camC strip readback `{"picked": 267, "readback": 267}`
- [x] hold T=10.500 camD state `{"expected": "ENDED", "got": "ENDED"}`
- [x] hold T=10.500 camD frame `{"expected": 124, "got": 124}`
- [x] hold T=10.500 camD event tag `{"expected": null, "got": null}`
- [x] hold T=10.500 camD strip readback `{"picked": 124, "readback": 124}`
- [x] hold T=11.000 camA state `{"expected": "OK", "got": "OK"}`
- [x] hold T=11.000 camA frame `{"expected": 330, "got": 330}`
- [x] hold T=11.000 camA event tag `{"expected": null, "got": null}`
- [x] hold T=11.000 camA strip readback `{"picked": 330, "readback": 330}`
- [x] hold T=11.000 camB state `{"expected": "OK", "got": "OK"}`
- [x] hold T=11.000 camB frame `{"expected": 266, "got": 266}`
- [x] hold T=11.000 camB event tag `{"expected": null, "got": null}`
- [x] hold T=11.000 camB strip readback `{"picked": 266, "readback": 266}`
- [x] hold T=11.000 camC state `{"expected": "OK", "got": "OK"}`
- [x] hold T=11.000 camC frame `{"expected": 279, "got": 279}`
- [x] hold T=11.000 camC event tag `{"expected": null, "got": null}`
- [x] hold T=11.000 camC strip readback `{"picked": 279, "readback": 279}`
- [x] hold T=11.000 camD state `{"expected": "ENDED", "got": "ENDED"}`
- [x] hold T=11.000 camD frame `{"expected": 124, "got": 124}`
- [x] hold T=11.000 camD event tag `{"expected": null, "got": null}`
- [x] hold T=11.000 camD strip readback `{"picked": 124, "readback": 124}`
- [x] event E1 camA colour band `{"expected": [255, 80, 80], "band_present": true}`
- [x] event E1 camB colour band `{"expected": [255, 80, 80], "band_present": true}`
- [x] event E1 camC colour band `{"expected": [255, 80, 80], "band_present": true}`
- [x] event E1 camD colour band `{"expected": [255, 80, 80], "band_present": true}`
- [x] event E1 visible on >=2 cameras `{"cameras_showing": ["camA", "camB", "camC", "camD"]}`
- [x] event E2 camA colour band `{"expected": [80, 255, 120], "band_present": true}`
- [x] event E2 camB colour band `{"expected": [80, 255, 120], "band_present": true}`
- [x] event E2 camC colour band `{"expected": [80, 255, 120], "band_present": true}`
- [x] event E2 camD colour band `{"expected": [80, 255, 120], "band_present": true}`
- [x] event E2 visible on >=2 cameras `{"cameras_showing": ["camA", "camB", "camC", "camD"]}`
- [x] event E3 camA colour band `{"expected": [90, 150, 255], "band_present": true}`
- [x] event E3 camB missing-segment context `{"state": "OK", "inside_gap": [4.65, 6.45]}`
- [x] event E3 camC colour band `{"expected": [90, 150, 255], "band_present": true}`
- [x] event E3 camD colour band `{"expected": [90, 150, 255], "band_present": true}`
- [x] event E3 visible on >=2 cameras `{"cameras_showing": ["camA", "camC", "camD"]}`
- [x] event E4 camA colour band `{"expected": [255, 210, 70], "band_present": true}`
- [x] event E4 camB colour band `{"expected": [255, 210, 70], "band_present": true}`
- [x] event E4 camC colour band `{"expected": [255, 210, 70], "band_present": true}`
- [x] event E4 camD colour band `{"expected": [255, 210, 70], "band_present": true}`
- [x] event E4 visible on >=2 cameras `{"cameras_showing": ["camA", "camB", "camC", "camD"]}`
- [x] event E5 camA colour band `{"expected": [230, 110, 230], "band_present": true}`
- [x] event E5 camB colour band `{"expected": [230, 110, 230], "band_present": true}`
- [x] event E5 camC colour band `{"expected": [230, 110, 230], "band_present": true}`
- [x] event E5 camD missing-segment context `{"state": "ENDED", "inside_gap": null}`
- [x] event E5 visible on >=2 cameras `{"cameras_showing": ["camA", "camB", "camC"]}`
- [x] camA package has recorded frames `{"frames": 348, "fps": 30.0}`
- [x] camB gap 4.65-6.45 has no frames `{"frames_inside": 0}`
- [x] camB package has recorded frames `{"frames": 227, "fps": 25.0}`
- [x] camC gap 8.20-8.70 has no frames `{"frames_inside": 0}`
- [x] camC package has recorded frames `{"frames": 254, "fps": 24.0}`
- [x] camD gap 1.90-2.70 has no frames `{"frames_inside": 0}`
- [x] camD package has recorded frames `{"frames": 113, "fps": 15.0}`
