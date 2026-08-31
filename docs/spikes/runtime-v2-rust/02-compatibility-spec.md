# Compatibility Specification

Hard requirement: Rust candidate may not create an unrelated durable world.

## Event JSON

Events serialized by Runtime v1 at `14c905c29299c6b2d7d1957208e84536ba707a1d` must be deserializable by the Rust candidate and project to the same semantic state for mandatory fixtures.

## SQLite

A deterministic SQLite fixture produced by the TS v1 reference must be opened/read by the Rust candidate in compatibility mode and yield equivalent projection/evidence for the chosen fixture scope.

## Failure rule

If compatibility requires breaking redesign of v1 durable semantics, stop the spike and recommend `KEEP_TS_CORE` unless the human explicitly creates a new experiment charter.
