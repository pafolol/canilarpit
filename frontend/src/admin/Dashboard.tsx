import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  type AdminGuide,
  type GuideStatus,
  type ResearchJob,
  type TopicRequestRow,
} from "../api";
import { ErrorState, Loading } from "../components";
import { VERDICT_LABEL } from "../data";

const STATUSES: (GuideStatus | "")[] = ["", "draft", "in_review", "published", "archived"];

export default function Dashboard() {
  const [status, setStatus] = useState<GuideStatus | "">("");
  const [guides, setGuides] = useState<AdminGuide[]>([]);
  const [topics, setTopics] = useState<TopicRequestRow[]>([]);
  const [jobs, setJobs] = useState<ResearchJob[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [reloads, setReloads] = useState(0);

  const reload = useCallback(() => setReloads((n) => n + 1), []);

  useEffect(() => {
    let cancelled = false;
    setBusy(true);
    Promise.all([
      api.admin.guides({ status: status || undefined, page_size: 50 }),
      api.admin.topicRequests({ page_size: 12 }),
      api.admin.jobs({ page_size: 8 }),
    ])
      .then(([guidePage, topicPage, jobPage]) => {
        if (cancelled) return;
        setGuides(guidePage.items);
        setTopics(topicPage.items);
        setJobs(jobPage.items);
        setError(null);
      })
      .catch((cause) => !cancelled && setError(cause))
      .finally(() => !cancelled && setBusy(false));
    return () => {
      cancelled = true;
    };
  }, [status, reloads]);

  if (error) return <ErrorState error={error} retry={reload} />;
  if (busy && guides.length === 0) return <Loading what="the catalog" />;

  return (
    <div className="admin__grid">
      <section className="panel panel--wide">
        <div className="panel__head">
          <h2 className="panel__h">Guides</h2>
          <div className="panel__actions">
            {STATUSES.map((value) => (
              <button
                key={value || "all"}
                className="chip"
                aria-pressed={status === value}
                onClick={() => setStatus(value)}
              >
                {value ? value.replace("_", " ") : "all"}
              </button>
            ))}
          </div>
        </div>
        {guides.length === 0 ? (
          <p className="panel__empty">
            Nothing here. <Link to="/admin/generate">Generate one</Link>.
          </p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Title</th>
                <th>Status</th>
                <th>Verdict</th>
                <th>Category</th>
                <th>Draft</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {guides.map((guide) => {
                const document = guide.draft_revision?.document ?? guide.current_revision?.document;
                const verdict = document?.content.larp.verdict;
                return (
                  <tr key={guide.id}>
                    <td>
                      <Link to={`/admin/guides/${guide.id}`}>{guide.title}</Link>
                      <span className="table__slug">{guide.slug}</span>
                    </td>
                    <td>
                      <span className={`pill pill--${guide.status}`}>
                        {guide.status.replace("_", " ")}
                      </span>
                    </td>
                    <td>{verdict ? VERDICT_LABEL[verdict] : "—"}</td>
                    <td>{guide.category.title}</td>
                    <td>
                      {guide.draft_revision
                        ? `r${guide.draft_revision.revision_number} ${guide.draft_revision.status}`
                        : "—"}
                    </td>
                    <td className="table__when">
                      {new Date(guide.updated_at).toLocaleDateString("en-GB")}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </section>

      <section className="panel">
        <div className="panel__head">
          <h2 className="panel__h">Demand</h2>
          <p className="panel__sub">
            What readers asked for and nobody has written. Topics that now have a
            published guide drop off on their own.
          </p>
        </div>
        {topics.length === 0 ? (
          <p className="panel__empty">No unmet requests.</p>
        ) : (
          <ul className="demand">
            {topics.map((topic) => (
              <li key={topic.id}>
                <Link to={`/admin/generate?topic=${encodeURIComponent(topic.topic)}`}>
                  {topic.topic}
                </Link>
                <span className="demand__n">{topic.request_count}</span>
                <button
                  className="demand__drop"
                  aria-label={`Dismiss ${topic.topic}`}
                  title="Dismiss: not worth writing"
                  onClick={() => {
                    api.admin
                      .dismissTopicRequest(topic.id)
                      .then(reload)
                      .catch(() => undefined);
                  }}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel">
        <div className="panel__head">
          <h2 className="panel__h">Recent jobs</h2>
          <button className="chip" onClick={reload}>
            Refresh
          </button>
        </div>
        {jobs.length === 0 ? (
          <p className="panel__empty">No generation runs yet.</p>
        ) : (
          <ul className="jobs">
            {jobs.map((job) => (
              <li key={job.id}>
                <span className={`pill pill--${job.status}`}>{job.status}</span>
                <span className="jobs__topic">{job.topic}</span>
                {job.created_guide_id ? (
                  <Link className="jobs__link" to={`/admin/guides/${job.created_guide_id}`}>
                    open draft
                  </Link>
                ) : job.error_message ? (
                  <span className="jobs__error">{job.error_message.slice(0, 90)}</span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
