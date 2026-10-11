# Decomposition guide: requirement → C4 nodes

## 1. Levels
| Graph type | C4 meaning | Typical content |
|---|---|---|
| `COMPONENT` | C4 component: a cohesive module/package with one responsibility area. It is a boundary in the UI | `config_manager`, `dispatch_engine` |
| `SERVICE_CLASS` | The component's application service / facade: the entry point other components call | `ConfigLibrary`, `Dispatcher` |
| `INTERFACE` | Port or extension point: plugin contracts, repositories, event sources | `Channel`, `RoutingRule`, `EventSource` |
| `CLASS` | Implementation classes (adapters, domain logic, plugins) | `SqliteConfigRepository`, `EmailSender` |
| `CONFIG_CLASS` | Typed configuration / settings objects | `ChannelConfig` |
| `UTILITY_CLASS` | Stateless shared helpers (also register the functions with `cg util add`) | `MoneyUtils` |

Functions are **not** nodes. Every function one class calls on another becomes a `CALLS` edge named after the function.

## 2. Platform vs use case
Put a responsibility in the **PLATFORM** layer if a second use case would need it unchanged: data feeds, config library, plugin loading, runtime envelope (quotas, rate limits, retries), persistence, observability. Put it in **USECASE** if it encodes one business variant: a specific channel, a specific routing rule, a specific report.

Test for a good split: adding the next anticipated use case means adding new USECASE nodes plus IMPLEMENTS edges, and zero edits to PLATFORM nodes. Write each anticipated use case into the platform component's `extensibility` field.

## 3. Procedure
1. List the business capabilities in the requirement and group them into components (usually 4–8 for a medium service).
2. For each component: pick its service class (entry point), its ports (interfaces), its implementations, and its config classes.
3. Draw the dependencies between components as `DEPENDS` edges. They must form a DAG, with PLATFORM never pointing at USECASE.
4. Write the contracts: for each interaction, add a `CALLS` edge `caller → callee` with the exact typed signature and one line of purpose. Cross-component calls target INTERFACE or SERVICE_CLASS nodes only.
5. Add `IMPLEMENTS` edges for every planned implementation of an interface.
6. Fill every node's `business_intent`, `extensibility` (anticipated change + pattern: Strategy, Ports & Adapters, Registry/Plugin, Chain of Responsibility, Observer, Template Method…), `contract` summary and planned `code_path`.
7. Seed shared utilities you already know about (money rounding, clock, id generation), so coders find them.

## 4. Id and path conventions
- Component ids: `snake_case` (`dispatch_engine`). Class ids: `<component>.<snake_class>` (`dispatch_engine.plugin_loader`).
- Names are the class names used in code, and are unique across the project.
- `code_path`: components → a directory (`src/dispatch_engine`), classes → `file.py::ClassName`.

## 5. Sizing
- **Small service:** 2–4 components, no ports unless the requirement anticipates variation.
- **Medium service:** ports and adapters around I/O (feeds, storage), plugin registries at the business variation points, and config as data.
- Anything whose expected complexity is > 7 gets split before coding.

## 6. `design/c4_design.md` template
```markdown
# <Project> C4 design
## Context          one paragraph: purpose, users, external systems
## Components       table: id | layer | responsibility | depends on | extension points
## Classes          per component: id | type | business intent | contract summary
## Contracts        table: caller | callee | function | signature | purpose
## Extension points interface | anticipated use cases | how a new one is added (files touched)
## Out of scope     deferred requirements, e.g. a phase-2 feature
## Decisions        link to ADRs (cg adr list)
```

## 7. Done when
- `cg check` has no ERRORs, every INTERFACE has a planned implementer, and every node has intent, extensibility (where relevant) and a code_path.
- Each planned coder task can be expressed as a set of nodes with no overlap between parallel tasks.
