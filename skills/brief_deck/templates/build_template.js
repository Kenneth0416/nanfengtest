// Builds one template per theme in ../themes/themes.json: templates/<theme>.pptx.
// Each template has the same thirteen layouts (references/layouts.md); every content area is a placeholder,
// so scripts/build_deck.py fills placeholders instead of drawing at coordinates.
//
//   npm i pptxgenjs@3.12.0 && node build_template.js && python3 finalize_template.py
//
// Design language taken from the slide patterns in Grok Build's bundled pptx templates (studied, not
// copied): tracked uppercase eyebrow above a sentence-case action title, a short accent rule, cards with
// an accent top edge, oversized hero numbers, a dark "so what" band (drawn by build_deck.py), and a
// tracked footer with the page number. The second pass over all 193 templates added the slide types
// they use most that the brief lacked: a stat row (the most common slide, 605 of 1,891), numbered
// pillars (141), a full-bleed statement and a timeline; and per-theme style flags (serif italic
// numerals, monospace labels, a top bar) in place of hard-coded theme names.
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const THEMES = JSON.parse(fs.readFileSync(path.join(__dirname, "..", "themes", "themes.json"), "utf8"));
const FOOTER = "LONDON OFFICE AGENT  ·  TEAM BRIEF";
const LAYOUTS = ["Cover", "Section", "Statement", "Hero number", "Stat row", "Chart + takeaway", "Two charts",
  "Chart + table", "Numbered pillars", "Timeline", "Signal cards", "Sources", "Title only"];

function build(name, th) {
  const C = th.colors, F = th.fonts, S = th.style;
  const LABEL = F.label || F.body;
  const ph = (pname, type, x, y, w, h, o = {}) => ({
    placeholder: { options: { name: pname, type, x, y, w, h, margin: 0.04, valign: "top", align: "left",
      fontFace: F.body, fontSize: 13, color: C.ink, ...o }, text: "" },
  });
  const line = (x, y, w, color, width) => ({ line: { x, y, w, h: 0, line: { color, width } } });
  const rect = (x, y, w, h, fill, border) => ({ rect: { x, y, w, h, fill: { color: fill },
    line: border ? { color: border, width: 0.75 } : { type: "none" } } });
  const text = (t, x, y, w, h, o = {}) => ({ text: { text: t, options: { x, y, w, h, margin: 0, fontFace: F.body,
    fontSize: 8, color: C.muted, charSpacing: 2, ...o } } });

  const label = { fontSize: 10, bold: true, color: C.muted, charSpacing: 2 };
  const eyebrow = () => ph("eyebrow", "body", 0.6, 0.32, 9.0, 0.3, { fontFace: LABEL, fontSize: 10, bold: true,
    color: C.accent, charSpacing: 3 });
  const title = () => ph("title", "title", 0.6, 0.74, 12.1, 0.95,
    { fontFace: F.head, fontSize: F.title_size, bold: S.title_bold, color: C.ink, valign: "bottom" });
  const source = () => ph("source", "body", 0.6, 6.8, 12.1, 0.24, { fontSize: 8, color: C.muted });
  const topBar = S.top_bar ? [rect(0, 0, 13.333, 0.08, C.accent)] : [];
  const big = (o = {}) => ({ fontFace: F.head, bold: true, italic: S.hero_italic, color: C.accent, ...o });

  const light = (objects) => ({
    background: { color: C.bg },
    slideNumber: { x: 12.0, y: 7.1, w: 0.73, h: 0.25, fontFace: F.body, fontSize: 8, color: C.muted, align: "right" },
    objects: [...topBar, line(0.6, 0.7, 0.6, C.accent, 2), eyebrow(), title(),
      line(0.6, 7.04, 12.13, C.rule, 0.5), text(FOOTER, 0.6, 7.12, 8, 0.22, { fontFace: LABEL }), ...objects],
  });

  const p = new pptxgen();
  p.layout = "LAYOUT_WIDE"; // 13.333 x 7.5 in
  p.title = `Team brief template (${name})`;
  p.theme = { headFontFace: F.head, bodyFontFace: F.body };

  // Cover: eyebrow, title, subtitle, three-sentence headline, four KPI cards with an accent top edge.
  const kpis = [0, 1, 2, 3].flatMap((i) => {
    const x = 0.7 + i * 3.03;
    return [line(x, 4.45, 2.85, C.accent, 3), ph(`kpi${i + 1}`, "body", x, 4.55, 2.85, 1.65,
      { color: C.on_dark, fontSize: 12 })];
  });
  p.defineSlideMaster({ title: "Cover", background: { color: C.dark }, objects: [
    ph("eyebrow", "body", 0.7, 0.55, 9, 0.3, { fontFace: LABEL, fontSize: 10, bold: true, color: C.accent, charSpacing: 3 }),
    ph("title", "title", 0.7, 0.9, 11.9, 1.0, { fontFace: F.head, fontSize: F.cover_size || 38, bold: true, color: C.on_dark, valign: "bottom" }),
    ph("subtitle", "body", 0.7, 1.95, 11.9, 0.4, { fontSize: 13, color: C.on_dark_muted }),
    ph("headline", "body", 0.7, 2.5, 11.9, 1.75, { fontSize: 15, color: C.on_dark }),
    ...kpis,
    ph("caveat", "body", 0.7, 6.75, 11.9, 0.45, { fontSize: 8, color: C.on_dark_muted }),
  ] });

  // Section: a divider for a longer IC pack or a second topic.
  p.defineSlideMaster({ title: "Section", background: { color: C.dark }, objects: [
    line(0.7, 2.95, 1.0, C.accent, 3),
    ph("eyebrow", "body", 0.7, 2.5, 9, 0.3, { fontFace: LABEL, fontSize: 10, bold: true, color: C.accent, charSpacing: 3 }),
    ph("title", "title", 0.7, 3.1, 11.9, 1.0, { fontFace: F.head, fontSize: 34, bold: true, color: C.on_dark }),
    ph("body", "body", 0.7, 4.2, 11.0, 1.2, { fontSize: 15, color: C.on_dark_muted }),
  ] });

  // Statement: one sentence carries the slide, full-bleed dark; *emphasis* in the text takes the accent.
  p.defineSlideMaster({ title: "Statement", background: { color: C.dark }, objects: [
    ph("eyebrow", "body", 0.9, 1.35, 9, 0.3, { fontFace: LABEL, fontSize: 10, bold: true, color: C.accent, charSpacing: 3 }),
    line(0.9, 1.8, 0.8, C.accent, 3),
    ph("statement", "body", 0.9, 2.05, 11.5, 2.2, { fontFace: F.head, fontSize: 34, bold: S.title_bold,
      color: C.on_dark }),
    ph("attribution", "body", 0.9, 4.4, 11.5, 0.6, { fontSize: 12, color: C.on_dark_muted }),
    text(FOOTER, 0.9, 7.0, 8, 0.22, { fontFace: LABEL, color: C.on_dark_muted }),
  ] });

  // Hero number: one figure carries the slide; context on the left, the series that explains it on the right.
  p.defineSlideMaster({ title: "Hero number", ...light([
    ph("hero", "body", 0.6, 1.85, 4.3, 1.3, big({ fontSize: 60, valign: "bottom" })),
    ph("hero_caption", "body", 0.6, 3.2, 4.3, 0.35, label),
    ph("hero_context", "body", 0.6, 3.65, 4.3, 2.4, { fontSize: 12 }),
    ph("chart_label", "body", 5.3, 1.8, 7.4, 0.32, label),
    ph("chart", "chart", 5.2, 2.12, 7.53, 3.95),
    source(),
  ]) });

  // Stat row: four figures across the top, each on an accent rule, and the series behind them below.
  const stats = [0, 1, 2, 3].flatMap((i) => {
    const x = 0.6 + i * 3.06;
    return [line(x, 1.85, 2.9, C.accent, 1.5),
      ph(`stat${i + 1}`, "body", x, 1.95, 2.9, 0.8, big({ fontSize: 30, valign: "bottom" })),
      ph(`stat${i + 1}_caption`, "body", x, 2.8, 2.9, 0.42, { ...label, fontFace: LABEL, fontSize: 9 }),
      ph(`stat${i + 1}_context`, "body", x, 3.24, 2.9, 0.48, { fontSize: 10, color: C.muted })];
  });
  p.defineSlideMaster({ title: "Stat row", ...light([...stats,
    ph("chart_label", "body", 0.6, 3.82, 12.1, 0.3, label),
    ph("chart", "chart", 0.5, 4.12, 12.23, 1.95),
    source(),
  ]) });

  // Chart + takeaway: one chart and the so-what beside it.
  p.defineSlideMaster({ title: "Chart + takeaway", ...light([
    ph("chart_label", "body", 0.6, 1.8, 8.2, 0.32, label),
    ph("chart", "chart", 0.5, 2.12, 8.3, 3.95),
    rect(9.05, 1.8, 3.68, 4.27, C.panel),
    line(9.05, 1.8, 3.68, C.accent, 3),
    ph("takeaway", "body", 9.2, 1.95, 3.4, 4.0, { fontSize: 12 }),
    source(),
  ]) });

  // Two charts: two measures side by side, never one dual-axis chart.
  p.defineSlideMaster({ title: "Two charts", ...light([
    ph("left_label", "body", 0.6, 1.8, 6.0, 0.32, label),
    ph("left_chart", "chart", 0.5, 2.12, 6.15, 3.95),
    ph("right_label", "body", 6.95, 1.8, 5.8, 0.32, label),
    ph("right_chart", "chart", 6.85, 2.12, 5.88, 3.95),
    source(),
  ]) });

  // Chart + table: a comparison and the few exact figures behind it.
  p.defineSlideMaster({ title: "Chart + table", ...light([
    ph("chart_label", "body", 0.6, 1.8, 7.3, 0.32, label),
    ph("chart", "chart", 0.5, 2.12, 7.4, 3.95),
    ph("table_label", "body", 8.2, 1.8, 4.5, 0.32, label),
    ph("table", "body", 8.2, 2.12, 4.53, 3.0),
    source(),
  ]) });

  // Numbered pillars: three ideas under oversized 01 / 02 / 03 numerals, each over a rule.
  const pillars = [0, 1, 2].flatMap((i) => {
    const x = 0.6 + i * 4.08;
    return [text(`0${i + 1}`, x, 1.75, 2.0, 0.95, big({ fontSize: 48, charSpacing: 0, valign: "bottom" })),
      line(x, 2.8, 3.85, C.rule, 1),
      ph(`pillar${i + 1}_head`, "body", x, 2.95, 3.85, 0.8, { fontFace: F.head, fontSize: 17, bold: true }),
      ph(`pillar${i + 1}_body`, "body", x, 3.8, 3.85, 2.2, { fontSize: 12 })];
  });
  p.defineSlideMaster({ title: "Numbered pillars", ...light(pillars) });

  // Timeline: up to five dated steps; build_deck.py draws the line and the nodes for the steps used.
  const steps = [0, 1, 2, 3, 4].flatMap((i) => {
    const x = 0.6 + i * 2.45;
    return [ph(`step${i + 1}_when`, "body", x, 2.4, 2.3, 0.35, { fontFace: LABEL, fontSize: 11, bold: true,
      color: C.accent, charSpacing: 2 }),
      ph(`step${i + 1}_head`, "body", x, 3.3, 2.3, 0.6, { fontFace: F.head, fontSize: 15, bold: true }),
      ph(`step${i + 1}_body`, "body", x, 4.0, 2.3, 2.0, { fontSize: 11 })];
  });
  p.defineSlideMaster({ title: "Timeline", ...light(steps) });

  // Signal cards: up to six findings; tone mark and accent edge drawn by the script; talk strip.
  const cards = [0, 1, 2, 3, 4, 5].flatMap((i) => {
    const x = 0.6 + (i % 3) * 4.08, y = 1.8 + Math.floor(i / 3) * 2.08;
    return [rect(x, y, 3.95, 1.95, C.card, C.rule), ph(`card${i + 1}`, "body", x + 0.14, y + 0.1, 3.7, 1.8,
      { fontSize: 10 })];
  });
  p.defineSlideMaster({ title: "Signal cards", ...light([...cards,
    ph("talk", "body", 0.6, 6.03, 12.1, 0.7, { fontSize: 10 })]) });

  // Sources: numbered footnotes, flagged figures, caveat.
  p.defineSlideMaster({ title: "Sources", ...light([ph("body", "body", 0.6, 1.8, 12.1, 4.95, { fontSize: 10 })]) });

  // Title only: a full-width table (IC evidence) or anything the other layouts do not cover.
  p.defineSlideMaster({ title: "Title only", ...light([]) });

  for (const l of LAYOUTS) p.addSlide({ masterName: l });
  return p.writeFile({ fileName: path.join(__dirname, `${name}.raw.pptx`) });
}

(async () => {
  for (const [name, th] of Object.entries(THEMES)) await build(name, th);
})();
