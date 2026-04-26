import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, Trash2, Download, RefreshCw, Search } from "lucide-react";
import { clearSiteLogs, getSiteLogs, logAudit } from "@/lib/siteLogger";

function formatTs(iso) {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

export default function LogsPage() {
  const [entries, setEntries] = useState(() => getSiteLogs());
  const [filterLevel, setFilterLevel] = useState("all");
  const [query, setQuery] = useState("");
  const queryDebounceRef = useRef(null);

  const reloadFromStore = useCallback(() => setEntries(getSiteLogs()), []);

  const manualRefresh = useCallback(() => {
    reloadFromStore();
    logAudit("logs:viewer", "Manual refresh control activated", { entryCount: getSiteLogs().length });
  }, [reloadFromStore]);

  useEffect(() => {
    logAudit("logs:viewer", "Session logs viewer opened", {
      entryCount: getSiteLogs().length,
      path: typeof window !== "undefined" ? window.location.pathname : "/logs",
    });
  }, []);

  useEffect(() => {
    const onLog = () => reloadFromStore();
    const onClear = () => setEntries([]);
    window.addEventListener("site-log", onLog);
    window.addEventListener("site-log-cleared", onClear);
    return () => {
      window.removeEventListener("site-log", onLog);
      window.removeEventListener("site-log-cleared", onClear);
    };
  }, [reloadFromStore]);

  useEffect(() => () => clearTimeout(queryDebounceRef.current), []);

  const levels = useMemo(() => {
    const s = new Set(entries.map((e) => e.level));
    return ["all", ...Array.from(s).sort()];
  }, [entries]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return entries.filter((e) => {
      if (filterLevel !== "all" && e.level !== filterLevel) return false;
      if (!q) return true;
      const hay = `${e.message} ${e.source} ${e.detail || ""}`.toLowerCase();
      return hay.includes(q);
    });
  }, [entries, filterLevel, query]);

  const handleClear = () => {
    if (!window.confirm("Clear all session logs for this tab?")) {
      logAudit("logs:viewer", "Clear logs cancelled at confirmation dialog");
      return;
    }
    const n = entries.length;
    logAudit("logs:viewer", "Session logs cleared after operator confirmation", { clearedCount: n });
    clearSiteLogs();
    setEntries([]);
  };

  const handleExport = () => {
    logAudit("logs:viewer", "Export JSON control activated", { rowCount: entries.length });
    const blob = new Blob([JSON.stringify(entries, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `flight-right-logs-${new Date().toISOString().slice(0, 19)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div
      className="min-h-screen"
      style={{
        fontFamily: "'Geist Variable', system-ui, sans-serif",
        background: "var(--bg-base)",
        color: "var(--text-primary)",
      }}
    >
      <header
        className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-3 border-b px-4 py-3 sm:px-6"
        style={{
          background: "var(--bg-panel-alt)",
          borderColor: "var(--border-default)",
        }}
      >
        <div className="flex min-w-0 items-center gap-3">
          <Link
            to="/"
            onClick={() => logAudit("logs:viewer", "Navigate to dashboard from logs header", { to: "/" })}
            className="inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium transition-colors hover:bg-[var(--bg-raised)]"
            style={{ borderColor: "var(--border-default)", color: "var(--text-secondary)" }}
          >
            <ArrowLeft className="h-4 w-4 shrink-0" />
            Dashboard
          </Link>
          <h1 className="truncate text-lg font-semibold sm:text-xl">Session logs</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={manualRefresh}
            className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-xs font-semibold uppercase tracking-wide transition-colors hover:bg-[var(--bg-raised)]"
            style={{ borderColor: "var(--border-default)", color: "var(--text-secondary)" }}
          >
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </button>
          <button
            type="button"
            onClick={handleExport}
            disabled={entries.length === 0}
            className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-xs font-semibold uppercase tracking-wide transition-colors hover:bg-[var(--bg-raised)] disabled:opacity-40"
            style={{ borderColor: "var(--border-default)", color: "var(--teal)" }}
          >
            <Download className="h-3.5 w-3.5" />
            Export JSON
          </button>
          <button
            type="button"
            onClick={handleClear}
            disabled={entries.length === 0}
            className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-xs font-semibold uppercase tracking-wide transition-colors hover:bg-[var(--bg-raised)] disabled:opacity-40"
            style={{ borderColor: "var(--border-red)", color: "var(--red)" }}
          >
            <Trash2 className="h-3.5 w-3.5" />
            Clear
          </button>
        </div>
      </header>

      <div className="mx-auto max-w-6xl px-4 py-4 sm:px-6 sm:py-6">
        <p className="mb-4 text-sm leading-relaxed" style={{ color: "var(--text-secondary)" }}>
          Logs are stored in <strong style={{ color: "var(--text-primary)" }}>sessionStorage</strong> for this tab
          only (console, toasts, errors, mock activity, and <strong style={{ color: "var(--text-primary)" }}>audit</strong>{" "}
          events). They clear when you close the tab.
        </p>

        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2"
              style={{ color: "var(--text-muted)" }}
            />
            <input
              type="search"
              value={query}
              onChange={(e) => {
                const v = e.target.value;
                setQuery(v);
                clearTimeout(queryDebounceRef.current);
                queryDebounceRef.current = setTimeout(() => {
                  const t = v.trim();
                  logAudit("logs:viewer", "Search query settled", {
                    charCount: t.length,
                    preview: t.slice(0, 256),
                  });
                }, 650);
              }}
              placeholder="Search message, source, detail…"
              className="w-full rounded-md border py-2.5 pl-10 pr-3 text-sm outline-none ring-0 focus:border-[var(--amber)]"
              style={{
                background: "var(--bg-panel)",
                borderColor: "var(--border-default)",
                color: "var(--text-primary)",
              }}
            />
          </div>
          <label className="flex items-center gap-2 text-sm" style={{ color: "var(--text-secondary)" }}>
            <span className="shrink-0 font-medium">Level</span>
            <select
              value={filterLevel}
              onChange={(e) => {
                const v = e.target.value;
                setFilterLevel(v);
                logAudit("logs:viewer", "Log level filter changed", { level: v });
              }}
              className="rounded-md border px-2 py-2 text-sm"
              style={{
                background: "var(--bg-panel)",
                borderColor: "var(--border-default)",
                color: "var(--text-primary)",
              }}
            >
              {levels.map((lv) => (
                <option key={lv} value={lv}>
                  {lv}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div
          className="panel overflow-hidden rounded-md"
          style={{ borderColor: "var(--border-default)" }}
        >
          <div
            className="panel-header flex items-center justify-between"
            style={{ borderBottomColor: "var(--amber)" }}
          >
            <span className="font-display text-[12px] tracking-widest" style={{ color: "var(--text-primary)" }}>
              ENTRIES ({filtered.length}
              {filtered.length !== entries.length ? ` / ${entries.length}` : ""})
            </span>
          </div>
          <div className="max-h-[calc(100vh-16rem)] overflow-auto">
            {filtered.length === 0 ? (
              <p className="p-8 text-center text-sm" style={{ color: "var(--text-muted)" }}>
                No log lines match your filters.
              </p>
            ) : (
              <table className="w-full border-collapse text-left text-sm">
                <thead
                  className="sticky top-0 z-[1]"
                  style={{ background: "var(--bg-panel-alt)" }}
                >
                  <tr className="border-b" style={{ borderColor: "var(--border-default)" }}>
                    <th className="whitespace-nowrap px-3 py-2 font-semibold" style={{ color: "var(--text-muted)" }}>
                      Time
                    </th>
                    <th className="whitespace-nowrap px-3 py-2 font-semibold" style={{ color: "var(--text-muted)" }}>
                      Level
                    </th>
                    <th className="whitespace-nowrap px-3 py-2 font-semibold" style={{ color: "var(--text-muted)" }}>
                      Source
                    </th>
                    <th className="px-3 py-2 font-semibold" style={{ color: "var(--text-muted)" }}>
                      Message
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {[...filtered].reverse().map((e) => (
                    <tr
                      key={e.id}
                      className="border-b align-top"
                      style={{ borderColor: "var(--border-default)" }}
                    >
                      <td
                        className="whitespace-nowrap px-3 py-2 font-mono text-xs tabular-nums"
                        style={{ color: "var(--text-muted)" }}
                      >
                        {formatTs(e.ts)}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs font-semibold uppercase" style={{ color: "var(--amber)" }}>
                        {e.level}
                      </td>
                      <td className="whitespace-nowrap px-3 py-2 text-xs" style={{ color: "var(--teal)" }}>
                        {e.source}
                      </td>
                      <td className="px-3 py-2 break-words" style={{ color: "var(--text-primary)" }}>
                        <div>{e.message}</div>
                        {e.detail && (
                          <pre
                            className="mt-1 max-h-32 overflow-auto rounded border p-2 text-xs leading-snug"
                            style={{
                              background: "var(--bg-base)",
                              borderColor: "var(--border-default)",
                              color: "var(--text-secondary)",
                            }}
                          >
                            {e.detail}
                          </pre>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
