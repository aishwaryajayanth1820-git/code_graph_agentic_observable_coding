# Seed JSON format (`cg import`, `cg export`)

The orchestrator writes the C4 design as one seed file (for example `<project>/design/c4_seed.json`) and imports it. Import is an idempotent upsert: existing nodes are updated (policies still apply), new ones are created, and parents are processed before children. A full example is in `code_graph/examples/sample_seed.json`.

```json
{
  "project": "notification_platform",
  "nodes": [
    {"id": "dispatch_engine", "name": "Dispatch Engine", "type": "COMPONENT", "layer": "PLATFORM",
     "business_intent": "...", "extensibility": "Plugin registry + Channel strategy", "code_path": "src/dispatch_engine"},
    {"id": "dispatch_engine.channel", "name": "Channel", "type": "INTERFACE", "parent": "dispatch_engine",
     "business_intent": "...", "contract": "configure(config); send(message) -> DeliveryResult",
     "code_path": "src/dispatch_engine/ports.py::Channel"}
  ],
  "edges": [
    {"kind": "DEPENDS", "from": "email_channel", "to": "dispatch_engine"},
    {"kind": "IMPLEMENTS", "from": "email_channel.email_sender", "to": "dispatch_engine.channel"},
    {"kind": "CALLS", "from": "dispatch_engine.dispatcher", "to": "dispatch_engine.channel",
     "function": "send", "signature": "send(message: Message) -> DeliveryResult",
     "purpose": "Hand each routed message to its channel plugin."}
  ],
  "utilities": [
    {"name": "render_template", "signature": "render_template(template: str, values: Mapping[str, str]) -> str", "purpose": "...", "module_path": "src/common/templates.py"}
  ],
  "evals": [
    {"id": "BIZ-101", "category": "BUSINESS", "title": "...", "rule": "...", "check_method": "...", "severity": "BLOCKER"}
  ]
}
```

Node keys: `id`, `name`, `type`, `layer` (optional under a parent), `parent`, `status`, `business_intent`, `extensibility`, `contract`, `code_path`, `loc`, `complexity`, `complexity_note`, `owner`.
Edge keys: `kind`, `from`, `to`, plus `function`, `signature`, `purpose` for CALLS.

Rules of thumb:
- Import **before** `cg design lock`. After the lock, an import that adds nodes needs `--adr <accepted ADR>`.
- Keep the seed file as the design source during planning. Once coding starts, the database is the source of truth; use `cg export` to snapshot it.
