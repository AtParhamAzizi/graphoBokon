export function safePath(value) {
  const path = value.replaceAll("\\", "/");
  if (!path || path.split("/").some((part) => !part || part === "." || part === "..") || path.includes("\0") || path.includes(":")) {
    throw new Error("Invalid project file path.");
  }
  return path;
}

export function parseGitHub(value) {
  if (/(?:^|\/)(?:\.|%2e){1,2}(?:\/|$)/i.test(value)) throw new Error("Invalid GitHub project path.");
  let url;
  try {
    url = new URL(/^https?:\/\//i.test(value) ? value : `https://${value}`);
  } catch {
    throw new Error("Enter a public GitHub repository URL, or use Choose folder.");
  }
  if (!["https:", "http:"].includes(url.protocol) || !["github.com", "www.github.com"].includes(url.hostname) || url.username || url.password || url.port) {
    throw new Error("Enter a public GitHub repository URL, or use Choose folder.");
  }
  const parts = url.pathname.replace(/\/$/, "").slice(1).split("/").map(decodeURIComponent);
  const [owner, originalRepo, section, ref, ...folder] = parts;
  const repo = originalRepo?.replace(/\.git$/, "");
  if (!owner || !repo || !/^[\w.-]+$/.test(owner) || !/^[\w.-]+$/.test(repo) || [owner, repo].some((part) => part === "." || part === "..") || (section && (section !== "tree" || !ref))) {
    throw new Error("Use github.com/owner/repo or github.com/owner/repo/tree/branch/folder.");
  }
  return { owner, repo, ref, folder: folder.length ? safePath(folder.join("/")) : "" };
}

export function selectFiles(entries, manifest, exclusions = []) {
  const excluded = new Set([...manifest.excluded, ...exclusions]);
  const selected = entries.filter((entry) => {
    const path = safePath(entry.path);
    const parts = path.split("/");
    const name = parts.at(-1);
    const extension = name.includes(".") ? `.${name.split(".").at(-1).toLowerCase()}` : "";
    return !parts.some((part) => excluded.has(part)) && !excluded.has(path) && entry.size <= manifest.maxBytes && (path === ".gitignore" || manifest.filenames.includes(name) || manifest.extensions.includes(extension));
  }).sort((first, second) => first.path.localeCompare(second.path));
  if (!selected.some((entry) => entry.path !== ".gitignore")) throw new Error("No supported source files found. Check the folder and exclusions.");
  if (selected.length > manifest.maxFiles) throw new Error(`Browser scans support up to ${manifest.maxFiles} files. Choose a smaller folder or add exclusions.`);
  if (selected.reduce((total, entry) => total + entry.size, 0) > manifest.maxTotalBytes) throw new Error("Project exceeds the 30 MB browser scan limit. Choose a smaller folder or use the local Python app.");
  return selected;
}

async function request(url, json = true) {
  const response = await fetch(url, { credentials: "omit", referrerPolicy: "no-referrer", signal: AbortSignal.timeout(30_000) });
  if (!response.ok) {
    if (response.status === 403 || response.status === 429) throw new Error("GitHub rate limit reached. Try later, or download the repository and use Choose folder.");
    if (response.status === 404) throw new Error("Repository, branch, or file not found. Only public GitHub repositories are supported in the browser.");
    throw new Error(`Could not load project (${response.status}).`);
  }
  return json ? response.json() : response;
}

async function readBounded(response, maximum) {
  const reader = response.body.getReader();
  const chunks = [];
  let length = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      length += value.length;
      if (length > maximum) throw new Error("A repository file exceeds the browser size limit.");
      chunks.push(value);
    }
  } finally {
    await reader.cancel();
  }
  const data = new Uint8Array(length);
  let offset = 0;
  for (const chunk of chunks) {
    data.set(chunk, offset);
    offset += chunk.length;
  }
  return data;
}

export async function readProject({ path, files, exclusions = [] }, manifest, progress = () => {}) {
  let entries;
  let name;
  let commit;
  let repository;
  if (files) {
    name = files[0]?.webkitRelativePath.split("/")[0] || "project";
    entries = files.map((file) => ({ path: safePath(file.webkitRelativePath.split("/").slice(1).join("/") || file.name), size: file.size, file }));
  } else {
    repository = parseGitHub(path);
    const base = `https://api.github.com/repos/${repository.owner}/${repository.repo}`;
    progress(5, "Reading public GitHub repository");
    const metadata = await request(base);
    commit = await request(`${base}/commits/${encodeURIComponent(repository.ref || metadata.default_branch)}`);
    const tree = await request(`${base}/git/trees/${commit.commit.tree.sha}?recursive=1`);
    if (tree.truncated) throw new Error("GitHub returned an incomplete file tree. Download the repository and choose a smaller folder instead.");
    const prefix = repository.folder ? `${repository.folder}/` : "";
    entries = tree.tree.filter((entry) => entry.type === "blob" && entry.mode !== "120000" && entry.path.startsWith(prefix)).map((entry) => ({ path: safePath(entry.path.slice(prefix.length)), size: entry.size }));
    name = repository.repo;
  }
  const selected = selectFiles(entries, manifest, exclusions);
  const content = new Array(selected.length);
  let next = 0;
  let complete = 0;
  let totalBytes = 0;
  async function readNext() {
    while (next < selected.length) {
      const index = next++;
      const entry = selected[index];
      let data;
      if (entry.file) {
        data = new Uint8Array(await entry.file.arrayBuffer());
      } else {
        const relative = [repository.folder, entry.path].filter(Boolean).join("/").split("/").map(encodeURIComponent).join("/");
        const response = await request(`https://raw.githubusercontent.com/${repository.owner}/${repository.repo}/${commit.sha}/${relative}`, false);
        data = await readBounded(response, manifest.maxBytes);
      }
      totalBytes += data.length;
      if (totalBytes > manifest.maxTotalBytes) throw new Error("Project exceeds the 30 MB browser scan limit.");
      content[index] = { path: entry.path, data };
      complete += 1;
      progress(10 + Math.round(complete / selected.length * 35), `Reading ${entry.path}`);
    }
  }
  await Promise.all(Array.from({ length: Math.min(6, selected.length) }, readNext));
  return { name, content };
}
