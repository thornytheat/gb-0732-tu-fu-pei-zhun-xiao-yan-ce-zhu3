const palette = {
  grid: '#ded4bf', frame: '#a99a82', muted: '#6e6251', ink: '#302b22',
  green: '#385b49', red: '#943a35', amber: '#77601e', accent: '#8c4638',
  fills: ['#eee6d5', '#f2e7d7', '#e8e8d8', '#ede3d9'],
};
const mono = '10px ui-monospace, monospace';
const serif = 'bold 13px "Songti SC", SimSun, serif';

function surface(canvas) {
  const {width, height} = canvas.getBoundingClientRect();
  if (!width || !height) return null;
  const ratio = window.devicePixelRatio || 1;
  canvas.width = Math.round(width * ratio);
  canvas.height = Math.round(height * ratio);
  const ctx = canvas.getContext('2d');
  ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
  ctx.font = mono;
  return {ctx, width, height};
}

function stroke(ctx, points, color, thickness = 1, dash = []) {
  if (!points.length) return;
  ctx.beginPath();
  ctx.moveTo(...points[0]);
  for (const point of points.slice(1)) ctx.lineTo(...point);
  ctx.strokeStyle = color;
  ctx.lineWidth = thickness;
  ctx.setLineDash(dash);
  ctx.stroke();
  ctx.setLineDash([]);
}

function text(ctx, value, x, y, options = {}) {
  ctx.font = options.font || mono;
  ctx.textAlign = options.align || 'left';
  ctx.fillStyle = options.color || palette.muted;
  ctx.fillText(value, x, y);
}

function dot(ctx, x, y, color, flagged = false) {
  if (flagged) {
    stroke(ctx, [[x, y - 5], [x + 5, y], [x, y + 5], [x - 5, y], [x, y - 5]], color, 1.5);
  } else {
    stroke(ctx, [[x - 3.5, y], [x + 3.5, y]], color, 1.25);
    stroke(ctx, [[x, y - 3.5], [x, y + 3.5]], color, 1.25);
  }
}

function grid(plot, xRange, yRange, options = {}) {
  const {ctx, width, height} = plot;
  const {xStep = 1, yStep = 1, equal = false, downward = false, xFormat = String, yFormat = String} = options;
  const [xmin, xmax] = xRange;
  const [ymin, ymax] = yRange;
  const sx = (width - 53) / (xmax - xmin);
  const sy = (height - 41) / (ymax - ymin);
  const kx = equal ? Math.min(sx, sy) : sx;
  const ky = equal ? kx : sy;
  const left = 35 + ((width - 53) - (xmax - xmin) * kx) / 2;
  const top = 15 + ((height - 41) - (ymax - ymin) * ky) / 2;
  const coord = ([x, y]) => [left + (x - xmin) * kx, top + (downward ? y - ymin : ymax - y) * ky];
  const [right] = coord([xmax, ymin]);
  const bottom = top + (ymax - ymin) * ky;
  for (let x = Math.ceil(xmin / xStep) * xStep; x <= xmax; x += xStep) {
    const [px] = coord([x, ymin]);
    stroke(ctx, [[px, top], [px, bottom]], palette.grid);
    text(ctx, xFormat(x), px, bottom + 13, {align: 'center'});
  }
  for (let y = Math.ceil(ymin / yStep) * yStep; y <= ymax; y += yStep) {
    const [, py] = coord([xmin, y]);
    stroke(ctx, [[left, py], [right, py]], palette.grid);
    text(ctx, yFormat(y), left - 4, py + 3, {align: 'right'});
  }
  ctx.strokeStyle = palette.frame;
  ctx.strokeRect(left, top, right - left, bottom - top);
  return coord;
}

const nearestStep = value => 10 ** Math.floor(Math.log10(value)) * (value / 10 ** Math.floor(Math.log10(value)) > 3 ? 5 : 2);

function range(values, step) {
  let lowest = Infinity;
  let highest = -Infinity;
  for (const value of values) {
    lowest = Math.min(lowest, value);
    highest = Math.max(highest, value);
  }
  return [Math.floor((lowest - step / 6) / step) * step, Math.ceil((highest + step / 6) / step) * step];
}

export function drawAtlas(canvas, snapshot, selected, edgeId) {
  const plot = surface(canvas);
  if (!plot) return;
  const {ctx, width, height} = plot;
  const sheets = snapshot?.catalog.sheets || [];
  const matches = [...(snapshot?.refit.accepted || []), ...(snapshot?.refit.outliers || [])];
  if (selected && !snapshot.refit.sheets[selected]?.footprint) {
    const sheet = sheets.find(item => item.code === selected);
    const xStep = nearestStep(sheet.width_px / 5);
    const yStep = nearestStep(sheet.height_px / 5);
    const scale = grid(plot, [0, sheet.width_px], [0, sheet.height_px], {xStep, yStep, equal: true, downward: true});
    for (const point of snapshot.pairing.pairs.filter(item => item.sheet === selected)) {
      dot(ctx, ...scale(point.pixel), palette.amber);
    }
    return;
  }
  const active = sheets.filter(sheet => !selected || sheet.code === selected);
  const outlines = active.filter(sheet => snapshot.refit.sheets[sheet.code].footprint);
  if (!outlines.length) {
    grid(plot, [0, 6], [0, 4], {xFormat: () => '', yFormat: () => ''});
    stroke(ctx, [[width / 2 - 19, height / 2], [width / 2 + 19, height / 2]], palette.frame);
    stroke(ctx, [[width / 2, height / 2 - 19], [width / 2, height / 2 + 19]], palette.frame);
    text(ctx, '待配准', width / 2, height / 2 + 35, {font: serif, align: 'center'});
    return;
  }
  const points = matches.filter(item => !selected || item.sheet === selected);
  const bounds = [...outlines.flatMap(sheet => snapshot.refit.sheets[sheet.code].footprint), ...points.map(point => point.ground)];
  const xx = bounds.map(point => point[0]);
  const yy = bounds.map(point => point[1]);
  const xStep = nearestStep((Math.max(...xx) - Math.min(...xx)) / 6);
  const yStep = nearestStep((Math.max(...yy) - Math.min(...yy)) / 5);
  const scale = grid(plot, range(xx, xStep), range(yy, yStep), {xStep, yStep, equal: true});
  for (const [index, sheet] of outlines.entries()) {
    const polygon = snapshot.refit.sheets[sheet.code].footprint.map(scale);
    ctx.beginPath();
    ctx.moveTo(...polygon[0]);
    for (const xy of polygon.slice(1)) ctx.lineTo(...xy);
    ctx.closePath();
    ctx.globalAlpha = .78;
    ctx.fillStyle = palette.fills[index % palette.fills.length];
    ctx.fill();
    ctx.globalAlpha = 1;
    stroke(ctx, [...polygon, polygon[0]], palette.frame, 1.25);
    const center = polygon.reduce(([x, y], p) => [x + p[0] / 4, y + p[1] / 4], [0, 0]);
    text(ctx, `${sheet.code}  ${sheet.title}`, center[0], center[1] + 25, {font: serif, align: 'center', color: palette.ink});
  }
  for (const edge of snapshot.seams.edges) {
    const color = edge.status === 'FAIL' ? palette.red : palette.accent;
    const emphasized = edge.code === edgeId;
    for (const [line, code, dash] of [[edge.a_line, edge.a, []], [edge.b_line, edge.b, [3, 3]]]) {
      if (line && (!selected || selected === code)) stroke(ctx, line.map(scale), color, emphasized ? 2.4 : 1.2, dash);
    }
  }
  for (const point of points) {
    const flagged = Boolean(point.reason);
    if (flagged) stroke(ctx, [scale(point.ground), scale(point.after.projected)], palette.red, 1.2, [2, 2]);
    dot(ctx, ...scale(point.ground), flagged ? palette.red : palette.green, flagged);
    if (flagged) {
      const [x, y] = scale(point.ground);
      text(ctx, point.name, x + 8, y - 5, {color: palette.red});
    }
  }
  stroke(ctx, [[width - 15, 42], [width - 15, 23], [width - 18, 30]], palette.ink);
  text(ctx, 'N', width - 15, 19, {align: 'center', color: palette.ink});
}

export function drawEdge(canvas, edge) {
  const plot = surface(canvas);
  if (!plot) return;
  const {ctx, width, height} = plot;
  if (!edge || edge.stations[0]?.normal_m === undefined) {
    text(ctx, edge ? '无可量测图边' : '待接边', width / 2, height / 2, {font: serif, align: 'center'});
    return;
  }
  const normals = [0, ...edge.stations.map(point => point.normal_m)];
  const magnitude = normals.reduce((max, value) => Math.max(max, Math.abs(value)), 0);
  const step = Math.max(.05, nearestStep(magnitude / 2 || .05));
  const scale = grid(plot, [0, 1], range(normals, step), {xStep: .25, yStep: step,
    xFormat: x => `${Math.round(x * 100)}%`, yFormat: y => y.toFixed(step < .1 ? 2 : 1)});
  stroke(ctx, [scale([0, 0]), scale([1, 0])], palette.ink, 1.2);
  const color = edge.status === 'FAIL' ? palette.red : palette.green;
  stroke(ctx, edge.stations.map(row => scale([row.at, row.normal_m])), color, 1.4);
  for (const row of edge.stations) {
    const from = scale([row.at, 0]);
    const to = scale([row.at, row.normal_m]);
    stroke(ctx, [from, to], palette.frame, 1, [2, 2]);
    dot(ctx, ...to, color);
  }
}

export function drawResidual(canvas, rows, limit) {
  const plot = surface(canvas);
  if (!plot || !rows.length) return;
  const {ctx, width, height} = plot;
  const values = rows.flatMap(row => [row.before?.distance_m || 0, row.after.distance_m]);
  const maximum = Math.max(limit, ...values);
  const top = 19;
  const bottom = height - 26;
  const left = 38;
  const xStep = (width - left - 15) / rows.length;
  const y = value => bottom - (bottom - top) * value / (maximum * 1.13);
  stroke(ctx, [[left, bottom], [width - 10, bottom]], palette.frame);
  stroke(ctx, [[left, y(limit)], [width - 10, y(limit)]], palette.frame, 1, [4, 3]);
  text(ctx, `${limit.toFixed(2)} m`, left - 3, y(limit) - 2, {align: 'right'});
  rows.forEach((row, index) => {
    const x = left + xStep * (index + .5);
    const before = row.before?.distance_m;
    if (before !== undefined) stroke(ctx, [[x - 2, bottom], [x - 2, y(before)]], palette.frame, 2);
    stroke(ctx, [[x + 2, bottom], [x + 2, y(row.after.distance_m)]], row.reason ? palette.red : palette.green, 2);
    if (xStep >= 24 || index % 5 === 0) text(ctx, row.name, x, height - 7, {align: 'center'});
  });
}
