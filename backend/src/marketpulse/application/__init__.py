"""Application layer: use cases and ports (interfaces).

Orchestrates domain rules and depends only on abstractions (ports). Concrete
adapters (databases, queues, HTTP) live in `infrastructure/` and are injected at the
composition root (`marketpulse.main`). Same import restrictions as the domain layer.
"""
