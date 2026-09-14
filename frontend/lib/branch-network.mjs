const COLORS = ["#0969da", "#1a7f37", "#bf5700", "#8250df", "#cf222e", "#0a7ea4", "#9a6700", "#a4377a", "#57606a", "#547b1d", "#6654b0", "#007b70", "#b84d57"];

export function branchColor(name) {
  let hash = 0;
  for (const char of name) hash = (hash * 31 + char.charCodeAt(0)) >>> 0;
  return COLORS[hash % COLORS.length];
}

export function buildBranchNetwork(branches, { compact = false, viewportWidth = 720, labelWidths = {} } = {}) {
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
  const visible = new Set(order);
  if (compact) {
    const heads = new Set(branches.map((branch) => branch.head_sha));
    const mergeParents = new Set([...commits.values()].filter((commit) => commit.parents.length > 1).flatMap((commit) => commit.parents));
    for (const sha of order) {
      const commit = commits.get(sha);
      if (!heads.has(sha) && !mergeParents.has(sha) && commit.parents.length === 1 && commits.has(commit.parents[0]) && children.get(sha).length === 1) visible.delete(sha);
    }
  }
  const visibleOrder = order.filter((sha) => visible.has(sha));
  const width = compact ? Math.max(240, Math.min(viewportWidth, 40 + Math.max(0, visibleOrder.length - 1) * 28)) : Math.max(240, 40 + Math.max(0, visibleOrder.length - 1) * 24);
  const spacing = compact ? Math.min(28, (width - 40) / Math.max(1, visibleOrder.length - 1)) : 24;
  const indexBySha = new Map(order.map((sha, index) => [sha, index]));
  const tracks = [];
  for (let laneIndex = 0; laneIndex < lanes.length; laneIndex++) {
    const lane = lanes[laneIndex];
    const owned = order.filter((sha) => ownership.get(sha) === laneIndex);
    // Include connecting fork/merge endpoints so reused tracks never overlap.
    const extent = owned.flatMap((sha) => [sha, ...commits.get(sha).parents, ...children.get(sha)]).filter((sha) => indexBySha.has(sha)).map((sha) => indexBySha.get(sha));
    const start = Math.min(...extent);
    const end = Math.max(...extent);
    const track = lane.labels.length === 0 ? tracks.find((candidate) => candidate.labels.length === 0 && candidate.intervals.every(([left, right]) => end <= left || start >= right)) : undefined;
    if (track) {
      track.intervals.push([start, end]);
      lane.track = track;
    } else {
      const next = { labels: lane.labels, intervals: [[start, end]] };
      tracks.push(next);
      lane.track = next;
    }
  }
  const groupedHeads = new Map();
  for (const branch of orderedBranches) {
    if (!visible.has(branch.head_sha)) continue;
    const refs = groupedHeads.get(branch.head_sha) ?? [];
    refs.push({ name: branch.name, color: colors.get(branch.name) });
    groupedHeads.set(branch.head_sha, refs);
  }
  const visibleIndex = new Map(visibleOrder.map((sha, index) => [sha, index]));
  const labelRows = [];
  // Ref labels are packed independently of history lanes; shared HEADs use one label.
  const labels = [...groupedHeads].map(([sha, refs]) => {
    const name = refs[0].name;
    const labelWidth = Math.min(180, (labelWidths[name] ?? [...name].reduce((size, char) => size + (char.charCodeAt(0) > 127 ? 12 : 8), 0)) + 28 + (refs.length > 1 ? 32 : 0));
    const x = 20 + visibleIndex.get(sha) * spacing;
    const left = Math.max(4, Math.min(x - 8, width - labelWidth - 4));
    let row = labelRows.findIndex((intervals) => intervals.every(([start, end]) => left >= end + 6 || left + labelWidth + 6 <= start));
    if (row === -1) { row = labelRows.length; labelRows.push([]); }
    labelRows[row].push([left, left + labelWidth]);
    return { name, sha, refs, x, left, width: labelWidth, y: 4 + row * 26, color: refs[0].color };
  });
  const labelHeight = labelRows.length * 26;
  for (const [index, track] of tracks.entries()) track.y = labelHeight + 16 + index * 24;
  const height = Math.max(64, labelHeight + tracks.length * 24 + 8);
  const nodes = visibleOrder.map((sha, index) => {
    const commit = commits.get(sha);
    const lane = lanes[ownership.get(sha)];
    return { ...commit, x: 20 + index * spacing, y: lane.track.y, color: lane.color, missingParents: commit.parents.filter((parent) => !commits.has(parent)) };
  });
  const bySha = new Map(nodes.map((node) => [node.sha, node]));
  const edges = nodes.flatMap((node) => node.parents.filter((sha) => commits.has(sha)).map((immediateParent) => {
    let sha = immediateParent;
    let collapsedCommits = 0;
    // Only degree-one chains are collapsed; every fork and merge remains explicit.
    while (!visible.has(sha)) {
      sha = commits.get(sha).parents[0];
      collapsedCommits++;
    }
    const parent = bySha.get(sha);
    const mid = (parent.x + node.x) / 2;
    return { from: sha, to: node.sha, collapsedCommits, color: node.parents[0] === immediateParent ? node.color : parent.color, path: `M ${parent.x} ${parent.y} C ${mid} ${parent.y}, ${mid} ${node.y}, ${node.x} ${node.y}` };
  }));
  for (const label of labels) label.nodeY = bySha.get(label.sha).y;
  return { nodes, edges, labels, spacing, totalCommits: order.length, width, height, incomplete: branches.some((branch) => branch.history_truncated || !bySha.has(branch.head_sha)) || nodes.some((node) => node.missingParents.length > 0) };
}
