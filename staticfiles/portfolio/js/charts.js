function drawBarChart(canvasId, labels, values, suffix) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const width = canvas.width;
  const height = canvas.height;
  const padding = { top: 18, right: 20, bottom: 54, left: 58 };
  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);

  const max = Math.max(...values.map(Math.abs), 1);
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const zeroY = padding.top + plotHeight;
  const barGap = 12;
  const barWidth = Math.max(16, (plotWidth - barGap * (values.length - 1)) / Math.max(values.length, 1));

  ctx.strokeStyle = "#d8dee8";
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top);
  ctx.lineTo(padding.left, zeroY);
  ctx.lineTo(width - padding.right, zeroY);
  ctx.stroke();

  ctx.fillStyle = "#64748b";
  ctx.font = "12px system-ui, sans-serif";
  ctx.textAlign = "right";
  for (let i = 0; i <= 4; i++) {
    const tick = max * i / 4;
    const y = zeroY - (tick / max) * plotHeight;
    ctx.fillText(formatValue(tick, suffix), padding.left - 8, y + 4);
    ctx.strokeStyle = "#eef2f7";
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(width - padding.right, y);
    ctx.stroke();
  }

  values.forEach((value, index) => {
    const x = padding.left + index * (barWidth + barGap);
    const barHeight = Math.abs(value) / max * plotHeight;
    const y = zeroY - barHeight;
    ctx.fillStyle = value < 0 ? "#b45309" : "#0f766e";
    ctx.fillRect(x, y, barWidth, barHeight);
    ctx.fillStyle = "#172033";
    ctx.textAlign = "center";
    ctx.fillText(formatValue(value, suffix), x + barWidth / 2, Math.max(12, y - 6));
    ctx.save();
    ctx.translate(x + barWidth / 2, zeroY + 12);
    ctx.rotate(-Math.PI / 7);
    ctx.fillStyle = "#64748b";
    ctx.fillText(String(labels[index] || "").slice(0, 18), 0, 18);
    ctx.restore();
  });
}

function formatValue(value, suffix) {
  if (suffix === "%") return `${Number(value).toFixed(1)}%`;
  if (suffix === "EUR") return `EUR ${Math.round(Number(value)).toLocaleString("en-US")}`;
  return Number(value).toLocaleString("en-US");
}
