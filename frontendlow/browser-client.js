window.BrowserAnalysis = (() => {
  let cancel = null;

  function analyze(request, onProgress) {
    return new Promise((resolve, reject) => {
      const worker = new Worker(new URL("analysis-worker.mjs", document.baseURI), { type: "module" });
      const timer = setTimeout(() => finish(new Error("Scan timed out. Try a smaller project or the local Python app.")), 180_000);
      function finish(error, result) {
        clearTimeout(timer);
        worker.terminate();
        cancel = null;
        if (error) reject(error);
        else resolve(result);
      }
      cancel = () => finish(new Error("Scan cancelled."));
      worker.onmessage = ({ data }) => {
        if (data.type === "progress") onProgress(data.percent, data.message);
        if (data.type === "complete") finish(null, data);
        if (data.type === "error") finish(new Error(data.message));
      };
      worker.onerror = (event) => {
        event.preventDefault();
        finish(new Error(event.message || "Could not load the browser analyzer. Check your connection and try again."));
      };
      worker.postMessage(request);
    });
  }

  return { analyze, cancel: () => cancel?.() };
})();
