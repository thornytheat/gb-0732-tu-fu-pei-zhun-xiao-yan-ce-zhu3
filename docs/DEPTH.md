# 深度登记 · 图幅配准校验册

- 规模：中型。县域测绘档案员从控制点原件开始，逐章校验后将图幅结论签入档案。
- 核心规则：只有非共线、稳定采信的控制点进入仿射模型，已登记的相邻边另用独立见证点投影测距。

## 功能模块

| 模块 | 使用者动作 | 入口 | 核心文件 | 测试 |
|---|---|---|---|---|
| M1 点表收件 | 探查表头、格式与原件结构 | `GET /api/intake` | `app/modules/intake/reader.py` `app/modules/intake/catalog.py` | `tests/test_intake.py` |
| M2 坐标换算 | 核对度、米、厘米与像素坐标 | `GET /api/coordinates` | `app/modules/coordinates/projection.py` `app/modules/coordinates/service.py` | `tests/test_coordinates.py` |
| M3 控制点配对 | 提取同名或同别名点的两侧证据 | `GET /api/pairing` | `app/modules/pairing/aliases.py` `app/modules/pairing/duplicates.py` | `tests/test_pairing.py` |
| M4 仿射拟合 | 求模型与初算误差 | `GET /api/affine` | `app/modules/affine/solve.py` `app/modules/affine/residuals.py` | `tests/test_affine.py` |
| M5 离群重估 | 查看稳健重估后的残差及排除理由 | `GET /api/refit` | `app/modules/refit/consensus.py` `app/modules/refit/service.py` | `tests/test_refit.py` |
| M6 接缝验核 | 验证相邻边覆盖、次序与偏差 | `GET /api/seams` | `app/modules/seams/witnesses.py` `app/modules/seams/geometry.py` `app/modules/seams/service.py` | `tests/test_seams.py` |
| M7 图幅签审 | 勾稽三表、签审、留存和导出 | `POST /api/review/runs` | `app/modules/review/decisions.py` `app/modules/review/reconcile.py` `app/modules/review/service.py` | `tests/test_review.py` |

## 陷阱登记

| TRAP | 样例与现象 | 朴素实现会怎样 | 本项目处理 | 处理位置 | 测试 |
|---|---|---|---|---|---|
| TRAP-01 | `sample_data/field/ground.csv` 为 GB18030 | 解码失败 | UTF-8 严格探测后回退 | `app/modules/intake/decode.py` | `tests/test_intake.py::test_gb18030_archive` |
| TRAP-02 | `sample_data/field/pixels.csv` 带 BOM | 首列不识别 | BOM 单独解码 | `app/modules/intake/decode.py` | `tests/test_intake.py::test_bom_stripped_from_first_header` |
| TRAP-03 | `sample_data/field/pixels.csv` 的首条备注跨行 | 一条拆两条 | CSV 逻辑记录保留物理起止行 | `app/modules/intake/reader.py` | `tests/test_intake.py::test_multiline_records_preserve_physical_lines` |
| TRAP-04 | `sample_data/field/pixels.csv` 有分段表头与空行 | 算入点数 | 分别登记 | `app/modules/intake/reader.py` | `tests/test_intake.py::test_repeated_section_header_is_counted_separately` |
| TRAP-05 | `sample_data/field/pixels.csv` 的短行多一个分隔符 | 字段错位 | 保留原列后隔离 | `app/modules/intake/reader.py` | `tests/test_intake.py::test_extra_delimiter_preserves_unshifted_raw_row` |
| TRAP-06 | `sample_data/field/pixels.csv` 有全角带千分位的像素 | 数值转换失败 | 规范化后校验分组和单位 | `app/modules/coordinates/numbers.py` | `tests/test_coordinates.py::test_fullwidth_thousands_and_pixel_suffix` |
| TRAP-07 | `sample_data/field/pixels.csv` 有 `N/A` | 用零点误配 | 缺测行单列隔离 | `app/modules/coordinates/service.py` | `tests/test_coordinates.py::test_missing_token_is_not_a_zero_coordinate` |
| TRAP-08 | `sample_data/field/pixels.csv` 的 `0421` | 前导零丢失 | 图幅字符串做业务键 | `app/modules/pairing/service.py` | `tests/test_pairing.py::test_sheet_codes_keep_their_leading_zero` |
| TRAP-14 | `sample_data/field/ground.csv` 与 `pixels.csv` 有同名冲突重测 | 末行覆盖前值 | 全组隔离并保留冲突行 | `app/modules/pairing/duplicates.py` | `tests/test_pairing.py::test_ground_and_pixel_conflicts_do_not_use_last_write` |
| TRAP-15 | `sample_data/field/ground.csv` 含经纬度、厘米和错误后缀 | 混合度米直接拟合 | 转 ENU 及处理单位冲突 | `app/modules/coordinates/projection.py` | `tests/test_coordinates.py::test_centimeters_and_geographic_degrees_match_reference` `tests/test_coordinates.py::test_degree_meter_conflicts_and_mismatched_suffix_are_isolated` |
| TRAP-16 | 在 `sample_data/field/witness.csv` 的测试副本续入半截引号 | 部分提交 | 结构错误拒收且事务无半批 | `app/modules/intake/reader.py` | `tests/test_intake.py::test_open_quote_after_valid_records_rejects_whole_table` |
| TRAP-18 | `sample_data/field/pixels.csv` 的测试副本分别留空、空行和表头 | 都当成功空批 | 独立收件状态 | `app/modules/intake/reader.py` | `tests/test_intake.py::test_empty_blank_and_header_only_are_distinct` |
| TRAP-19 | 测试内两组同规模像素仿射共享四点 | 按遍历次序裁决 | 同等多数阻断 | `app/modules/refit/consensus.py` | `tests/test_refit.py::test_same_size_alternate_models_return_ambiguity_instead_of_arbitrary_choice` |
| TRAP-20 | 测试内两条别名互相指向 | 无限追溯 | 检测别名环并给出路径 | `app/modules/pairing/aliases.py` | `tests/test_pairing.py::test_alias_loop_and_normalized_collision_are_explicit` |
| TRAP-22 | `sample_data/field/catalog.json` 的两级旧名 | 错丢控制点 | 确定性归并 | `app/modules/pairing/aliases.py` | `tests/test_pairing.py::test_alias_chains_resolve_independent_of_row_and_alias_order` |
| TRAP-26 | `sample_data/field/` 的柳湾在测试中被两名签审员提交 | 后写覆盖签审 | 检查版本并保持首笔 | `app/store.py` | `tests/test_review.py::test_stale_signature_cannot_replace_first_reviewer` |
| TRAP-27 | `sample_data/field/pixels.csv` 的双井 7 点共线 | 系数表面可求，模型不可用 | 设计秩阻断 | `app/modules/affine/solve.py` | `tests/test_affine.py::test_collinear_scans_are_blocked_even_with_seven_controls` |
| TRAP-28 | `sample_data/field/ground.csv` 的河西 P08 偏离 | 初算剔除误伤多点 | 稳定多数重估恢复良点 | `app/modules/refit/consensus.py` | `tests/test_refit.py::test_refit_recovers_good_points_that_initial_fit_would_drop` |
| TRAP-29 | `sample_data/field/witness.csv` 的 `HX-QS` | 小训练残差冒充拼缝通过 | 两侧独立投影后取最大平面差 | `app/modules/seams/geometry.py` | `tests/test_seams.py::test_independent_edge_fails_even_when_both_training_residuals_are_small` |
| TRAP-30 | `sample_data/field/witness.csv` 测试副本用旧控制点名冒充见证 | 重复证据进入独立核验 | 用规范名和像素索引排除 | `app/modules/seams/witnesses.py` | `tests/test_seams.py::test_pseudo_witness_reusing_a_control_alias_is_excluded` |

## 对账

| 输入 | 去向 |
|---|---|
| 53 条控制点像素记录 | 35 采信 + 1 离群 + 17 隔离 |
| 49 条地面坐标记录 | 43 配对 + 6 隔离 |
| 19 条拼缝见证记录 | 18 可用 + 1 隔离 |

空行和重复表头各一行，未纳入逻辑记录。对账比较源行号多重集，同计数但错行也会阻断。签审沿所有登记拼缝求判定，`HX-QS` 实测超限与 `QS-SJ` 缺模型分别留证。
