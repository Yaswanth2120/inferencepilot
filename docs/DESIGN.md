# Design status

M0 implements package wiring, best-effort environment inspection, and isolated
fake tools. See AGENTS.md for the planned architecture. Planner, statistics,
server management, adapters, persistence, and reporting are later milestones.

Production modules do not import the fake package. Tests invoke its executable
through PATH or use its ASGI application directly. The fake bench emits seeded
synthetic measurements; it does not generate load or contact a real server.
