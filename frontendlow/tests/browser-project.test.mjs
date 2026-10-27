import assert from "node:assert/strict";
import { test } from "node:test";
import { parseGitHub, readProject, safePath, selectFiles } from "../browser-project.mjs";

const manifest = {
  extensions: [".py", ".js", ".md"],
  filenames: ["README"],
  excluded: [".git", ".venv", "node_modules"],
  maxFiles: 3,
  maxBytes: 1000,
  maxTotalBytes: 2000,
};

test("GitHub URLs support default branches, explicit refs, and subfolders", () => {
  assert.deepEqual(parseGitHub("https://github.com/owner/repo.git/"), { owner: "owner", repo: "repo", ref: undefined, folder: "" });
  assert.deepEqual(parseGitHub("github.com/owner/repo/tree/feature%2Fui/src/app"), { owner: "owner", repo: "repo", ref: "feature/ui", folder: "src/app" });
  for (const value of ["C:\\project", "https://example.com/owner/repo", "https://github.com/owner/repo/issues", "https://user:pass@github.com/owner/repo", "https://github.com/owner/repo/tree/main/%2e%2e/secret"]) {
    assert.throws(() => parseGitHub(value));
  }
});

test("file paths cannot escape the virtual project", () => {
  assert.equal(safePath("src\\main.py"), "src/main.py");
  for (const path of ["../main.py", "/main.py", "src/../../main.py", "src//main.py", "C:/main.py", "bad\0.py"]) assert.throws(() => safePath(path));
});

test("source selection excludes dependencies, secrets, binaries, and oversized files", () => {
  const files = ["main.py", ".gitignore", ".env", "image.png", "node_modules/index.js", "tests/test_main.py", "large.py"].map((path) => ({ path, size: path === "large.py" ? 1001 : 10 }));
  assert.deepEqual(selectFiles(files, manifest, ["tests"]).map((file) => file.path), [".gitignore", "main.py"]);
});

test("browser projects enforce file-count and aggregate-size limits", () => {
  assert.throws(() => selectFiles([], manifest), /No supported/);
  assert.throws(() => selectFiles(Array.from({ length: 4 }, (_, index) => ({ path: `file${index}.py`, size: 10 })), manifest), /up to 3 files/);
  assert.throws(() => selectFiles(Array.from({ length: 3 }, (_, index) => ({ path: `file${index}.py`, size: 900 })), manifest), /30 MB/);
});

test("local folder sources are read without making network requests", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = () => { throw new Error("Local files must not be uploaded"); };
  try {
    const project = await readProject({ files: [{ name: "main.py", webkitRelativePath: "my-project/main.py", size: 4, arrayBuffer: async () => new TextEncoder().encode("pass").buffer }] }, manifest);
    assert.equal(project.name, "my-project");
    assert.equal(project.content[0].path, "main.py");
    assert.equal(new TextDecoder().decode(project.content[0].data), "pass");
  } finally {
    globalThis.fetch = original;
  }
});

test("GitHub downloads pin sources to a commit and exclude symlinks", async () => {
  const original = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url) => {
    requests.push(url);
    if (url.endsWith("/repos/owner/repo")) return Response.json({ default_branch: "main" });
    if (url.includes("/commits/")) return Response.json({ sha: "commit-sha", commit: { tree: { sha: "tree-sha" } } });
    if (url.includes("/git/trees/")) return Response.json({ truncated: false, tree: [
      { path: "src/main.py", type: "blob", mode: "100644", size: 4 },
      { path: "src/link.py", type: "blob", mode: "120000", size: 4 },
      { path: "outside.py", type: "blob", mode: "100644", size: 4 },
    ] });
    assert.equal(url, "https://raw.githubusercontent.com/owner/repo/commit-sha/src/main.py");
    return new Response("pass");
  };
  try {
    const project = await readProject({ path: "https://github.com/owner/repo/tree/main/src" }, manifest);
    assert.equal(project.content.length, 1);
    assert.equal(project.content[0].path, "main.py");
    assert.equal(requests.length, 4);
  } finally {
    globalThis.fetch = original;
  }
});

test("rate limits and incomplete GitHub trees give actionable errors", async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response("", { status: 403 });
    await assert.rejects(readProject({ path: "github.com/owner/repo" }, manifest), /rate limit/);
    globalThis.fetch = async (url) => {
      if (url.includes("/git/trees/")) return Response.json({ truncated: true });
      if (url.includes("/commits/")) return Response.json({ commit: { tree: { sha: "tree" } } });
      return Response.json({ default_branch: "main" });
    };
    await assert.rejects(readProject({ path: "github.com/owner/repo" }, manifest), /incomplete file tree/);
  } finally {
    globalThis.fetch = original;
  }
});
