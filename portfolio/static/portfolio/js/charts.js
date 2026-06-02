function drawBarChart(canvasId, labels, values, suffix) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const { ctx, width, height } = prepareCanvas(canvas);
  const isMobile = width <= 420;
  const padding = isMobile ? { top: 16, right: 12, bottom: 42, left: 42 } : { top: 18, right: 20, bottom: 54, left: 58 };
  const axisFont = isMobile ? "10px system-ui, sans-serif" : "12px system-ui, sans-serif";
  const valueFont = isMobile ? "700 10px system-ui, sans-serif" : "700 12px system-ui, sans-serif";
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
  ctx.font = axisFont;
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
    ctx.font = valueFont;
    ctx.textAlign = "center";
    const shouldShowValue = !isMobile || barWidth >= 28 || values.length <= 4;
    if (shouldShowValue) {
      ctx.fillText(formatValue(value, suffix), x + barWidth / 2, Math.max(12, y - 6));
    }
    ctx.fillStyle = "#64748b";
    ctx.font = axisFont;
    if (isMobile) {
      const label = String(labels[index] || "");
      ctx.fillText(label.length > 8 ? `${label.slice(0, 7)}…` : label, x + barWidth / 2, zeroY + 20);
    } else {
      ctx.save();
      ctx.translate(x + barWidth / 2, zeroY + 12);
      ctx.rotate(-Math.PI / 7);
      ctx.fillText(String(labels[index] || "").slice(0, 18), 0, 18);
      ctx.restore();
    }
  });
}

function drawStackedContributionChart(canvasId, labels, series, suffix) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const { ctx, width, height } = prepareCanvas(canvas);
  const isMobile = width <= 420;
  const colors = ["#0f766e", "#2563eb", "#7c3aed", "#b45309", "#be123c", "#047857", "#4338ca", "#a16207"];
  const keys = ["value", "debt", "equity"];
  const totals = keys.map((key) => series.reduce((sum, item) => sum + Math.max(0, Number(item[key] || 0)), 0));
  const max = Math.max(...totals, 1);
  const padding = isMobile ? { top: 16, right: 12, bottom: 68, left: 44 } : { top: 16, right: 18, bottom: 92, left: 62 };
  const axisFont = isMobile ? "10px system-ui, sans-serif" : "12px system-ui, sans-serif";
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const zeroY = padding.top + plotHeight;
  const barGap = isMobile ? 14 : 30;
  const barWidth = Math.max(isMobile ? 44 : 58, Math.min(isMobile ? 96 : 140, (plotWidth - barGap * (labels.length - 1)) / Math.max(labels.length, 1)));
  const startX = padding.left + Math.max(0, (plotWidth - (barWidth * labels.length + barGap * (labels.length - 1))) / 2);

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "#d8dee8";
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top);
  ctx.lineTo(padding.left, zeroY);
  ctx.lineTo(width - padding.right, zeroY);
  ctx.stroke();

  ctx.fillStyle = "#64748b";
  ctx.font = axisFont;
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

  keys.forEach((key, barIndex) => {
    const total = totals[barIndex];
    const x = startX + barIndex * (barWidth + barGap);
    let currentY = zeroY;
    series.forEach((item, index) => {
      const rawValue = Number(item[key] || 0);
      const value = Math.max(0, rawValue);
      if (!value || !total) return;
      const segmentHeight = value / max * plotHeight;
      const y = currentY - segmentHeight;
      ctx.fillStyle = colors[index % colors.length];
      ctx.fillRect(x, y, barWidth, segmentHeight);
      const percent = value / total;
      if (segmentHeight >= 20 && percent >= 0.06) {
        ctx.fillStyle = "#ffffff";
        ctx.font = isMobile ? "700 10px system-ui, sans-serif" : "700 12px system-ui, sans-serif";
        ctx.textAlign = "center";
        ctx.fillText(`${(percent * 100).toFixed(0)}%`, x + barWidth / 2, y + segmentHeight / 2 + 4);
      }
      currentY = y;
    });

    ctx.fillStyle = "#172033";
    ctx.font = isMobile ? "700 10px system-ui, sans-serif" : "700 12px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(formatValue(total, suffix), x + barWidth / 2, Math.max(12, currentY - 8));
    ctx.fillStyle = "#64748b";
    ctx.font = axisFont;
    if (isMobile) {
      ctx.fillText(labels[barIndex], x + barWidth / 2, zeroY + 20);
    } else {
      ctx.save();
      ctx.translate(x + barWidth / 2, zeroY + 18);
      ctx.rotate(-Math.PI / 9);
      ctx.fillText(labels[barIndex], 0, 0);
      ctx.restore();
    }
  });

  drawLegend(ctx, series.map((item) => item.label), colors, padding.left, height - (isMobile ? 28 : 38), width - padding.left - padding.right, { isMobile });
}

function drawLineTrendChart(canvasId, labels, values, suffix, seriesLabel, color, options = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const { ctx, width, height } = prepareCanvas(canvas);
  const isMobile = width <= 420;
  const padding = isMobile ? { top: 20, right: 12, bottom: 40, left: 46 } : { top: 20, right: 24, bottom: 48, left: 72 };
  const axisFont = isMobile ? "10px system-ui, sans-serif" : "12px system-ui, sans-serif";
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const numericValues = values.map((value) => Number(value || 0));
  const minRaw = numericValues.length ? Math.min(...numericValues) : 0;
  const maxRaw = numericValues.length ? Math.max(...numericValues) : 0;
  const span = Math.max(maxRaw - minRaw, Math.abs(maxRaw), 1);
  let min = minRaw - span * 0.12;
  let max = maxRaw + span * 0.12;
  if (minRaw >= 0) min = 0;
  if (maxRaw <= 0) max = 0;
  if (min === max) {
    min -= 1;
    max += 1;
  }

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, width, height);

  function xFor(index) {
    if (labels.length <= 1) return padding.left + plotWidth / 2;
    return padding.left + (index / (labels.length - 1)) * plotWidth;
  }
  function yFor(value) {
    return padding.top + ((max - value) / (max - min)) * plotHeight;
  }

  ctx.strokeStyle = "#d8dee8";
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top);
  ctx.lineTo(padding.left, padding.top + plotHeight);
  ctx.lineTo(width - padding.right, padding.top + plotHeight);
  ctx.stroke();

  ctx.fillStyle = "#64748b";
  ctx.font = axisFont;
  ctx.textAlign = "right";
  const tickCount = isMobile ? 3 : 4;
  for (let i = 0; i <= tickCount; i++) {
    const tick = min + ((max - min) * i) / tickCount;
    const y = yFor(tick);
    ctx.fillText(formatValue(tick, suffix), padding.left - 8, y + 4);
    ctx.strokeStyle = "#eef2f7";
    ctx.beginPath();
    ctx.moveTo(padding.left, y);
    ctx.lineTo(width - padding.right, y);
    ctx.stroke();
  }

  if (min < 0 && max > 0) {
    const zeroY = yFor(0);
    ctx.strokeStyle = "#cbd5e1";
    ctx.beginPath();
    ctx.moveTo(padding.left, zeroY);
    ctx.lineTo(width - padding.right, zeroY);
    ctx.stroke();
  }

  if (!labels.length) {
    ctx.fillStyle = "#64748b";
    ctx.textAlign = "center";
    ctx.fillText("No yearly data yet", width / 2, height / 2);
    attachTrendHover(canvas, []);
    return;
  }

  const points = [];
  ctx.strokeStyle = color || "#0f766e";
  ctx.lineWidth = 2.5;
  ctx.beginPath();
  numericValues.forEach((value, index) => {
    const x = xFor(index);
    const y = yFor(value);
    if (index === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  numericValues.forEach((value, index) => {
    const x = xFor(index);
    const y = yFor(value);
    points.push({
      x,
      y,
      label: labels[index],
      value,
      suffix,
      seriesLabel,
      tooltipLines: options.tooltipLines?.[index] || [],
    });
    ctx.fillStyle = "#ffffff";
    ctx.strokeStyle = color || "#0f766e";
    ctx.lineWidth = 2;
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#172033";
    ctx.font = isMobile ? "700 10px system-ui, sans-serif" : "700 12px system-ui, sans-serif";
    ctx.textAlign = "center";
    if (!isMobile || labels.length <= 5 || index % 2 === 0) {
      ctx.fillText(formatValue(value, suffix), x, Math.max(12, y - 10));
    }
  });

  ctx.fillStyle = "#64748b";
  ctx.font = axisFont;
  ctx.textAlign = "center";
  labels.forEach((label, index) => {
    if (!isMobile || labels.length <= 6 || index === 0 || index === labels.length - 1 || index % 2 === 0) {
      ctx.fillText(String(label), xFor(index), padding.top + plotHeight + 24);
    }
  });

  ctx.fillStyle = color || "#0f766e";
  ctx.fillRect(padding.left, 10, 10, 10);
  ctx.fillStyle = "#475569";
  ctx.textAlign = "left";
  ctx.fillText(seriesLabel || "", padding.left + 16, 20);
  attachTrendHover(canvas, points);
}

function attachTrendHover(canvas, points) {
  canvas._trendHoverPoints = points;
  canvas.dataset.trendPointCount = String(points.length);
  canvas.dataset.trendPoints = JSON.stringify(points.map((point) => ({ x: point.x, y: point.y })));
  let tooltip = document.getElementById("chart-hover-tooltip");
  if (!tooltip) {
    tooltip = document.createElement("div");
    tooltip.id = "chart-hover-tooltip";
    tooltip.className = "chart-hover-tooltip";
    document.body.appendChild(tooltip);
  }
  canvas.onmousemove = (event) => {
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    let nearest = null;
    let nearestDistance = Infinity;
    points.forEach((point) => {
      const distance = Math.hypot(point.x - x, point.y - y);
      if (distance < nearestDistance) {
        nearest = point;
        nearestDistance = distance;
      }
    });
    if (!nearest || nearestDistance > 16) {
      tooltip.classList.remove("is-visible");
      canvas.style.cursor = "";
      return;
    }
    canvas.style.cursor = "default";
    tooltip.textContent = [
      `${nearest.label} · ${nearest.seriesLabel}: ${formatValue(nearest.value, nearest.suffix)}`,
      ...nearest.tooltipLines,
    ].join("\n");
    tooltip.classList.add("is-visible");
    positionChartTooltip(tooltip, event.clientX, event.clientY);
  };
  canvas.onmouseleave = () => {
    canvas.style.cursor = "";
    tooltip.classList.remove("is-visible");
  };
}

function positionChartTooltip(tooltip, clientX, clientY) {
  const padding = 12;
  const rect = tooltip.getBoundingClientRect();
  let left = clientX + 14;
  if (left + rect.width > window.innerWidth - padding) left = clientX - rect.width - 14;
  let top = clientY + 14;
  if (top + rect.height > window.innerHeight - padding) top = clientY - rect.height - 14;
  tooltip.style.left = `${Math.max(padding, left)}px`;
  tooltip.style.top = `${Math.max(padding, top)}px`;
}

function drawLegend(ctx, labels, colors, x, y, maxWidth, options = {}) {
  ctx.font = options.isMobile ? "10px system-ui, sans-serif" : "12px system-ui, sans-serif";
  let currentX = x;
  let currentY = y;
  labels.forEach((label, index) => {
    const text = String(label || "").slice(0, options.isMobile ? 14 : 22);
    const itemWidth = 18 + ctx.measureText(text).width + 18;
    if (currentX + itemWidth > x + maxWidth) {
      currentX = x;
      currentY += 18;
    }
    ctx.fillStyle = colors[index % colors.length];
    ctx.fillRect(currentX, currentY - 10, 10, 10);
    ctx.fillStyle = "#475569";
    ctx.textAlign = "left";
    ctx.fillText(text, currentX + 16, currentY);
    currentX += itemWidth;
  });
}

function prepareCanvas(canvas) {
  const ctx = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  const width = Math.max(260, Math.round(rect.width));
  const height = Math.max(180, Math.round(rect.height || 280));
  const dpr = Math.max(1, window.devicePixelRatio || 1);
  const bitmapWidth = Math.round(width * dpr);
  const bitmapHeight = Math.round(height * dpr);
  if (canvas.width !== bitmapWidth || canvas.height !== bitmapHeight) {
    canvas.width = bitmapWidth;
    canvas.height = bitmapHeight;
  }
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  return { ctx, width, height };
}

function formatValue(value, suffix) {
  if (suffix === "%") return `${Number(value).toFixed(1)}%`;
  if (suffix === "€") return `€${Math.round(Number(value)).toLocaleString("en-US")}`;
  return Number(value).toLocaleString("en-US");
}
