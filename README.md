# PyArch Graph

PyArch Graph is a project architecture explorer that runs as a GitHub Pages website or a local FastAPI application. Both modes reuse the same Python AST analyzer without importing or executing project code. The Pages version runs Python inside your browser and can read a selected folder or a public GitHub repository. The lightweight ring interface uses plain HTML, CSS, JavaScript, and inline SVG, without frontend packages or external fonts.

## Architecture

- **Analyzer:** indexes common source, configuration, and documentation files; Python receives multi-pass AST analysis for modules, classes, functions, async functions, methods, decorators, signatures, docstrings, source locations, imports, calls, inheritance, route definitions, and outbound HTTP requests.
- **Graph schema:** file nodes, symbol nodes, external endpoint/library nodes, symbol-level evidence edges, containment edges, and aggregated file-level edges.
- **API:** background jobs, progress polling, node relationship details, safe source retrieval, and JSON export.
- **UI:** circular file layout, searchable files, incoming/outgoing dependencies, symbol summaries, source inspection, pan/zoom controls, themes, and JSON export.

## Relationships

The graph includes containment, imports, calls, class instantiation, function references/callbacks, type annotations (including forward references), decorators, inheritance, method overrides, raised exceptions, routes, and HTTP requests. File-level links aggregate the underlying symbol evidence.

Resolution follows import aliases, dotted module calls, package-relative imports and re-exports, standard `src/` layouts, nested function scopes, `self`/`cls`, inherited methods, `super()`, constructor-assigned instances, annotated parameters, and annotated factory returns. Imported constants and unresolved type aliases retain their defining file dependencies. Unknown dynamic calls remain visibly unresolved rather than being linked to unrelated functions with the same name.

After scanning, select a file in the ring or explorer to inspect its symbols, source, and incoming/outgoing dependencies. Drag to pan, scroll to zoom, and use the percentage button or double-click to reset the view. JSON export includes the full symbol-level graph and relationship evidence.

Use the theme toggle for light or dark mode. Outside inputs, `+` and `-` zoom and `0` resets the view.

## Publish on GitHub Pages

1. Push this project to a GitHub repository with a `main` or `master` branch.
2. In the repository, open **Settings → Pages → Build and deployment**, and set **Source** to **GitHub Actions**.
3. Open **Actions → Deploy GitHub Pages → Run workflow**, or push a commit to `main`/`master`.
4. After deployment completes, open the website URL in the workflow's `github-pages` environment or in **Settings → Pages**.

The included workflow tests the project, builds `_site`, and publishes only the static website, the demo, and the standard-library Python analyzer. Pull requests run the build/tests without publishing. All asset paths are relative, so repository subpaths and custom domains work without a base-URL setting. No server, API key, or GitHub token is required by visitors.

On Pages, **Map project** accepts public GitHub repository URLs. **Choose folder** reads a directory you select; local files are processed on your device, not uploaded. Python analysis runs in a Web Worker using a pinned Pyodide runtime downloaded from jsDelivr on the first scan. The app does not execute analyzed code. **Explore demo** works instantly without loading the Python runtime. Graph inspection, source viewing, JSON export, themes, and zoom work without FastAPI.

Browser scans are limited to 2,000 eligible files, 2 MB per file, and 30 MB total. GitHub's unauthenticated API limits apply; private repositories are not supported in browser mode. Download a repository and choose its folder if you hit a rate limit. For branch names containing `/`, URL-encode the branch name in `/tree/BRANCH/folder`. A browser cannot open a directory from a typed filesystem path: use **Choose folder**, or run the local Python app for server-side scanning.

Preview the exact Pages build locally without installing backend packages:

```powershell
python -B scripts/build_pages.py
python -B -m http.server 8080 --directory _site
```

Open `http://localhost:8080`. Internet access is required to download the browser Python runtime and to scan GitHub repositories. Demo data and the interface are served directly from the site.

## Run locally with FastAPI

From the repository root, install the backend once:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
```

Then start everything with:

```powershell
python app.py
```

The launcher starts FastAPI, serves `frontendlow/index.html`, prints `http://127.0.0.1:8000`, and opens the browser automatically. Enter a local directory such as `demo_project`, or a GitHub URL such as `https://github.com/owner/repo`. GitHub downloads use Git when available, otherwise the archive API. Each scan keeps a separate checkout under `pyarch-repos` in the system temporary directory; remove these checkouts when the server is stopped to reclaim disk space.

## Demo

`demo_project` is a 25-file user-management application covering all 12 relationship types across routes, services, repositories, clients, models, decorators, events, reports, workflows, jobs, and plugins. It includes nested functions, recursion, callbacks, method overrides, package re-exports, and intentionally unresolved dynamic dispatch. See `demo_project/README.md` for the relationship examples and optional API setup.

Run its standard-library-only offline walkthrough without making network requests:

```powershell
python -B demo_project/run_demo.py
```

## Tests

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s backend/tests -v
```

The tests cover the analyzer, background jobs, source access, frontend availability, isolated GitHub checkouts, and offline demo. GitHub tests use mocks and do not access the network.

Browser project-loading tests use Node's built-in test runner (no npm install):

```powershell
node --test frontendlow/tests/*.test.mjs
```

## Safety and limitations

The scanner never imports or executes analyzed code, installs dependencies, follows symlinks outside the root, or sends source to external services. It indexes common text-based project files and skips virtual environments, VCS metadata, caches, build outputs, dependency folders, files matched by `.gitignore`, symlinks, oversized files, binary files, and syntax-error Python files while reporting warnings.

Bindings and receiver types are static approximations, not runtime traces. Conditional rebinding, multiple-inheritance dispatch order, wildcard exports, and arbitrary dynamic factories cannot be fully resolved; external constructor receivers are inferred from class-style names.
