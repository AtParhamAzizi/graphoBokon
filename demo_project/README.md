# Architecture demo

A small user-management application with 25 Python files and 100 symbols. It connects API routes, services, repositories, HTTP clients, models, validation, events, decorators, reports, workflows, jobs, and plugins. Every relationship type supported by PyArch has a concrete example.

## Explore the graph

Scan the `demo_project` directory from PyArch. Select a file in the ring or explorer to inspect its symbols, source, and incoming/outgoing dependencies. Drag to pan, scroll to zoom, and use the file filter to search. The backend JSON export includes symbol-level evidence and all relationship types listed below.

## Relationship examples

| Type | Example |
| --- | --- |
| `CONTAINS` | `UserService` contains `create`; `traced` contains the nested `wrapped` function. |
| `IMPORTS` | `services.py` imports `UserRepository` through a package re-export. |
| `CALLS` | `create_user_route` calls the cross-file `create_user` service function. |
| `INSTANTIATES` | `build_user_service` constructs a `UserService`, repository, clients, and event bus. |
| `REFERENCES` | `build_event_bus` passes `on_user_created` as a callback; reports pass formatter functions. |
| `USES_TYPE` | `fetch_user` returns `User`; service constructors annotate their repository and client dependencies. |
| `DECORATED_BY` | `UserService.create` uses the local `traced` decorator; async workflows use `async_traced`. |
| `INHERITS` | `MemoryUserRepository` extends `UserRepository`; `ActiveUserRepository` extends the concrete repository. |
| `OVERRIDES` | `MemoryUserRepository.save` overrides its contract; model, report, job, and plugin methods also override base methods. |
| `RAISES` | `validate_email` raises `ValidationError`; repositories raise `UserNotFound`. |
| `DEFINES_ROUTE` | `/users`, `/users/{user_id}`, `/reports/users`, `/jobs/run`, `/health`, and other routes. |
| `HTTP_REQUEST` | `DirectoryClient.fetch` makes an async GET; `NotificationClient.send_welcome` makes an async POST. |

Additional examples include aliased imports, dotted module calls, package-relative imports, public re-exports, function aliases, forward-reference annotations, `self`/`cls`, `super()`, annotated factory returns, imported configuration constants, and a recursive `batch_users` call.

`plugins.invoke_plugin` selects a method with `getattr`, while the event bus and job runner invoke runtime-selected callbacks. These calls deliberately remain **unresolved** in static analysis; they are valid runtime code, not missing functions. Unresolved is a call status, not an additional relationship type.

## Offline walkthrough

From the repository root:

```powershell
python -B demo_project/run_demo.py
```

This uses only the Python standard library. It seeds an in-memory repository, creates users through a decorated workflow and nested pipeline, publishes events, runs plugins and jobs, batches users recursively, and prints a five-user CSV report. It does not start a server, import FastAPI/httpx, or make network requests.

## Optional API

With FastAPI and uvicorn installed, start the demo on a different port from PyArch:

```powershell
python -m uvicorn app.main:app --app-dir demo_project --port 8001
```

The health, report, job, and seeded-user routes work locally. Outbound integrations additionally require `httpx`; their `example.com` URLs are placeholders, not working user-directory or notification services. Scanning never executes these requests. Configure real integrations before exercising remote-fetch or notification paths.
