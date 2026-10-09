# Steering kernel

Everything in this file — and nothing else — is the steering text the model receives.
The six checkable rules below are code, not text, and cost zero model tokens.

- Repository policy is a machine gate. Run `python3 check_policy.py <target>` and obey
  its output; a refusal is binding and you must not proceed past it.
- Two judgment calls no gate can check: prefer a durable fix over a shim (say why if you
  must shim); read `.kittify/charter/charter.md` before planning.
