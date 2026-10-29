# Tech stack

**Status:** ✅ Approved 2026-10-29 (Rhino 8 first); see [`docs/plan.md`](../../../docs/plan.md)

Part of [03 · Planning](../README.md) in the [Lintel SaaS plan](../../README.md).

## Architecture
```
 Host app (Rhino 8 / later SketchUp, Revit)              Lintel backend (FastAPI, :8002)
 +--------------------------------------+   HTTP/JSON   +-----------------------------------+
 | lintel_rhino.py                      | ------------> | /api/plugin/snapshot  model in    |
 |  - extract snapshot (layers+usertext)|               | /api/plugin/pending   approved    |
 |  - apply ops in one undo record      | <------------ |        change sets out            |
 |  - WebView panel -> /panel?project=  |   poll 2 s    | /api/plugin/result    applied     |
 +--------------------------------------+               |                                   |
                                                        | checker.py  deterministic rules   |
 Browser dashboard (/) ---------------------------->    | agent.py    Claude + tool calls   |
   projects, issues, approval queue, history,           | store.py    SQLite: projects,     |
   rules, audit log, chat                               |   snapshots, rules, changesets,   |
                                                        |   audit, chat                     |
                                                        +-----------------------------------+
```

## Choices
| Layer | Choice | Why |
|---|---|---|
| Backend | Python 3.12 + FastAPI + SQLite (stdlib `sqlite3`) | Same family as the other workspace apps; zero-ops locally; Postgres later |
| Agent | Anthropic Python SDK, Claude (model configurable, default `claude-sonnet-5-5`) with tool use | Strong tool use; tools map to host ops, and approval is enforced server-side |
| Checker | Plain Python, deterministic | Repeatable results that don't depend on the LLM; the LLM explains and proposes |
| Dashboard | Static HTML + vanilla JS served by FastAPI | No build step; the same page is embedded in the host panel |
| Host plugin #1 | Rhino 8, Python 3 (RhinoCommon, Eto `WebView`), run with `RunPythonScript`; later packaged with yak | Free 90-day trial and free SDK. Rhino has no BIM semantics, so the plugin reads a **layer and user-text convention** (`Lintel::Rooms`, `Lintel::Doors`, …) |
| Test host | `hosts/fixture_host.py`: same protocol, JSON model | Lets e2e run without Rhino |

## Host plugin protocol (shared by every host)
- `POST /api/plugin/snapshot` with `{project, host, elements:[{id,type,props,geom}]}`.
- `GET /api/plugin/pending?project=` returns approved change sets: `{id, ops:[{op, element, prop, from, to}, ...]}`.
- `POST /api/plugin/result` with `{changeset, ok, error?, elements?}`.

Element types are `room` (a corridor is a room with `use=corridor`), `wall`, `door`, `stair` and `exit` (a door with `exit=true`).

**Operations:**
- `set_prop`: door width, stair riser/tread, room name.
- Every op carries the `from` value it expects. The host refuses the whole change set if the model has drifted since the proposal.
