const COLORS = ["#0969da", "#1a7f37", "#bf5700", "#8250df", "#cf222e", "#0a7ea4", "#9a6700", "#a4377a", "#57606a", "#547b1d", "#6654b0", "#007b70", "#b84d57"];

export function branchColor(name) {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return COLORS[hash % COLORS.length];
}

export function buildBranchNetwork(branches) {
  const orderedBranches = [...branches].sort((a, b) => Number(b.is_default) - Number(a.is_default) || a.name.localeCompare(b.name));
  const usedColors = new Set([COLORS[0]]);
  const colors = new Map(orderedBranches.map((branch) => {
    let color = branch.is_default ? COLORS[0] : branchColor(branch.name);
    if (!branch.is_default && usedColors.has(color)) color = COLORS.find((candidate) => !usedColors.has(candidate)) ?? color;
    usedColors.add(color);
    return [branch.name, color];
  }));
  const commits = new Map();
  for (const branch of orderedBranches) {
    for (const commit of branch.commits ?? []) {
      if (!commits.has(commit.sha)) commits.set(commit.sha, { ...commit, parents: [...new Set(commit.parents)] });
    }
  }
  const children = new Map([...commits.keys()].map((sha) => [sha, []]));
  const pending = new Map();
  for (const commit of commits.values()) {
    const known = commit.parents.filter((sha) => commits.has(sha));
    pending.set(commit.sha, known.length);
    for (const parent of known) children.get(parent).push(commit.sha);
  }
  const compare = (a, b) => (commits.get(a).committed_at ?? "").localeCompare(commits.get(b).committed_at ?? "") || a.localeCompare(b);
  const ready = [...commits.keys()].filter((sha) => pending.get(sha) === 0).sort(compare);
  const order = [];
  while (ready.length) {
    const sha = ready.shift();
    order.push(sha);
    for (const child of children.get(sha)) {
      pending.set(child, pending.get(child) - 1);
      if (pending.get(child) === 0) ready.push(child);
    }
    ready.sort(compare);
  }

  // Keep first-parent histories together; second parents retain their own lanes.
  const lanes = [];
  const ownership = new Map();
  function assignChain(head, color) {
    if (!commits.has(head) || ownership.has(head)) return;
    const lane = lanes.length;
    lanes.push({ color, labels: [] });
    let sha = head;
    while (commits.has(sha) && !ownership.has(sha)) {
      ownership.set(sha, lane);
      sha = commits.get(sha).parents[0];
    }
  }
  for (const branch of orderedBranches) assignChain(branch.head_sha, colors.get(branch.name));
  for (const sha of [...order].reverse()) assignChain(sha, COLORS[lanes.length % COLORS.length]);
  for (const branch of orderedBranches) {
    const lane = ownership.get(branch.head_sha);
    if (lane !== undefined) lanes[lane].labels.push(branch);
  }
  let height = 20;
  for (const lane of lanes) {
    lane.top = height;
    lane.y = height + lane.labels.length * 30 + 28;
    height = lane.y + 48;
  }
  const nodes = order.map((sha, index) => {
    const commit = commits.get(sha);
    const lane = lanes[ownership.get(sha)];
    return { ...commit, x: 36 + index * 44, y: lane.y, color: lane.color, missingParents: commit.parents.filter((parent) => !commits.has(parent)) };
  });
  const bySha = new Map(nodes.map((node) => [node.sha, node]));
  const edges = nodes.flatMap((node) => node.parents.filter((sha) => bySha.has(sha)).map((sha) => {
    const parent = bySha.get(sha);
    const mid = (parent.x + node.x) / 2;
    return { from: sha, to: node.sha, color: node.parents[0] === sha ? node.color : parent.color, path: `M ${parent.x} ${parent.y} C ${mid} ${parent.y}, ${mid} ${node.y}, ${node.x} ${node.y}` };
  }));
  const labels = lanes.flatMap((lane) => lane.labels.map((branch, index) => ({ name: branch.name, sha: branch.head_sha, x: bySha.get(branch.head_sha).x, y: lane.top + index * 30, nodeY: lane.y, color: colors.get(branch.name) })));
  return { nodes, edges, labels, width: Math.max(720, nodes.length * 44 + 300), height: Math.max(140, height), incomplete: branches.some((branch) => branch.history_truncated || !bySha.has(branch.head_sha)) || nodes.some((node) => node.missingParents.length > 0) };
}
