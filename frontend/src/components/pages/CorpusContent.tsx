"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getAllCorpusVersions, getAllEvaluations, uploadCorpus } from "@/lib/data";
import { formatDate, riskScoreColor } from "@/lib/utils";
import StatusBadge from "@/components/shared/StatusBadge";
import type { CorpusVersion, Evaluation } from "@/lib/types";

const ACCEPTED_TYPES = ".yml,.yaml";

export default function CorpusContent() {
  const [corpusVersions, setCorpusVersions] = useState<CorpusVersion[]>([]);
  const [allEvaluations, setAllEvaluations] = useState<Evaluation[]>([]);
  const [expandedVersion, setExpandedVersion] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const refresh = useCallback(async () => {
    const [versions, evaluations] = await Promise.all([
      getAllCorpusVersions(),
      getAllEvaluations(),
    ]);
    setCorpusVersions(versions);
    setAllEvaluations(evaluations);
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      const [versions, evaluations] = await Promise.all([
        getAllCorpusVersions(),
        getAllEvaluations(),
      ]);
      if (!cancelled) {
        setCorpusVersions(versions);
        setAllEvaluations(evaluations);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const handleUploadClick = () => {
    setUploadError(null);
    setUploadSuccess(null);
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    if (!file.name.endsWith(".yml") && !file.name.endsWith(".yaml")) {
      setUploadError("Please select a YAML file (.yml or .yaml)");
      return;
    }
    setUploading(true);
    setUploadError(null);
    setUploadSuccess(null);
    try {
      const result = await uploadCorpus(file);
      setUploadSuccess(
        `Uploaded corpus "${result.version_id}" with ${result.chunk_count} chunk(s). Evaluations will now use this corpus.`
      );
      await refresh();
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-5 max-w-[1200px] animate-fade-in">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text-light-primary dark:text-text-primary">Corpus Versions</h1>
          <p className="text-[13px] text-text-light-secondary dark:text-text-secondary mt-0.5">
            Registered regulatory corpus releases used for compliance evaluations
          </p>
        </div>
        <div className="flex flex-col gap-2">
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_TYPES}
            className="hidden"
            onChange={handleFileChange}
          />
          <button
            type="button"
            onClick={handleUploadClick}
            disabled={uploading}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-accent text-white text-[13px] font-medium hover:bg-accent/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {uploading ? (
              <>
                <svg className="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Uploading…
              </>
            ) : (
              <>
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-8l-4-4m0 0L8 8m4-4v12" />
                </svg>
                Upload corpus
              </>
            )}
          </button>
          {uploadError && (
            <p className="text-[12px] text-red-500 dark:text-red-400" role="alert">
              {uploadError}
            </p>
          )}
          {uploadSuccess && (
            <p className="text-[12px] text-green-600 dark:text-green-400" role="status">
              {uploadSuccess}
            </p>
          )}
        </div>
      </div>

      <div className="space-y-2">
        {corpusVersions.map((cv, i) => {
          const relatedEvals = allEvaluations.filter((e) => e.corpus_version === cv.version_id);
          const isExpanded = expandedVersion === cv.version_id;
          const isLatest = i === 0;

          return (
            <div
              key={cv.version_id}
              className={`card overflow-hidden animate-slide-up ${isLatest ? "border-l-[3px] border-l-accent" : ""}`}
              style={{ animationDelay: `${i * 60}ms`, animationFillMode: "backwards" }}
            >
              <button
                onClick={() => setExpandedVersion(isExpanded ? null : cv.version_id)}
                className="w-full flex items-center gap-4 px-4 py-3.5 text-[13px] hover:bg-bg-light-hover dark:hover:bg-bg-hover transition-colors text-left"
              >
                <svg className={`w-3.5 h-3.5 text-text-light-muted dark:text-text-muted transition-transform duration-200 shrink-0 ${isExpanded ? "rotate-90" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="m8.25 4.5 7.5 7.5-7.5 7.5" />
                </svg>
                <div className="flex items-center gap-2 min-w-[180px]">
                  <span className="mono font-semibold text-text-light-primary dark:text-text-primary">{cv.version_id}</span>
                  {isLatest && (
                    <span className="px-1.5 py-px text-[9px] font-bold uppercase tracking-wider rounded bg-accent/10 text-accent dark:text-accent-secondary border border-accent/20">Latest</span>
                  )}
                </div>
                <span className="text-text-light-secondary dark:text-text-secondary hidden md:block flex-1 truncate">{cv.source_set}</span>
                <span className="text-text-light-muted dark:text-text-muted whitespace-nowrap text-[12px]">{formatDate(cv.released_at)}</span>
                <span className="text-[11px] text-text-light-muted dark:text-text-muted whitespace-nowrap min-w-[60px] text-right tabular-nums">
                  {relatedEvals.length} eval{relatedEvals.length !== 1 ? "s" : ""}
                </span>
              </button>

              {isExpanded && (
                <div className="px-4 pb-4 animate-slide-down">
                  <p className="md:hidden text-[12px] text-text-light-secondary dark:text-text-secondary mb-3 ml-7">{cv.source_set}</p>
                  {relatedEvals.length > 0 ? (
                    <div className="ml-7 rounded-lg border border-border-light dark:border-border-dark overflow-hidden">
                      <table className="w-full text-[12px]">
                        <thead>
                          <tr className="bg-bg-light-elevated dark:bg-white/2 border-b border-border-light dark:border-border-dark">
                            <th className="text-left py-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted">Feature</th>
                            <th className="text-left py-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted">Decision</th>
                            <th className="text-left py-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted">Risk</th>
                            <th className="text-left py-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-text-light-muted dark:text-text-muted">Date</th>
                          </tr>
                        </thead>
                        <tbody>
                          {relatedEvals.map((ev, j) => (
                            <tr key={`${ev.feature_id}-${j}`} className="border-b border-border-light dark:border-border-dark last:border-b-0 hover:bg-bg-light-hover dark:hover:bg-bg-hover transition-colors">
                              <td className="py-2 px-3 font-medium text-text-light-primary dark:text-text-primary">{ev.feature_id}</td>
                              <td className="py-2 px-3"><StatusBadge decision={ev.decision} /></td>
                              <td className={`py-2 px-3 font-bold tabular-nums ${riskScoreColor(ev.risk_score)}`}>{ev.risk_score}</td>
                              <td className="py-2 px-3 text-text-light-muted dark:text-text-muted">{formatDate(ev.evaluated_at)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p className="ml-7 text-[12px] text-text-light-muted dark:text-text-muted py-2">No evaluations ran against this corpus version</p>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
