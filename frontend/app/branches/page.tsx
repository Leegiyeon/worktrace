"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";

import type { ProjectSummary, RepositorySource } from "../projects/types";
import { BranchActivityGraph } from "../projects/[projectId]/BranchActivityGraph";
import styles from "./page.module.css";

export default function BranchesPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState("");
  const [projectsError, setProjectsError] = useState("");
  const [repositoryError, setRepositoryError] = useState("");
  const [repository, setRepository] = useState<RepositorySource | null>(null);
  const [isLoadingProjects, setIsLoadingProjects] = useState(true);
  const [isLoadingRepository, setIsLoadingRepository] = useState(false);
  const [projectsAttempt, setProjectsAttempt] = useState(0);
  const [repositoryAttempt, setRepositoryAttempt] = useState(0);
  const selectedProjectIdRef = useRef("");

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/projects", { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("프로젝트를 불러오지 못했습니다.");
        return (await response.json()) as ProjectSummary[];
      })
      .then((payload) => {
        if (controller.signal.aborted) return;
        const currentProjectId = selectedProjectIdRef.current;
        const nextProjectId = currentProjectId && payload.some((project) => project.id === currentProjectId) ? currentProjectId : payload[0]?.id ?? "";
        setProjects(payload);
        setSelectedProjectId(nextProjectId);
        selectedProjectIdRef.current = nextProjectId;
        if (!nextProjectId) {
          setRepository(null);
          setRepositoryError("");
          setIsLoadingRepository(false);
        } else if (nextProjectId !== currentProjectId) {
          setRepository(null);
          setRepositoryError("");
          setIsLoadingRepository(true);
        }
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted) setProjectsError(reason instanceof Error ? reason.message : "프로젝트를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoadingProjects(false);
      });
    return () => controller.abort();
  }, [projectsAttempt]);

  useEffect(() => {
    if (!selectedProjectId) return;

    const controller = new AbortController();
    fetch(`/api/projects/${selectedProjectId}/repository`, { cache: "no-store", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error("저장소 연결 정보를 불러오지 못했습니다.");
        return (await response.json()) as RepositorySource | null;
      })
      .then((payload) => {
        if (!controller.signal.aborted && selectedProjectIdRef.current === selectedProjectId) setRepository(payload);
      })
      .catch((reason: unknown) => {
        if (!controller.signal.aborted && selectedProjectIdRef.current === selectedProjectId) setRepositoryError(reason instanceof Error ? reason.message : "저장소 연결 정보를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!controller.signal.aborted && selectedProjectIdRef.current === selectedProjectId) setIsLoadingRepository(false);
      });
    return () => controller.abort();
  }, [selectedProjectId, repositoryAttempt]);

  const selectedProject = useMemo(
    () => projects.find((project) => project.id === selectedProjectId) ?? null,
    [projects, selectedProjectId]
  );

  const selectProject = (projectId: string) => {
    selectedProjectIdRef.current = projectId;
    setSelectedProjectId(projectId);
    setRepository(null);
    setRepositoryError("");
    setIsLoadingRepository(Boolean(projectId));
  };

  const retryProjects = () => {
    setIsLoadingProjects(true);
    setProjectsError("");
    setProjectsAttempt((value) => value + 1);
  };

  const retryRepository = () => {
    if (!selectedProjectId) return;
    setRepository(null);
    setRepositoryError("");
    setIsLoadingRepository(true);
    setRepositoryAttempt((value) => value + 1);
  };

  return (
    <main className={`page-shell project-page ${styles.shell}`} aria-label="브랜치 그래프">
      <header className={styles.header}>
        <h1>브랜치 그래프</h1>
        <div className={styles.controls}>
          <label className={styles.projectField}>
            <span>프로젝트</span>
            <select
              value={selectedProjectId}
              onChange={(event) => selectProject(event.target.value)}
              disabled={isLoadingProjects || projects.length === 0}
            >
              {projects.map((project) => <option key={project.id} value={project.id}>{project.title}</option>)}
            </select>
          </label>
          {selectedProject ? <Link className={styles.projectLink} href={`/projects/${selectedProject.id}`}>프로젝트 열기</Link> : null}
          {isLoadingProjects ? <span className={styles.status} role="status">프로젝트를 불러오는 중입니다.</span> : null}
        </div>
      </header>

      {projectsError ? (
        <div className={`alert error ${styles.alert}`} role="alert">
          <span>{projectsError}</span>
          <button type="button" onClick={retryProjects}>다시 불러오기</button>
        </div>
      ) : null}

      {!isLoadingProjects && !projectsError && projects.length === 0 ? <div className="empty-state">표시할 프로젝트가 없습니다.</div> : null}

      {selectedProject ? (
        <>
          {isLoadingRepository ? <div className="empty-state" role="status">저장소 연결 정보를 불러오는 중입니다.</div> : null}

          {repositoryError ? (
            <div className={`alert error ${styles.alert}`} role="alert">
              <span>{repositoryError}</span>
              <button type="button" onClick={retryRepository}>다시 불러오기</button>
            </div>
          ) : null}

          {!isLoadingRepository && !repositoryError && !repository ? <div className="empty-state">연결된 GitHub 저장소가 없습니다.</div> : null}

          {!isLoadingRepository && !repositoryError && repository ? (
            <BranchActivityGraph
              projectId={selectedProject.id}
              projectName={selectedProject.title}
              repositoryName={repository.full_name}
            />
          ) : null}
        </>
      ) : null}
    </main>
  );
}
