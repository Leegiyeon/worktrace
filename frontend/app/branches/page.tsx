"use client";

import { useEffect, useState } from "react";

import type { ProjectSummary, RepositorySource } from "../projects/types";
import { BranchActivityGraph } from "../projects/[projectId]/BranchActivityGraph";

type ProjectBranchSource = {
  project: ProjectSummary;
  repository: RepositorySource | null;
};

export default function BranchesPage() {
  const [items, setItems] = useState<ProjectBranchSource[]>([]);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/projects", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("프로젝트를 불러오지 못했습니다.");
        return (await response.json()) as ProjectSummary[];
      })
      .then(async (projects) => {
        const sources = await Promise.all(projects.map(async (project) => {
          const response = await fetch(`/api/projects/${project.id}/repository`, { cache: "no-store" });
          const repository = response.ok ? ((await response.json()) as RepositorySource | null) : null;
          return { project, repository };
        }));
        if (!cancelled) setItems(sources);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : "브랜치 데이터를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => { cancelled = true; };
  }, []);

  return (
    <main className="page-shell project-page">
      <div className="dashboard-topbar">
        <div>
          <span className="eyebrow">GITHUB BRANCH ACTIVITY</span>
          <h1>브랜치 그래프</h1>
        </div>
      </div>
      {error ? <div className="alert error" role="alert">{error}</div> : null}
      {isLoading ? <div className="panel empty-state">브랜치 그래프를 준비하는 중입니다.</div> : null}
      {!isLoading && !error ? (
        <div className="stacked-section">
          {items.map(({ project, repository }) => (
            <section className="stacked-section" key={project.id}>
              <div className="panel-title-row">
                <div>
                  <h2>{project.title}</h2>
                  <small>프로젝트 진척 {project.progress_percent}%</small>
                </div>
              </div>
              <BranchActivityGraph projectId={project.id} repositoryName={repository?.full_name ?? null} />
            </section>
          ))}
        </div>
      ) : null}
    </main>
  );
}
