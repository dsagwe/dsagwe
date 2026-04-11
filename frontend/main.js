const { useEffect, useMemo, useState } = React;

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  let value = bytes;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i++;
  }
  return `${value.toFixed(1)} ${units[i]}`;
}

function iconFor(ext) {
  if (ext.includes("pdf")) return "📕";
  if (ext.includes("xls")) return "📗";
  return "📄";
}

function App() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState([]);
  const [facets, setFacets] = useState({ types: [], folders: [], tags: [] });
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState(null);
  const [darkMode, setDarkMode] = useState(false);
  const [sort, setSort] = useState("relevance");
  const [view, setView] = useState("list");
  const [history, setHistory] = useState([]);
  const [savedSearches, setSavedSearches] = useState([]);
  const [total, setTotal] = useState(0);
  const [filters, setFilters] = useState({ file_types: [], folders: [], tags: [] });
  const [indexStatus, setIndexStatus] = useState({});
  const [indexFolders, setIndexFolders] = useState("/workspace");

  useEffect(() => {
    document.documentElement.classList.toggle("dark", darkMode);
  }, [darkMode]);

  useEffect(() => {
    const timer = setInterval(loadIndexStatus, 2000);
    loadIndexStatus();
    loadHistory();
    loadSavedSearches();
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    const keyHandler = (e) => {
      if (e.ctrlKey && e.key.toLowerCase() === "f") {
        e.preventDefault();
        document.getElementById("searchBox")?.focus();
      }
      if (e.key === "Escape") setQuery("");
      if (e.ctrlKey && e.key.toLowerCase() === "o" && selected) {
        window.open(`file://${selected.path}`);
      }
      if (e.ctrlKey && e.key.toLowerCase() === "c" && selected?.matches?.[0]) {
        navigator.clipboard.writeText(selected.matches[0].content || "");
      }
    };
    window.addEventListener("keydown", keyHandler);
    return () => window.removeEventListener("keydown", keyHandler);
  }, [selected]);

  async function loadIndexStatus() {
    const r = await fetch("/api/index/status");
    setIndexStatus(await r.json());
  }

  async function loadHistory() {
    const r = await fetch("/api/search_history");
    const d = await r.json();
    setHistory(d.history || []);
  }

  async function loadSavedSearches() {
    const r = await fetch("/api/saved_searches");
    const d = await r.json();
    setSavedSearches(d.items || []);
  }

  async function runSearch(overrideQuery = query) {
    setLoading(true);
    const payload = { query: overrideQuery, sort, view, ...filters };
    const r = await fetch("/api/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await r.json();
    setResults(data.results || []);
    setFacets(data.facets || { types: [], folders: [], tags: [] });
    setTotal(data.total || 0);
    if (data.results?.length) setSelected(data.results[0]);
    setLoading(false);
    loadHistory();
  }

  async function triggerIndex() {
    await fetch("/api/index", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ folders: indexFolders.split(",").map((s) => s.trim()) }),
    });
    loadIndexStatus();
  }

  async function clearIndex() {
    await fetch("/api/index/clear", { method: "POST" });
    setResults([]);
    setSelected(null);
    loadIndexStatus();
  }

  async function saveCurrentSearch() {
    const name = prompt("Name this search");
    if (!name) return;
    await fetch("/api/saved_searches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name, query, filters }),
    });
    loadSavedSearches();
  }

  const resultClasses = view === "grid" ? "grid grid-cols-2 gap-2" : "space-y-2";

  return (
    <div className="min-h-screen text-slate-800 dark:text-slate-100">
      <header className="sticky top-0 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700 p-3 flex gap-2 items-center z-20">
        <h1 className="font-bold text-xl mr-3">DocFind</h1>
        <input id="searchBox" value={query} onChange={(e) => setQuery(e.target.value)} onKeyUp={() => runSearch()} placeholder="Search with boolean, phrase, wildcard, fuzzy..." className="flex-1 p-2 rounded border dark:bg-slate-700" />
        <button onClick={() => runSearch()} className="px-3 py-2 rounded bg-blue-600 text-white">Search</button>
        <button onClick={() => setDarkMode((d) => !d)} className="px-3 py-2 rounded bg-slate-200 dark:bg-slate-700">{darkMode ? "Light" : "Dark"}</button>
      </header>

      <div className="grid grid-cols-12 min-h-[calc(100vh-64px)]">
        <aside className="col-span-3 border-r border-slate-200 dark:border-slate-700 p-3 space-y-4 overflow-auto">
          <section>
            <h2 className="font-semibold">Indexing</h2>
            <input value={indexFolders} onChange={(e) => setIndexFolders(e.target.value)} className="w-full p-2 rounded border mt-1 text-sm dark:bg-slate-700" placeholder="comma-separated folders" />
            <div className="flex gap-2 mt-2">
              <button onClick={triggerIndex} className="text-sm px-2 py-1 bg-green-600 text-white rounded">Reindex Now</button>
              <button onClick={clearIndex} className="text-sm px-2 py-1 bg-rose-700 text-white rounded">Clear Index</button>
            </div>
            <div className="text-xs mt-2 space-y-1">
              <div>Status: {indexStatus.running ? "Running" : "Idle"}</div>
              <div>Progress: {indexStatus.processed || 0}/{indexStatus.total || 0}</div>
              <div>Last Indexed: {indexStatus.last_indexed_time || "-"}</div>
              <div>Total Files: {indexStatus.total_files_indexed || 0}</div>
              <div>Index Size: {formatBytes(indexStatus.index_size_bytes || 0)}</div>
            </div>
          </section>

          <section>
            <h2 className="font-semibold">Filters</h2>
            <div className="mt-1 text-sm">
              <div className="font-medium">File Type</div>
              {(facets.types || []).map((t) => (
                <label key={t.extension} className="block">
                  <input type="checkbox" checked={filters.file_types.includes(t.extension)} onChange={(e) => {
                    const next = e.target.checked ? [...filters.file_types, t.extension] : filters.file_types.filter((x) => x !== t.extension);
                    setFilters({ ...filters, file_types: next });
                    setTimeout(() => runSearch(), 0);
                  }} /> {t.extension} ({t.c})
                </label>
              ))}
            </div>
            <div className="mt-2 text-sm">
              <div className="font-medium">Folders</div>
              {(facets.folders || []).slice(0,8).map((f) => (
                <label className="block" key={f.folder}>
                  <input type="checkbox" checked={filters.folders.includes(f.folder)} onChange={(e) => {
                    const next = e.target.checked ? [...filters.folders, f.folder] : filters.folders.filter((x) => x !== f.folder);
                    setFilters({ ...filters, folders: next });
                    setTimeout(() => runSearch(), 0);
                  }} /> {f.folder} ({f.count})
                </label>
              ))}
            </div>
          </section>

          <section>
            <h2 className="font-semibold">Saved Searches</h2>
            <button className="text-xs px-2 py-1 rounded bg-indigo-600 text-white my-1" onClick={saveCurrentSearch}>Save Current</button>
            <div className="text-xs space-y-1 max-h-28 overflow-auto">
              {savedSearches.map((s) => <button key={s.id} className="block underline" onClick={() => { setQuery(s.query); runSearch(s.query); }}>{s.name}</button>)}
            </div>
          </section>

          <section>
            <h2 className="font-semibold">Recent Queries</h2>
            <div className="text-xs max-h-40 overflow-auto space-y-1">
              {history.map((h, i) => <button key={i} className="block underline" onClick={() => { setQuery(h.query); runSearch(h.query); }}>{h.query} · {new Date(h.created_at).toLocaleString()}</button>)}
            </div>
          </section>
        </aside>

        <main className="col-span-5 p-3 border-r border-slate-200 dark:border-slate-700 overflow-auto">
          <div className="flex items-center justify-between mb-2">
            <div className="text-sm">{total} files matched</div>
            <div className="flex gap-2">
              <select className="text-sm border rounded p-1 dark:bg-slate-700" value={sort} onChange={(e) => { setSort(e.target.value); setTimeout(() => runSearch(), 0); }}>
                <option value="relevance">Relevance</option>
                <option value="name_asc">File name A-Z</option>
                <option value="date_modified">Date modified</option>
                <option value="file_size">File size</option>
              </select>
              <button className="text-sm px-2 py-1 border rounded" onClick={() => setView(view === "list" ? "grid" : "list")}>{view === "list" ? "Grid" : "List"}</button>
              <a href={`/api/export?q=${encodeURIComponent(query)}`} className="text-sm px-2 py-1 border rounded">Export CSV</a>
            </div>
          </div>

          {loading ? (
            <div className="space-y-2">{Array.from({ length: 6 }).map((_, i) => <div key={i} className="skeleton h-20 rounded" />)}</div>
          ) : results.length === 0 ? (
            <div className="p-6 border rounded bg-white dark:bg-slate-800 text-sm">
              No results found. Try a broader search term, remove active filters, or reindex your folders.
            </div>
          ) : (
            <div className={resultClasses}>
              {results.map((r) => (
                <div key={r.file_id} onClick={() => setSelected(r)} className={`p-3 rounded border bg-white dark:bg-slate-800 cursor-pointer ${selected?.file_id === r.file_id ? "ring-2 ring-blue-500" : ""}`}>
                  <div className="flex items-center justify-between text-sm">
                    <div>{iconFor(r.extension)} <span className="font-semibold">{r.name}</span></div>
                    <div className="text-xs">score: {r.score.toFixed(2)}</div>
                  </div>
                  <div className="text-xs text-slate-500 truncate">{r.path}</div>
                  <div className="text-xs mt-1">{formatBytes(r.size)} · {new Date(r.modified_at).toLocaleString()} · matches: {r.match_count}</div>
                  <div className="text-sm mt-2" dangerouslySetInnerHTML={{ __html: r.matches?.[0]?.snippet || "" }} />
                  <div className="mt-2 flex gap-1 text-xs">
                    <button className="px-2 py-1 border rounded" onClick={(e) => { e.stopPropagation(); navigator.clipboard.writeText(r.matches?.[0]?.content || ""); }}>Copy Snippet</button>
                    <button className="px-2 py-1 border rounded" onClick={(e) => { e.stopPropagation(); window.open(`file://${r.path}`); }}>Open File</button>
                    <button className="px-2 py-1 border rounded" onClick={async (e) => { e.stopPropagation(); const tag = prompt("Tag"); if (tag) await fetch(`/api/files/${r.file_id}/tag`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tag }) }); }}>Add Tag</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </main>

        <section className="col-span-4 p-3 overflow-auto">
          <h2 className="font-semibold mb-2">Preview</h2>
          {!selected ? (
            <div className="text-sm text-slate-500">Select a result to preview.</div>
          ) : (
            <div className="space-y-2">
              <div className="p-3 rounded border bg-white dark:bg-slate-800">
                <div className="font-semibold">{selected.name}</div>
                <div className="text-xs text-slate-500 break-all">{selected.path}</div>
                <div className="text-xs mt-1">Type: {selected.extension} | {formatBytes(selected.size)} | Author: {selected.author || "-"}</div>
                <div className="mt-2 text-xs">
                  <strong>Match navigation:</strong> Match 1 of {selected.matches?.length || 0} (use arrows in list)
                </div>
              </div>

              <div className="p-3 rounded border bg-white dark:bg-slate-800">
                <div className="font-medium text-sm mb-1">Matches</div>
                <div className="space-y-2 max-h-[60vh] overflow-auto">
                  {(selected.matches || []).map((m, i) => (
                    <div key={i} className="text-sm border rounded p-2">
                      <div className="text-xs text-slate-500 mb-1">{m.ref}</div>
                      <div dangerouslySetInnerHTML={{ __html: m.snippet }} />
                    </div>
                  ))}
                </div>
              </div>

              <div className="p-3 rounded border bg-white dark:bg-slate-800">
                <button className="px-2 py-1 border rounded text-sm" onClick={() => window.open(`file://${selected.path}`)}>Open Externally</button>
              </div>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
