import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiError, api, type Submission, type SubmissionStatus } from "../api";
import { ErrorState, Loading } from "../components";
import { isAdmin, useAuth } from "../auth";

const FILTERS: (SubmissionStatus | "")[] = [
  "",
  "pending",
  "drafted",
  "accepted",
  "rejected",
  "spam",
];

type Busy = { id: string; what: string } | null;

/**
 * The queue of reader suggestions.
 *
 * Reviewing one is the only place a stranger's text reaches a model, and it
 * happens because an editor pressed a button. Nothing here publishes: the best
 * a submission does is become a draft with somebody's name on the review.
 */
export default function Submissions() {
  const { account } = useAuth();
  const [status, setStatus] = useState<SubmissionStatus | "">("pending");
  const [rows, setRows] = useState<Submission[]>([]);
  const [busy, setBusy] = useState(true);
  const [working, setWorking] = useState<Busy>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  const reload = useCallback(() => setReloads((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    api.admin
      .submissions({ status: status || undefined, page_size: 50 })
      .then((page) => {
        if (cancelled) return;
        setRows(page.items);
        setError(null);
      })
      .catch((cause) => !cancelled && setError(cause))
      .finally(() => !cancelled && setBusy(false));
    return () => {
      cancelled = true;
    };
  }, [status, reloads]);

  const run = async (row: Submission, what: string, action: () => Promise<unknown>) => {
    setWorking({ id: row.id, what });
    setNotice(null);
    try {
      await action();
      reload();
    } catch (cause) {
      setNotice(cause instanceof ApiError ? cause.message : "That did not work.");
    } finally {
      setWorking(null);
    }
  };

  if (error) return <ErrorState error={error} retry={reload} />;
  if (busy && rows.length === 0) return <Loading what="the queue" />;

  return (
    <section className="panel panel--wide">
      <div className="panel__head">
        <h2 className="panel__h">Submissions</h2>
        <div className="panel__actions">
          {FILTERS.map((value) => (
            <button
              key={value || "all"}
              className="chip"
              aria-pressed={status === value}
              onClick={() => setStatus(value)}
            >
              {value || "all"}
            </button>
          ))}
        </div>
      </div>

      {notice ? (
        <p className="admin__error" role="alert">
          {notice}
        </p>
      ) : null}

      {rows.length === 0 ? (
        <p className="panel__empty">Nothing here.</p>
      ) : (
        <ul className="subs">
          {rows.map((row) => {
            const screening = (row.screening ?? {}) as {
              verdict?: string;
              reason?: string;
              concerns?: string[];
            };
            const doing = working?.id === row.id ? working.what : null;
            return (
              <li className="sub" key={row.id}>
                <div className="sub__head">
                  <span className={`pill pill--${row.status}`}>{row.status}</span>
                  <h3 className="sub__topic">{row.topic}</h3>
                  {row.credit_name ? (
                    <span className="sub__credit">credit: {row.credit_name}</span>
                  ) : null}
                  <span className="sub__when">
                    {new Date(row.created_at).toLocaleDateString("en-GB")}
                  </span>
                </div>

                <p className="sub__notes">{row.notes}</p>

                <p className="sub__meta">
                  {row.guide_type ? <span>{row.guide_type}</span> : null}
                  {row.entry_type ? <span>{row.entry_type}</span> : null}
                  {row.category ? <span>{row.category.title}</span> : null}
                  {row.suggested_category ? (
                    <span className="sub__newcat">
                      suggests “{row.suggested_category}”
                      {isAdmin(account) ? (
                        <button
                          className="chip"
                          disabled={Boolean(doing)}
                          onClick={() =>
                            run(row, "category", async () => {
                              await api.admin.createCategory({
                                name: row.suggested_category as string,
                              });
                              setNotice(`Category “${row.suggested_category}” created.`);
                            })
                          }
                        >
                          Add it
                        </button>
                      ) : null}
                    </span>
                  ) : null}
                </p>

                {screening.verdict ? (
                  <div className={`sub__screen sub__screen--${screening.verdict}`}>
                    <span className="u-label">{screening.verdict}</span> {screening.reason}
                    {screening.concerns?.length ? (
                      <ul className="sub__concerns">
                        {screening.concerns.map((concern) => (
                          <li key={concern}>{concern}</li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : null}

                <div className="sub__actions">
                  {row.status === "pending" ? (
                    <button
                      className="chip chip--ai"
                      disabled={Boolean(doing)}
                      title="Screen it, and write the draft if it passes. This costs money."
                      onClick={() =>
                        run(row, "review", () => api.admin.reviewSubmission(row.id))
                      }
                    >
                      {doing === "review" ? "reviewing…" : "Review with AI"}
                    </button>
                  ) : null}

                  {row.created_guide_id ? (
                    <Link className="chip" to={`/admin/guides/${row.created_guide_id}`}>
                      Open the draft
                    </Link>
                  ) : null}

                  {row.created_guide_id && row.status !== "accepted" && isAdmin(account) ? (
                    <button
                      className="chip chip--go"
                      disabled={Boolean(doing)}
                      onClick={() => run(row, "accept", () => api.admin.acceptSubmission(row.id))}
                    >
                      Accept
                    </button>
                  ) : null}

                  {row.status !== "spam" && row.status !== "rejected" ? (
                    <button
                      className="chip"
                      disabled={Boolean(doing)}
                      onClick={() =>
                        run(row, "reject", () => api.admin.rejectSubmission(row.id, null))
                      }
                    >
                      Reject
                    </button>
                  ) : null}

                  <button
                    className="chip sub__block"
                    disabled={Boolean(doing)}
                    title="Reject and stop this client sending more. Anonymous and reversible."
                    onClick={() => {
                      if (!confirm(`Block whoever sent “${row.topic}”?`)) return;
                      void run(row, "block", () =>
                        api.admin.rejectSubmission(row.id, "Blocked by an editor", true),
                      );
                    }}
                  >
                    Block sender
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
