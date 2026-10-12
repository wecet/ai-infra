export function connectionLabel(from, to, kind) {
  if (kind === "snapshot") return "lakeFS snapshot of the dataset used for training";
  if (from.type === "training" && to.type === "model") return "Trained model published";
  if (to.type === "training") return "Used dataset for training";
  if (to.type === "lakefs") return "Published dataset saved to lakeFS";
  if (to.type === "deployment") return "Published model deployed";
  if (to.type === "version") return "Dataset state frozen into a published version";
  return from.type === "project" ? "Project started dataset history" : "Next event in dataset history";
}

export function connectionPath(from, to, root = false) {
  if (!root && Math.abs(from.x - to.x) < 1 && to.y >= from.y + from.height && to.y - from.y - from.height <= 40) {
    const x = from.x + from.width / 2, y = from.y + from.height + 1;
    const tx = to.x + to.width / 2, ty = to.y - 5;
    return `M ${x} ${y} C ${x} ${y + 8}, ${tx} ${ty - 8}, ${tx} ${ty}`;
  }
  const y = from.y + from.height / 2, ty = to.y + to.height / 2;
  if (root || Math.abs(from.x - to.x) < 1) {
    const x = from.x - 1, tx = to.x - 5;
    const lane = Math.min(x, tx) - 32;
    return `M ${x} ${y} C ${lane} ${y}, ${lane} ${ty}, ${tx} ${ty}`;
  }
  const x = from.x + from.width + 1;
  const tx = to.x - 5, bend = Math.max(24, (tx - x) / 2);
  return `M ${x} ${y} C ${x + bend} ${y}, ${tx - bend} ${ty}, ${tx} ${ty}`;
}

export function connectionArrowhead(to, from, root = false) {
  if (from && !root && Math.abs(from.x - to.x) < 1 && to.y >= from.y + from.height && to.y - from.y - from.height <= 40) {
    const x = to.x + to.width / 2, y = to.y - 5;
    return `M ${x} ${y} L ${x - 4} ${y - 8} L ${x + 4} ${y - 8} Z`;
  }
  const x = to.x - 5, y = to.y + to.height / 2;
  return `M ${x} ${y} L ${x - 8} ${y - 4} L ${x - 8} ${y + 4} Z`;
}
