# Cursorstat gate v2 result

**Date:** 2026-10-05
**Branch:** `feat/map-homography`
**Reader blob:** `5e52384db61e4c3c76e727a23f6a83ff7ca62f36`
**Reader freeze:** `54ffcce`
**Score tools:** `ab47a2c`
**Result:** failed. Sealed as `data/runtime/cursorstat_sessions/gate_report_v2.json`. Exit 3.

The sessions `20261003-gate17` and `20261004-gate18` are regression only. They do not gate a reader. See `docs/cursorstat-regression-v2.json`.

## Sealed counts

| | Count |
|---|---:|
| Frames | 528 |
| Read | 492 |
| Miss | 1 |
| Wrong | 35 |
| Corrected | 2 |
| Unreadable | 0 |
| Reader on unreadable | 0 |

## Corrections

Both reasons are `operator typo, relabeled from crop in 20261005-gate-review`. `labels.json` was not edited.

| Session | Frame | Old | New |
|---|---|---|---|
| `20261003-gate17` | `sweep1_21.png` | 89, 90 | 89, 80 |
| `20261004-gate18` | `sweep4_27.png` | 175, 96 | 175, 69 |

## Leading 1

The 35 wrong reads are all in `20261004-gate18`. The label x is 160–169. The reader returns that x without the leading 1 and the same y. Examples: 160, 74 read as 60, 74; 163, 65 read as 63, 65; 169, 65 read as 69, 65. The operator typed those 16x labels again in `20261005-gate-review`, so they are not typos.

The remaining miss is `20261003-gate17/sweep2_00.png`. The operator labeled it 94, 102. The reader abstains.
