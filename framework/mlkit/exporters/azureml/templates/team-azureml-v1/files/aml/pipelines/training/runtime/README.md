# Environment build context

Minimal context of the Azure ML environment (`../aml-environment.yml`): the `Dockerfile`, a
byte copy of `../requirements.lock` (checked by `data/hypotrail/SHA256SUMS` through the
export manifest) and, when the study captured its model, the `hypotrail_runtime` wheel of
that model. It holds no data, no study and no credential. The base image comes from the
destination profile; the environment is qualified only by a recipe run on Azure.
