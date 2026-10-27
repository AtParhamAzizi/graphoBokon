import { readProject } from "./browser-project.mjs";

const RUNTIME = "https://cdn.jsdelivr.net/pyodide/v314.0.7/full/";

self.onmessage = async ({ data: request }) => {
  const progress = (percent, message) => self.postMessage({ type: "progress", percent, message });
  try {
    const manifestResponse = await fetch(new URL("manifest.json", import.meta.url));
    if (!manifestResponse.ok) throw new Error("Browser analyzer assets are missing. Rebuild the Pages site.");
    const project = await readProject(request, await manifestResponse.json(), progress);
    progress(45, "Loading browser Python runtime (first scan may take a moment)");
    const { loadPyodide } = await import(`${RUNTIME}pyodide.mjs`);
    const python = await loadPyodide({ indexURL: RUNTIME });
    python.FS.mkdirTree("/app/backend");
    for (const module of ["__init__.py", "analyzer.py", "language_readers.py"]) {
      const response = await fetch(new URL(`python/backend/${module}`, import.meta.url));
      if (!response.ok) throw new Error(`Could not load analyzer module ${module}.`);
      python.FS.writeFile(`/app/backend/${module}`, await response.text());
    }
    python.FS.mkdirTree("/project");
    for (const file of project.content) {
      const target = `/project/${file.path}`;
      python.FS.mkdirTree(target.slice(0, target.lastIndexOf("/")));
      python.FS.writeFile(target, file.data);
    }
    python.globals.set("_exclusions_json", JSON.stringify(request.exclusions || []));
    python.globals.set("_progress", (index, total, message) => progress(60 + Math.round(index / Math.max(total, 1) * 39), message));
    const result = JSON.parse(python.runPython(`
import json
import sys
sys.path.insert(0, '/app')
from backend.analyzer import analyze_directory
json.dumps(analyze_directory('/project', json.loads(_exclusions_json), _progress))
`));
    result.root = project.name;
    result.source_url = request.files ? null : request.path;
    const sources = Object.fromEntries(result.nodes.filter((node) => node.kind === "file").map((node) => [node.path, python.FS.readFile(`/project/${node.path}`, { encoding: "utf8" })]));
    progress(100, "Analysis complete");
    self.postMessage({ type: "complete", result, sources });
  } catch (error) {
    self.postMessage({ type: "error", message: error.message || "Browser analysis failed." });
  }
};
