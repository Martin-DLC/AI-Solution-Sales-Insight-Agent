# Retrieval Metadata Blind Label Freeze

## P1合同假设背景

- Runtime Boundary Contract v2.1 当前仍是 P1：content explainable but not blind validated。
- 本阶段只负责导入并冻结 blind labels，不做任何效果评估。

## Blind Packet来源隔离

- 盲标只基于 authoring packet、guide、template 和 blind bundle manifest 完成。
- 本阶段未读取 Mapping、Cases、Gold、正式 Results 或 Comparison。

## Workspace Attempt说明

- 第一次 workspace 设置失败发生在 packet 访问前。
- 该失败没有生成标签，不计入有效 blind authoring attempt 数量。
- 第一次有效 blind authoring attempt 已完成并被冻结。

## 输入Hash

- packet_sha256: d67abcf03ea4be2eb1c992efca133eea9cf2af0acacebe2401b2eaea05124364
- guide_sha256: 94f36c4dec139e10afeb08e7fac9905a138a9927e2ea74bf489953b2a0397986
- template_sha256: d66dcdcc5c39d81f2efe0c7597ea46fd1bc77f5bc1d4e1b1b51907696f84b8d0
- bundle_manifest_sha256: e8eee96bbe163e8b6f11328243b1d0aa86f55ad276adad67c161dc71443fb9e7

## 输出Hash

- completed_labels_sha256: 748797a5772e4389c89a1fd013f114d1097b1be862f5dc386b2d69b8ed69f839
- authoring_report_sha256: af56e2cddfdb026d81654cd7b55f0988ec46d3bd8be3ec2a3901c90398a7500c

## 覆盖范围

- document_count: 20
- chunk_count: 40

## Mode分布

- document_default_mode_counts: {"full_applicable_scope": 8, "global_reusable": 6, "primary_in_scope": 6}
- chunk_override_count: 4
- chunk_override_mode_counts: {"full_applicable_scope": 0, "global_reusable": 1, "primary_in_scope": 3}

## Manual Review

- manual_review_document_count: 0
- manual_review_chunk_count: 0

## 冻结边界

- 标签在任何评估开始前被冻结。
- 本阶段未加载 Mapping、Cases 或 Gold。
- 本阶段未进行效果评估，也未计算 retention、boundary removal、recall 或 eligible。
- 若后续评估失败，不得基于评估结果回改同一快照标签。

## 下一阶段

- 下一阶段是独立 Evaluation，而不是当前 freeze 阶段继续判断效果。
- RET2-015 / RET2-016 仍是独立 Recall 问题。
- Architecture C 仍为 blocked。


## Attempt 2 Freeze

- Schema和枚举未改变。
- Guide / Protocol 发生变化。
- Attempt 2 在独立 Workspace 完成。
- Mode 分布为 primary_in_scope=6、full_applicable_scope=8、global_reusable=6。
- Chunk Override 为 4。
- Manual Review 为 0。
- 标签在 Evaluation 前冻结。
- Attempt 1 快照保持不变。
- Attempt 2 只允许进行一次独立评估。
- 无论成功失败，Boundary 合同研究之后结束。

- protocol_version: 2.2
- blind_attempt_number: 2
- completed_labels_sha256: 748797a5772e4389c89a1fd013f114d1097b1be862f5dc386b2d69b8ed69f839
- authoring_report_sha256: af56e2cddfdb026d81654cd7b55f0988ec46d3bd8be3ec2a3901c90398a7500c