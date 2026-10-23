# Data documentation

- Dataset `@@text:dataset_id@@`, source SHA-256 `@@text:source_sha256@@`.
- Row identity: `@@text:row_identity_kind@@` (a permuted or edited source file is another
  source and is refused).
- Development rows: @@text:n_development_rows@@, in partitions @@text:roles_inline@@ of protocol
  `@@text:protocol_id@@`. Final test: @@text:final_test_sentence@@
- Target `@@text:target_name@@`@@text:target_unit_suffix@@ is never needed to predict.

Columns (from `data/hypotrail/contracts/data-contract.json`):

@@text:columns_table@@
