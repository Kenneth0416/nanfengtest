// Pi extension "market-info": the team's information agent. One Pi agent that collects and reads
// whatever comes in (web pages, news, RSS, PDFs, spreadsheets, open-data APIs, colleagues' tips),
// choosing a playbook per input from info_skills/ (check-terms, fetch-source, dedupe, read-pdf,
// read-table, read-article, map-submarkets, check-figures).
//
// Tools that touch the network or the playbooks run here in Pi: fetch_source, check_report_index,
// follow_source and load_skill. Parsing steps (PDF overview, vision reading, market mapping, the three
// figure checks, saving) come from the Python skills over the bridge, so the numbers are always
// checked by the same code. The agent decides the order and adapts to the material.
//
// Installed in the Copilot (agent.ts), so "follow X", "I heard…" or a pasted link work in chat. Run on
// its own it processes one instruction (an upload, a link) or a daily round:
//   node --experimental-strip-types info_agent.ts   (stdin: the instruction)
// Every tool call is committed before it runs, so a crashed run resumes instead of saving twice.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { createModels, Type } from "@earendil-works/pi-ai";
import { AssistantEntry, createRegistry, defineExtension, defineTool, Harness, section } from "@earendil-works/pi-durable";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import { bridgeTool, callPython, env, manifest, pickModel, REQUEST_ID } from "./common.ts";
import type { BridgeTool } from "./common.ts";

const UA = { "user-agent": "Mozilla/5.0 (london-office-agent PoC)" };
export const NATIVE = ["fetch_source", "check_report_index", "follow_source", "load_skill"];
// Tools served by the Python skills (market_gather, info_processing) over the bridge.
export const GATHER = ["share_tip", "list_inbox", "classify_item", "find_matches", "save_item", "score_hotness",
	"collect_open_data", "list_followed", "dedupe_report", "pdf_overview", "pdf_page_text", "read_pdf_pages",
	"map_markets", "check_figures", "stage_figures", "save_figures", "read_table", "save_series"];
// Python tools Pi tools call internally, not offered to the model.
export const INTERNAL = ["resolve_source", "read_link", "list_skills"];

async function getHtml(url: string): Promise<string> {
	return (await getPage(url)).body;
}

async function getPage(url: string): Promise<{ body: string; type: string }> {
	const res = await fetch(url, { headers: UA, redirect: "follow", signal: AbortSignal.timeout(15000) });
	if (!res.ok) throw new Error(`${url} returned ${res.status}`);
	return { body: (await res.text()).slice(0, 2_000_000), type: res.headers.get("content-type") ?? "" };
}

// A real terms page: a short path whose segment is "terms", "legal", "conditions"…, never an article
// whose headline happens to contain "legal" (/news/2026/10/legal-battle-over-...). Mirrors core/follow.py.
const TERMS_SEGMENT = /^(terms(-|_)?(and|of|&)?(-|_)?(conditions|use|service|business)?|conditions|legal(-|_)?(notice|notices|information)?|copyright|disclaimer|t-?and-?cs?|tandcs?|tcs|privacy-and-terms|policies)(\.[a-z]+)?$/;
function isTermsUrl(href: string): boolean {
	let path = "";
	try { path = new URL(href).pathname.toLowerCase().replace(/\/+$/, ""); } catch { return false; }
	const segs = path.split("/").filter(Boolean);
	if (segs.length > 3 || segs.some((p) => /^(\d{4}|\d{1,2})$/.test(p))) return false;
	return segs.some((p) => TERMS_SEGMENT.test(p));
}
function termsLink(html: string, base: string): string {
	for (const m of html.matchAll(/<a[^>]+href=["']([^"']+)["'][^>]*>([\s\S]*?)<\/a>/gi)) {
		let full = "";
		try { full = new URL(m[1], base).toString(); } catch { continue; }
		if (isTermsUrl(full)) return full;
	}
	return "";
}

const text = (body: unknown) => ({ content: [{ type: "text", text: JSON.stringify(body) }] });

export function infoExtension(m: any) {
	const index: { publisher: string; url: string }[] = m.info?.report_index ?? [];
	const info = m.info ?? {};
	const fetchSource = defineTool({
		name: "fetch_source",
		description: "fetch-source: get a link once. Web pages and feeds come back as text; PDFs, CSV, Excel and JSON "
			+ "are saved and their path returned for read-pdf or read-table. Never use it on an upload-only source.",
		parameters: Type.Object({ url: Type.String() }),
		replay: "safe",
		execute: async ({ url }: { url: string }) => {
			const res = await fetch(url, { headers: UA, redirect: "follow", signal: AbortSignal.timeout(30000) });
			if (!res.ok) throw new Error(`${url} returned ${res.status}`);
			const body = Buffer.from(await res.arrayBuffer()).subarray(0, 40_000_000);
			return text(await callPython("fetch_source", { url, body_b64: body.toString("base64"),
				content_type: res.headers.get("content-type") ?? "" }));
		},
	} as any);
	const skills: { name: string; description: string }[] = info.skills ?? [];
	const loadSkill = defineTool({
		name: "load_skill",
		description: "Load one of your playbooks and follow it: " + skills.map((k) => k.name).join(", ") + ".",
		parameters: Type.Object({ name: Type.String() }),
		replay: "safe",
		execute: async ({ name }: { name: string }) => {
			const file = join(info.skills_dir ?? "../info_skills", name.replace(/[^a-z0-9-]/g, ""), "SKILL.md");
			if (!existsSync(file)) return text({ error: `No skill ${name}`, skills: skills.map((k) => k.name) });
			return { content: [{ type: "text", text: readFileSync(file, "utf8").split("---").slice(2).join("---").trim() }] };
		},
	} as any);
	const checkIndex = defineTool({
		name: "check_report_index",
		description: "Check agency research index pages for new London office report titles that nobody on the "
			+ "team has uploaded. Reads titles only; never downloads a report.",
		parameters: Type.Object({}),
		replay: "safe",
		execute: async () => {
			const pages: Record<string, string> = {};
			const failed: string[] = [];
			for (const i of index) {
				try { pages[i.url] = await getHtml(i.url); } catch (e) { failed.push(`${i.publisher}: ${e}`); }
			}
			const out = Object.keys(pages).length ? await callPython("check_report_index", { pages }) : { summary: "" };
			return text({ ...out, unreachable: failed });
		},
	} as any);
	const followSource = defineTool({
		name: "follow_source",
		description: "Follow a new information source for the whole team, from a link or a name ('follow Savills "
			+ "Market Watch'). Reads its robots.txt, the page and its terms page first: allowed sources are collected "
			+ "automatically, restricted ones become upload-only with reminders to the team.",
		parameters: Type.Object({
			source: Type.String({ description: "a link, or the source's name" }),
			name: Type.Optional(Type.String()),
			cadence: Type.Optional(Type.Union(["daily", "weekly", "monthly", "quarterly", "half-yearly", "annual"]
				.map((c) => Type.Literal(c)))),
		}),
		// Adds a row for the team: never replayed after a crash (Python also ignores a second add of the same URL).
		execute: async (args: { source: string; name?: string; cadence?: string }) => {
			const src = (await callPython("resolve_source", { source: args.source })).data;
			if (!src.url) return text(await callPython("follow_source", args));
			const ev: Record<string, string> = { robots: "", page: "", content_type: "", terms: "", terms_url: "" };
			const origin = new URL(src.url).origin;
			try { ev.robots = await getHtml(`${origin}/robots.txt`); } catch { /* no robots.txt */ }
			try { const p = await getPage(src.url); ev.page = p.body; ev.content_type = p.type; } catch { /* unreadable */ }
			ev.terms_url = ev.page ? termsLink(ev.page, src.url) : "";
			if (!ev.terms_url && new URL(src.url).pathname !== "/") {  // a feed has no footer: look on the home page
				try { ev.terms_url = termsLink(await getHtml(`${origin}/`), `${origin}/`); } catch { /* unreadable */ }
			}
			if (ev.terms_url) { try { ev.terms = await getHtml(ev.terms_url); } catch { /* unreadable */ } }
			return text(await callPython("follow_source", { ...args, source: src.url, name: args.name ?? src.name, ...ev }));
		},
	} as any);
	const python = (m.tools as BridgeTool[])
		.filter((t) => GATHER.includes(t.name))
		.map(bridgeTool);
	const catalogue = () => (info.system ?? "") + "\n\nYour playbooks (load_skill before you start on a kind of "
		+ "material you have not handled in this conversation):\n" + skills.map((k) => `- ${k.name}: ${k.description}`).join("\n");
	return defineExtension({
		name: "market-info",
		sections: [section("information-agent", catalogue, { tag: false })],
		tools: [fetchSource, checkIndex, followSource, loadSkill, ...python],
	});
}

// Scripted run for tests (PI_FAUX=1 without PI_FAUX_SCRIPT): file inbox item 1 as a new story.
const FAUX = [
	{ tool: "list_inbox" },
	{ tool: "find_matches", args: { title: "Google looking for 200,000 sq ft in King's Cross" } },
	{ tool: "save_item", args: { title: "Google looking for 200,000 sq ft in King's Cross", text: "Broker says Google is looking for 200,000 sq ft in King's Cross", shared_by: "Kenneth", how: "Broker call", inbox_id: 1 } },
	{ text: "Gathering round done: 1 new tip from Kenneth saved." },
];

async function main() {
	const instruction = readFileSync(0, "utf8").trim() || "Run today's gathering round for the team: load the "
		+ "playbooks you need, file the team inbox, collect open data, and check for new agency report titles.";
	const m = await manifest();
	const models = createModels();
	const model = pickModel(models, FAUX);
	const registry = createRegistry();
	// The information agent gets only its own tools: it collects, reads and files; it does not answer
	// market questions (that is the Copilot).
	registry.install(infoExtension(m));
	const harness = await Harness.open(await openNodeSqliteStorage(env.PI_STORE ?? "./pi_durable.sqlite"),
		{ models, registry }, BACKGROUND_CONTEXT);
	harness.resume();

	const mapPath = env.PI_CONVERSATIONS ?? "./pi_conversations.json";
	const map: Record<string, string> = existsSync(mapPath) ? JSON.parse(readFileSync(mapPath, "utf8")) : {};
	let conv: any;
	try {
		conv = map["#info-agent"] ? await harness.conversation(map["#info-agent"] as any, BACKGROUND_CONTEXT) : undefined;
	} catch (err) {
		// A conversation that will not load (a run killed mid-write) is left in the store; a new one starts.
		process.stderr.write(`conversation ${map["#info-agent"]} could not be loaded, starting a new one: ${String(err)}\n`);
		conv = undefined;
	}
	if (!conv) {
		conv = await harness.createConversation({ ownership: { kind: "ownerless" }, agent: { model } } as any, BACKGROUND_CONTEXT);
		map["#info-agent"] = conv.id as string;
		writeFileSync(mapPath, JSON.stringify(map, null, 1));
	} else {
		await conv.configure({ model } as any, BACKGROUND_CONTEXT);
	}
	const submission = await conv.submit({ type: "input", content: instruction, requestId: REQUEST_ID }, BACKGROUND_CONTEXT);
	const settled = await submission.wait(BACKGROUND_CONTEXT);
	let answer = "";
	let failure: { reason: string; detail: unknown } | null = null;
	if (settled.status === "done" && settled.type === "input") {
		const entry = await conv.commit((tx) => tx.entry(AssistantEntry, settled.answer), BACKGROUND_CONTEXT);
		answer = ((entry?.model?.[0] as any)?.content ?? []).filter((b: any) => b.type === "text").map((b: any) => b.text).join("\n");
	} else {
		// The model API failed (budget, key, outage...): report it as a failure, not as an answer.
		failure = { reason: (settled as any).reason ?? settled.status, detail: (settled as any).detail ?? null };
	}
	await harness.close(BACKGROUND_CONTEXT);
	process.stdout.write(JSON.stringify({ answer, conversation: conv.id, model: `${model.provider}/${model.modelId}`,
		status: settled.status, failure }) + "\n");
}

if (import.meta.url === `file://${process.argv[1]}`) {
	main().catch((err) => {
		process.stderr.write(String(err?.stack ?? err) + "\n");
		process.exit(1);
	});
}
