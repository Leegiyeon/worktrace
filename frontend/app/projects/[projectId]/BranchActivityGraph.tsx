"use client";

import { useEffect, useMemo, useState } from "react";

type BranchActivityPoint = {
  date: string;
  commits: number;
};

type GitHubBranchActivity = {
  name: string;
  is_default: boolean;
  ahead_by: number;
  behind_by: number;
  status: string;
  latest_commit_at: string | null;
  activity: BranchActivityPoint[];
};

type Props = {
  projectId: string;
  repositoryName: string | null;
};

function branchStatusLabel(branch: GitHubBranchActivity) {
  if (branch.is_default) return "기준 브랜치";
  if (branch.ahead_by > 0 && branch.behind_by > 0) return "분기 진행 중";
  if (branch.ahead_by > 0) return "작업 진행 중";
  if (branch.behind_by > 0) return "기준 브랜치 추종 필요";
  return "차이 없음";
}

function formatLatest(value: string | null) {
  if (!value) return "고유 커밋 없음";
  return new Intl.DateTimeFormat("ko-KR", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function Sparkline({ points }: { points: BranchActivityPoint[] }) {
  const width = 260;
  const height = 58;
  const max = Math.max(1, ...points.map((point) => point.commits));
  const coordinates = points.map((point, index) => {
    const x = points.length <= 1 ? 0 : (index / (points.length - 1)) * width;
    const y = height - (point.commits / max) * (height - 8) - 4;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");

  const total = points.reduce((sum, point) => sum + point.commits, 0);
  return (
    <div className="branch-sparkline-wrap" aria-label={`최근 30일 고유 커밋 ${total}개`}>
      <svg className="branch-sparkline" role="img" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none">
        <polyline points={coordinates} />
      </svg>
      <small>최근 30일 {total}개</small>
    </div>
  );
}

export function BranchActivityGraph({ projectId, repositoryName }: Props) {
  const [branches, setBranches] = useState<GitHubBranchActivity[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!repositoryName) {
      setBranches([]);
      return;
    }
    const controller = new AbortController();
    setIsLoading(true);
    setError("");
    fetch(`/api/projects/${projectId}/branch-activity`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("브랜치 활동을 불러오지 못했습니다.");
        return (await response.json()) as GitHubBranchActivity[];
      })
      .then((payload) => setBranches(payload))
      .catch((reason: unknown) => {
        if (controller.signal.aborted) return;
        setError(reason instanceof Error ? reason.message : "브랜치 활동을 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
    return () => controller.abort();
  }, [projectId, repositoryName]);

  const maxAhead = useMemo(() => Math.max(1, ...branches.map((branch) => branch.ahead_by)), [branches]);
  const workBranches = branches.filter((branch) => !branch.is_default);

  return (
    <section className="panel branch-activity-panel">
      <div className="panel-title-row">
        <div>
          <h2>작업 브랜치 그래프</h2>
          <small>{repositoryName ?? "연결된 저장소 없음"}</small>
        </div>
        <span className="count-badge">{workBranches.length}개 작업 브랜치</span>
      </div>
      {!repositoryName ? <div className="empty-state">GitHub 저장소를 먼저 연결하세요.</div> : null}
      {isLoading ? <div className="empty-state">브랜치 활동을 계산하는 중입니다.</div> : null}
      {error ? <div className="alert error" role="alert">{error}</div> : null}
      {!isLoading && !error && repositoryName && branches.length === 0 ? <div className="empty-state">표시할 작업 브랜치가 없습니다.</div> : null}
      <div className="branch-graph-list">
        {branches.map((branch) => (
          <article className="branch-graph-row" key={branch.name}>
            <div className="branch-graph-heading">
              <div>
                <strong>{branch.name}</strong>
                <small>{branchStatusLabel(branch)} · 최근 {formatLatest(branch.latest_commit_at)}</small>
              </div>
              <div className="branch-graph-badges">
                {!branch.is_default ? <span className="count-badge">ahead {branch.ahead_by}</span> : null}
                {!branch.is_default ? <span className="count-badge">behind {branch.behind_by}</span> : null}
              </div>
            </div>
            <div className="branch-ahead-track" aria-label={`${branch.name} 기준 브랜치 대비 고유 커밋 ${branch.ahead_by}개`}>
              <span style={{ width: branch.is_default ? "100%" : `${Math.max(branch.ahead_by > 0 ? 6 : 0, (branch.ahead_by / maxAhead) * 100)}%` }} />
            </div>
            <Sparkline points={branch.activity} />
          </article>
        ))}
      </div>
      {branches.length > 0 ? <p className="muted branch-graph-note">작업 브랜치 막대는 기준 브랜치 대비 고유 커밋 수를, 선 그래프는 최근 30일 고유 커밋 흐름을 나타냅니다.</p> : null}
    </section>
  );
}
