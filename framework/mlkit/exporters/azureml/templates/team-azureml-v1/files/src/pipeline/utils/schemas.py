"""Schema of the study's development rows (rendered by the Hypotrail export).

The authority is the data contract in ``data/hypotrail/contracts/data-contract.json``
(``hypotrail.data_contract/1``); this module only names its columns for readers and
tests. The example schemas of the team template were removed.
"""

DATASET_ID = @@py:dataset_id@@
TARGET = @@py:target_name@@
FEATURES = @@py:features@@
# name -> (role, physical type, semantic type, nullable)
COLUMNS = @@py:schema_columns@@
