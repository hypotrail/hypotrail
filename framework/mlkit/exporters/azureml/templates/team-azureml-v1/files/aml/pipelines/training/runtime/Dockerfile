# Minimal build context of the Azure ML environment (Hypotrail export, team-azureml-v1).
# It holds no data and no study: the lock, and the runtime wheel when the model was captured.
FROM @@text:base_image@@
COPY . /tmp/hypotrail/
RUN python -m pip install --no-cache-dir -r /tmp/hypotrail/requirements.lock
@@text:wheel_install@@
