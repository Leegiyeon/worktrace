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
type Props = { projectId: string; repositoryName: string | null; projectName?: string };

function formatTime(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "날짜 미확인" : new Intl.DateTimeFormat("ko-KR", { dateStyle: "short", timeStyle: "short" }).format(date);
}

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
  const [compact, setCompact] = useState(true);
  const [viewportWidth, setViewportWidth] = useState(720);
  const [labelWidths, setLabelWidths] = useState<Record<string, number>>({});
  const [selectedSha, setSelectedSha] = useState<string | null>(null);
  const container = useRef<HTMLDivElement>(null);
  const graph = useMemo(() => buildBranchNetwork(branches, { compact, viewportWidth, labelWidths }), [branches, compact, viewportWidth, labelWidths]);
  const branchDetails = useRef<HTMLDetailsElement>(null);
  const canvas = useRef<HTMLDivElement>(null);
  const selectedNode = graph.nodes.find((node) => node.sha === selectedSha) ?? graph.nodes.find((node) => branches.some((branch) => branch.is_default && branch.head_sha === node.sha)) ?? graph.nodes.at(-1);
  useEffect(() => {
    let cancelled = false;
    const measure = () => {
      const context = document.createElement("canvas").getContext("2d");
      if (!context || !container.current || cancelled) return;
      context.font = `600 12px ${getComputedStyle(container.current).fontFamily}`;
      setLabelWidths(Object.fromEntries(branches.map((branch) => [branch.name, Math.ceil(context.measureText(branch.name).width)])));
    };
    void document.fonts.ready.then(measure);
    return () => { cancelled = true; };
  }, [branches]);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(([entry]) => setViewportWidth(Math.max(240, Math.floor(entry.contentRect.width))));
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (canvas.current) canvas.current.scrollLeft = compact ? 0 : Math.max(0, (graph.nodes.at(-1)?.x ?? 0) - canvas.current.clientWidth * 0.85);
  }, [graph, compact]);

  return <div className={styles.graphBody} ref={container}>
    <div className={styles.toolbar}>
      <div className={styles.modes} role="group" aria-label="커밋 표시 범위">
        <button type="button" aria-pressed={compact} onClick={() => setCompact(true)}>요약</button>
        <button type="button" aria-pressed={!compact} onClick={() => setCompact(false)}>전체 커밋</button>
      </div>
      <small>{graph.totalCommits}개 커밋{compact ? ` · 주요 지점 ${graph.nodes.length}개` : ""}</small>
    </div>
    {graph.nodes.length === 0 ? <div className="empty-state">표시할 커밋 이력이 없습니다.</div> : <div className={`${styles.canvas} ${compact ? styles.summaryCanvas : ""}`} ref={canvas} tabIndex={0} role="region" aria-label="커밋 네트워크">
      <svg className={styles.network} width={graph.width} height={graph.height} aria-label="브랜치 병합 네트워크">
        {graph.edges.map((edge) => <path key={`${edge.from}-${edge.to}`} className={styles.branchLine} d={edge.path} stroke={edge.color} strokeDasharray={edge.collapsedCommits ? "4 2" : undefined}><title>{edge.collapsedCommits ? `중간 커밋 ${edge.collapsedCommits}개` : "부모 커밋 연결"}</title></path>)}
        {graph.nodes.map((node) => <g key={node.sha}>
          {node.missingParents.length > 0 ? <path d={`M ${node.x - 18} ${node.y} H ${node.x}`} stroke={node.color} strokeDasharray="3 3"><title>이전 부모 커밋은 조회 범위 밖입니다.</title></path> : null}
          <g role="button" tabIndex={0} aria-pressed={selectedNode?.sha === node.sha} aria-label={`${node.sha.slice(0, 7)} ${node.message}`} onClick={() => setSelectedSha(node.sha)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); setSelectedSha(node.sha); } }}>
            <title>{`${node.sha.slice(0, 7)} · ${node.message}\n${node.committed_at ?? "날짜 미확인"}${node.parents.length > 1 ? " · 병합 커밋" : ""}`}</title>
            <circle className={styles.hitTarget} cx={node.x} cy={node.y} r={Math.min(12, graph.spacing / 2)} />
            <circle className={styles.commitNode} cx={node.x} cy={node.y} r={node.parents.length > 1 ? 6 : 4} fill={node.color} />
          </g>
        </g>)}
        {graph.labels.map((label) => <g className={styles.branchLabel} key={label.name}>
          <path d={`M ${Math.min(label.left + label.width - 8, Math.max(label.left + 8, label.x))} ${label.y + 22} L ${label.x} ${label.nodeY - 7}`} stroke={label.color} strokeDasharray="2 3" />
          <foreignObject x={label.left} y={label.y} width={label.width} height="23">
            <button type="button" className={styles.headLabel} style={{ borderColor: label.color, color: label.color }} title={`${label.refs.map((ref) => ref.name).join(", ")} · ${label.sha}`} aria-label={`${label.refs.map((ref) => ref.name).join(", ")} 브랜치 상태`} onClick={() => { setSelectedSha(label.sha); if (branchDetails.current) branchDetails.current.open = true; }}>
              <span className={styles.swatch} style={{ backgroundColor: label.color }} /><span className={styles.labelText}>{label.name}</span>
              {label.refs.length > 1 ? <span className={styles.refCount}>+{label.refs.length - 1}</span> : null}
            </button>
          </foreignObject>
        </g>)}
      </svg>
    </div>}
    {selectedNode ? <div className={styles.commitDetail} aria-live="polite">
      <div className={styles.commitMeta}><code>{selectedNode.sha.slice(0, 7)}</code><span>{selectedNode.parents.length > 1 ? "병합 커밋" : "커밋"}</span>{selectedNode.committed_at ? <time dateTime={selectedNode.committed_at}>{formatTime(selectedNode.committed_at)}</time> : null}</div>
      <p title={selectedNode.message}>{selectedNode.message.split("\n")[0] || "커밋 메시지 없음"}</p>
      {commitLink(selectedNode.url) ? <a href={commitLink(selectedNode.url)} target="_blank" rel="noreferrer">GitHub에서 보기</a> : null}
    </div> : null}
    {graph.incomplete || branches.some((branch) => branch.branch_list_truncated) ? <p className={styles.note}>일부 이력 표시 · {branches.some((branch) => branch.branch_list_truncated) ? "브랜치 최대 13개 · " : ""}브랜치별 최대 100개 커밋</p> : null}
    <details className={styles.branchDetails} ref={branchDetails}>
      <summary>브랜치별 상태 <span>{branches.length}</span></summary>
      <div className={styles.legend} aria-label="브랜치별 병합 상태">
      {branches.map((branch) => <div className={styles.legendItem} key={branch.name}>
        <span className={styles.swatch} style={{ backgroundColor: graph.labels.flatMap((label) => label.refs).find((ref) => ref.name === branch.name)?.color ?? branchColor(branch.name) }} />
        <div><strong>{branch.name}</strong><small>{branch.head_sha?.slice(0, 7) ?? "HEAD 미확인"} · {branchStatusLabel(branch)}</small></div>
        <span className={styles.distance}>ahead {branch.ahead_by} · behind {branch.behind_by}</span>
      </div>)}
      </div>
    </details>
  </div>;
}

function BranchNetworkLoader({ projectId, repositoryName, projectName }: Props) {
  const [branches, setBranches] = useState<GitHubBranchActivity[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [fetchedAt, setFetchedAt] = useState<string | null>(null);

  useEffect(() => {
    if (!repositoryName) return;
    const controller = new AbortController();
    fetch(`/api/projects/${projectId}/branch-activity`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("브랜치 이력을 불러오지 못했습니다.");
        return (await response.json()) as GitHubBranchActivity[];
      })
      .then((payload) => { if (!controller.signal.aborted) { setBranches(payload); setError(""); setFetchedAt(new Date().toISOString()); } })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "브랜치 이력을 불러오지 못했습니다.");
      })
      .finally(() => { if (!controller.signal.aborted) { setLoaded(true); setRefreshing(false); } });
    return () => controller.abort();
  }, [projectId, repositoryName, attempt]);

  return <section className={styles.panel} aria-busy={Boolean(repositoryName) && (!loaded || refreshing)}>
    <div className={styles.titleRow}>
      <div><h2>{projectName ?? "브랜치 병합 네트워크"}</h2><small>{repositoryName ?? "연결된 저장소 없음"}</small></div>
      {repositoryName ? <button className={styles.refresh} type="button" disabled={!loaded || refreshing} aria-label="브랜치 새로고침" title="GitHub에서 다시 조회" onClick={() => { setError(""); setRefreshing(true); setAttempt((value) => value + 1); }}><span aria-hidden="true">&#x21bb;</span></button> : null}
    </div>
    {fetchedAt ? <div className={styles.source}><span>GitHub API · 기준 {branches.find((branch) => branch.is_default)?.name ?? "미확인"}</span><span>{branches.length}개 브랜치 · {refreshing ? "조회 중" : `조회 ${formatTime(fetchedAt)}`}</span></div> : null}
    {!repositoryName ? <div className="empty-state">연결된 GitHub 저장소가 없습니다.</div> : null}
    {repositoryName && (!loaded || (refreshing && !fetchedAt)) ? <div className="empty-state" role="status">커밋 이력을 불러오는 중입니다.</div> : null}
    {error ? <div className={`alert error ${styles.error}`} role="alert">{error}{fetchedAt ? " 이전 조회 결과입니다." : ""}</div> : null}
    {loaded && !refreshing && !error && repositoryName && branches.length === 0 ? <div className="empty-state">표시할 브랜치가 없습니다.</div> : null}
    {loaded && branches.length > 0 ? <NetworkGraph branches={branches} /> : null}
  </section>;
}

export function BranchActivityGraph(props: Props) {
  return <BranchNetworkLoader key={`${props.projectId}:${props.repositoryName}`} {...props} />;
}
