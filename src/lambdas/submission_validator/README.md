# Submission Validator

This Lambda validates that a submission exists and contains all expected `fileId`s.

It is used by the Phase 5 Step Functions skeleton to fail cleanly when the completion event arrives before all expected files are present.
