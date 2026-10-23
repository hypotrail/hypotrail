# Solution Design and Architecture

Study `@@text:study_id@@` (revision @@text:study_revision@@) selected a @@text:task@@ model,
family `@@text:family@@`, with decision `@@text:selection_decision@@`. This project runs the
recorded recipe; it does not choose a model.

```
data/hypotrail (one data asset)          src (code: upload, filtered by .amlignore)
  development/ ──► data_preparation ──► data_splitting ──► training ──► evaluation
  contracts/   ──►   (typing only)      (recorded plan)   (new candidate) (technical checks)
  models/evaluated/  (the evaluated model, transported as captured; never refitted)
```

Two objects must not be confused:

- the **evaluated model** (`data/hypotrail/models/evaluated/`): the object the study captured
  before its final test; its evidence status is `@@text:evidence_status@@`;
- a **rebuilt candidate** (output of `training`): a new fit of the same recipe on the
  development rows. It has a new identity and does not inherit the study's verdict.
