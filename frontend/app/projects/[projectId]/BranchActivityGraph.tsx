"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { branchColor, buildBranchNetwork, type NetworkBranch } from "../../../lib/branch-network.mjs";
import styles from "./BranchActivityGraph.module.css";

type GitHubBranchActivity = NetworkBranch & {
  status: string;
  branch_list_truncated?: boolean;
  ahead_by: number;
  behind_by: number;
  latest_commit_at: string | null;
};
type Props = { projectId: string; repositoryName: string | null };

function branchStatusLabel(branch: GitHubBranchActivity) {
  if (branch.is_default) return "기준 브랜치";
  if (branch.status === "unknown") return "비교 상태 미확인";
  if (branch.ahead_by > 0 && branch.behind_by > 0) return "분기 진행 중";
  if (branch.ahead_by > 0) return "병합 대기";
  if (branch.behind_by > 0) return "기준 브랜치에 포함";
  return "기준 브랜치와 동일 커밋";
}

function commitLink(url: string | null) {
  if (!url) return undefined;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" && parsed.hostname === "github.com" ? url : undefined;
  } catch { return undefined; }
}

function NetworkGraph({ branches }: { branches: GitHubBranchActivity[] }) {
  const graph = useMemo(() => buildBranchNetwork(branches), [branches]);
  const canvas = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (canvas.current) canvas.current.scrollLeft = Math.max(0, (graph.nodes.at(-1)?.x ?? 0) - canvas.current.clientWidth * 0.45);
  }, [graph]);

  return <>
    {graph.nodes.length === 0 ? <div className="empty-state">표시할 커밋 이력이 없습니다.</div> : <div className={styles.canvas} ref={canvas} tabIndex={0} role="region" aria-label="커밋 네트워크">
      <svg className={styles.network} width={graph.width} height={graph.height} aria-label="브랜치 병합 네트워크">
        {graph.edges.map((edge) => <path key={`${edge.from}-${edge.to}`} className={styles.branchLine} d={edge.path} stroke={edge.color} />)}
        {graph.nodes.map((node) => <g key={node.sha}>
          {node.missingParents.length > 0 ? <path d={`M ${node.x - 18} ${node.y} H ${node.x}`} stroke={node.color} strokeDasharray="3 3"><title>이전 부모 커밋은 조회 범위 밖입니다.</title></path> : null}
          <a href={commitLink(node.url)} target="_blank" rel="noreferrer" aria-label={`${node.sha.slice(0, 7)} ${node.message}`}>
            <title>{`${node.sha.slice(0, 7)} · ${node.message}\n${node.committed_at ?? "날짜 미확인"}${node.parents.length > 1 ? " · 병합 커밋" : ""}`}</title>
            <circle className={styles.hitTarget} cx={node.x} cy={node.y} r="12" />
            <circle className={styles.commitNode} cx={node.x} cy={node.y} r={node.parents.length > 1 ? 6 : 4} fill={node.color} />
          </a>
        </g>)}
        {graph.labels.map((label) => <g className={styles.branchLabel} key={label.name}>
          <path d={`M ${label.x} ${label.y + 25} V ${label.nodeY - 8}`} stroke={label.color} strokeDasharray="2 3" />
          <foreignObject x={label.x - 8} y={label.y} width="270" height="26">
            <span className={styles.headLabel} style={{ borderColor: label.color, color: label.color }} title={`${label.name} · ${label.sha}`}>
              <span className={styles.swatch} style={{ backgroundColor: label.color }} /><span className={styles.labelText}>{label.name}</span>
            </span>
          </foreignObject>
        </g>)}
      </svg>
    </div>}
    {graph.incomplete ? <p className={styles.note}>최근 커밋 일부만 표시됩니다. 조회 범위 밖의 분기·병합 관계는 생략됩니다.</p> : null}
    {branches.some((branch) => branch.branch_list_truncated) ? <p className={styles.note}>브랜치 목록은 기준 브랜치 포함 최대 13개까지 표시됩니다.</p> : null}
    <div className={styles.legend} aria-label="브랜치별 병합 상태">
      {branches.map((branch) => <div className={styles.legendItem} key={branch.name}>
        <span className={styles.swatch} style={{ backgroundColor: graph.labels.find((label) => label.name === branch.name)?.color ?? branchColor(branch.name) }} />
        <div><strong>{branch.name}</strong><small>{branch.head_sha?.slice(0, 7) ?? "HEAD 미확인"} · {branchStatusLabel(branch)}</small></div>
        <span className={styles.distance}>ahead {branch.ahead_by} · behind {branch.behind_by}</span>
      </div>)}
    </div>
  </>;
}

function BranchNetworkLoader({ projectId, repositoryName }: Props) {
  const [branches, setBranches] = useState<GitHubBranchActivity[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!repositoryName) return;
    const controller = new AbortController();
    fetch(`/api/projects/${projectId}/branch-activity`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("브랜치 이력을 불러오지 못했습니다.");
        return (await response.json()) as GitHubBranchActivity[];
      })
      .then((payload) => { if (!controller.signal.aborted) { setBranches(payload); setError(""); } })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "브랜치 이력을 불러오지 못했습니다.");
      })
      .finally(() => { if (!controller.signal.aborted) setLoaded(true); });
    return () => controller.abort();
  }, [projectId, repositoryName, attempt]);

  return <section className={`panel ${styles.panel}`}>
    <div className={styles.titleRow}>
      <div><h2>브랜치 병합 네트워크</h2><small>{repositoryName ?? "연결된 저장소 없음"}</small></div>
      {loaded && !error ? <span className="count-badge">{branches.filter((branch) => !branch.is_default).length}개 작업 브랜치</span> : null}
    </div>
    {!repositoryName ? <div className="empty-state">연결된 GitHub 저장소가 없습니다.</div> : null}
    {repositoryName && !loaded ? <div className="empty-state" role="status">커밋 이력을 불러오는 중입니다.</div> : null}
    {error ? <div className={`alert error ${styles.error}`} role="alert">{error}<button type="button" onClick={() => { setError(""); setLoaded(false); setAttempt((value) => value + 1); }}>다시 불러오기</button></div> : null}
    {loaded && !error && repositoryName && branches.length === 0 ? <div className="empty-state">표시할 브랜치가 없습니다.</div> : null}
    {loaded && !error && branches.length > 0 ? <NetworkGraph branches={branches} /> : null}
  </section>;
}

export function BranchActivityGraph(props: Props) {
  return <BranchNetworkLoader key={`${props.projectId}:${props.repositoryName}`} {...props} />;
}
