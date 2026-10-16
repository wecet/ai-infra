export function ancestors(edges, selected) {
  const result = new Set(selected ? [selected] : []);
  let changed = true;
  while (changed) {
    changed = false;
    for (const edge of edges) if (result.has(edge.to) && !result.has(edge.from)) { result.add(edge.from); changed = true; }
  }
  return result;
}
