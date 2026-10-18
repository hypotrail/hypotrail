# Auto MPG

Second acceptance case, used after Bank Marketing to verify adaptation to regression.

`case.yaml` is the junior study case contract ([`hypotrail.case/1`](../../docs/specs/CASE-CONTRACT.md)), generated from `project.json` and `case-supplement.yaml`. Since M3 the engine runs it as a regression study: an ordinal split on `model_year`, MAE and RMSE in mpg, residuals, and a model choice against the training mean. The declared group column `car_name` is accepted with its limitation named (`grouped split (v0.2)`): each split reports the car names both partitions share.

UCI Auto MPG contains 398 observations with numeric target `mpg`. Provenance, limitations, and units needing confirmation are in `project.json` and `data/auto-mpg.names`. Higher mpg means more distance per gallon and therefore better fuel efficiency.

The historical `prepare_auto_mpg.py` experiment learns from model years 1970–1978 (280 rows) and compares on 1979–1982 (118 rows). Models and errors are already in `results.json`. Executing the script trains models; viewing outputs does not.

The future workflow should use MAE/RMSE in mpg, residuals, and an appropriate reference rather than classification threshold controls. Some car names repeat across years; chronology alone does not establish independence between vehicle models. These historical observations do not describe current vehicles.
