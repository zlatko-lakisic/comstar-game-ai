# Cursorstat gate v3 result

**Date:** 2026-10-06
**Branch:** `feat/map-homography`
**Reader blob:** `510274238a21fdac8b76b067524bbdec5d235eb6`
**Reader freeze:** `9e4dd23`
**Score tools:** `8e06f43`
**Result:** failed. Sealed as `data/runtime/cursorstat_sessions/gate_report_v3.json`. Exit 3.

The sessions `20261006-gate19` through `20261006-gate24` are regression only. They do not gate a reader. Even frames only. See `docs/cursorstat-regression-v3.json`. The v2 regression file is unchanged.

## Sealed counts

| | Count |
|---|---:|
| Frames | 440 |
| Read | 430 |
| Miss | 0 |
| Wrong | 10 |
| Corrected | 2 |
| Unreadable | 0 |
| Reader on unreadable | 0 |

## Corrections

Both reasons are `operator typo, relabeled from review crop`. `labels.json` was not edited.

| Session | Frame | Old | New |
|---|---|---|---|
| `20261006-gate22` | `sweep0_20.png` | 78, 99 | 70, 99 |
| `20261006-gate22` | `sweep1_36.png` | 755, 119 | 75, 119 |

## The 10 wrong reads

Eight are `20261006-gate23` sweep5. The label x is 43, 44, 48, or 49. The reader returns that x without the leading 4 and the same y. Examples: 43, 42 read as 3, 42; 48, 42 read as 8, 42; 44, 49 read as 4, 49. Each one was accepted at ink cutoff 60 on the strict path. The operator typed those labels again in `20261006-gate-review`, so they are not typos.

The other two were accepted only after the strict ink-60 line refused unexplained ink and the fainter pass at cutoff 57 returned a coordinate. `20261006-gate19/sweep0_38.png` is labeled 102, 91 and read as 102, 94. `20261006-gate24/sweep0_00.png` is labeled 91, 53 and read as 94, 53.
