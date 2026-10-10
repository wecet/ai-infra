import React from "react";

export default function AnnotationBox({ box, color, label, imageWidth, imageHeight, selected = false, labelScale = 1, onPointerDown }) {
  const fontSize = Math.max(12, imageWidth / 70) * labelScale;
  const labelWidth = Math.min(imageWidth, (label?.length || 0) * fontSize * .65 + 12);
  const labelHeight = fontSize * 1.6;
  const labelX = Math.max(0, Math.min(box.x, imageWidth - labelWidth));
  const labelY = Math.max(0, Math.min(box.y >= labelHeight ? box.y - labelHeight : box.y, imageHeight - labelHeight));
  return <g className={`annotation-box ${selected ? "annotation-box-selected" : ""}`}>
    <rect x={box.x} y={box.y} width={box.width} height={box.height} fill="none" stroke="#f4f5f7" strokeOpacity=".8"
      strokeWidth={selected ? 8 : 6} vectorEffect="non-scaling-stroke" pointerEvents="none" />
    <rect x={box.x} y={box.y} width={box.width} height={box.height} fill="none" stroke="#161a22"
      strokeWidth={selected ? 6 : 4} vectorEffect="non-scaling-stroke" pointerEvents="none" />
    <rect x={box.x} y={box.y} width={box.width} height={box.height} fill={color} fillOpacity={selected ? .12 : .04}
      stroke={color} strokeWidth={selected ? 3 : 2} vectorEffect="non-scaling-stroke" onPointerDown={onPointerDown}
      style={{ cursor: onPointerDown ? "move" : "default" }} />
    {label && <g pointerEvents="none">
      <rect x={labelX} y={labelY} width={labelWidth} height={labelHeight} rx="3" fill="#20242c" stroke={color} strokeWidth="1" vectorEffect="non-scaling-stroke" />
      <text x={labelX + 6} y={labelY + fontSize * 1.15} fill="#f4f5f7" fontSize={fontSize} fontWeight="600"
        textLength={Math.min(labelWidth - 12, label.length * fontSize * .6)} lengthAdjust="spacingAndGlyphs">{label}</text>
    </g>}
  </g>;
}
