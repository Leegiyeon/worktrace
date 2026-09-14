export type NetworkCommit = { sha: string; parents: string[]; message: string; committed_at: string | null; url: string | null };
export type NetworkBranch = { name: string; is_default: boolean; head_sha: string | null; commits: NetworkCommit[]; history_truncated: boolean };
export function branchColor(name: string): string;
export function buildBranchNetwork(branches: NetworkBranch[]): {
  nodes: (NetworkCommit & { x: number; y: number; color: string; missingParents: string[] })[];
  edges: { from: string; to: string; color: string; path: string }[];
  labels: { name: string; sha: string; x: number; y: number; nodeY: number; color: string }[];
  width: number; height: number; incomplete: boolean;
};
