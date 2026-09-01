"""The second entry point.

ARCHITECTURE.md §3: `workers/` sits beside `routes/`, at the same level, and
consumes `services/` exactly as routes do. A job must be runnable from either
without changes — which is why nothing in here contains pipeline logic, and why
the confirmation gate lives in the service layer where both callers cross it.
"""
