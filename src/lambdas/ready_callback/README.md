# Ready Callback

This Lambda is the POC stand-in for the external "submission ready" callback.

Inputs:

- `submissionId`
- `status`
- `readyAt`
- `documentIds`

Behavior:

- records `callbackStatus=DELIVERED` in `SubmissionRegistry`
- records `callbackDeliveredAt`
- logs the delivered payload as structured JSON

The current POC uses this as a mock external endpoint so we can validate callback sequencing without depending on an out-of-band HTTP target.
