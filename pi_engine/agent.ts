// Pi Durable engine for the London Office Market Agent.
//
// The Python app owns the data, skills and UI and serves its tools on a local
// HTTP bridge. This script runs one question through a Pi Durable harness:
// every model turn and tool call is committed to SQLite before it is shown, so
// a crashed run resumes from its last checkpoint when it is retried with the
// same REQUEST_ID. Each person keeps their own persistent conversation.
//
// Input: the question on stdin. Output: JSON lines on stdout: progress events while the model works
// ({"event":"delta","text":...} for each piece of the answer, {"event":"tool","name":...} when a tool
// starts, {"event":"tool_end","name":...} when it ends), then one final line with the answer.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { createModels } from "@earendil-works/pi-ai";
import { AssistantEntry, createRegistry, defineExtension, Harness, section, watchEvents } from "@earendil-works/pi-durable";
import { openNodeSqliteStorage } from "@earendil-works/pi-durable/storage/sqlite/node";
import { bridgeTool, env, manifest as getManifest, pickModel, REQUEST_ID, ROLE } from "./common.ts";
import type { BridgeTool } from "./common.ts";
import { GATHER, INTERNAL, infoExtension, NATIVE } from "./info_agent.ts";

const context = BACKGROUND_CONTEXT;
// Scripted model for tests: one tool call, then an answer.
const FAUX = [{ tool: "get_signals", args: { limit: 3 } },
	{ text: "Faux model answer: the top signals were fetched through Pi Durable." }];

async function main() {
	const question = readFileSync(0, "utf8").trim();
	const manifest = await getManifest();
	// Collecting and reading tools come from the market-info extension (the information agent's toolset).
	const gatherNames = [...GATHER, ...NATIVE, ...INTERNAL];
	const tools = (manifest.tools as BridgeTool[]).filter((t) => !gatherNames.includes(t.name)).map(bridgeTool);

	const models = createModels();
	const model = pickModel(models, FAUX);
	const registry = createRegistry();
	registry.install(defineExtension({
		name: "london-office-market",
		sections: [section("market-agent", () => manifest.system as string, { tag: false })],
		tools,
	}));
	registry.install(infoExtension(manifest));

	const harness = await Harness.open(await openNodeSqliteStorage(env.PI_STORE ?? "./pi_durable.sqlite"),
		{ models, registry }, context);
	harness.resume(); // finish anything a previous process left mid-run

	// One persistent conversation per chat (PI_CONVERSATION_KEY, the web app's chat id) or, without one, per
	// person (the CLI), so follow-up questions keep context and a new chat starts clean.
	const KEY = env.PI_CONVERSATION_KEY ?? ROLE;
	const mapPath = env.PI_CONVERSATIONS ?? "./pi_conversations.json";
	const map: Record<string, string> = existsSync(mapPath) ? JSON.parse(readFileSync(mapPath, "utf8")) : {};
	let conversation: any;
	try {
		conversation = map[KEY] ? await harness.conversation(map[KEY] as any, context) : undefined;
	} catch (err) {
		// A conversation that will not load (a run killed mid-write) is left in the store; a new one starts.
		process.stderr.write(`conversation ${map[KEY]} could not be loaded, starting a new one: ${String(err)}\n`);
		conversation = undefined;
	}
	if (!conversation) {
		conversation = await harness.createConversation({ ownership: { kind: "ownerless" }, agent: { model } } as any, context);
		map[KEY] = conversation.id as string;
		writeFileSync(mapPath, JSON.stringify(map, null, 1));
	} else {
		await conversation.configure({ model } as any, context);
	}

	// Stream the answer as it is written: text deltas and tool starts go to stdout as they happen, so the
	// web app can show them before the turn is finished.
	const emit = (e: Record<string, unknown>) => process.stdout.write(JSON.stringify({ event: e.type, ...e, type: undefined }) + "\n");
	const stream = await watchEvents(harness, conversation.id as any, context);
	let streamed = 0, inMessage = 0;  // characters streamed in total, and in the message being written
	// text of an assistant message; user input and tool results (string content) give ""
	const textOf = (m: any) => m?.role === "assistant" && Array.isArray(m.content)
		? m.content.filter((b: any) => b.type === "text").map((b: any) => b.text).join("") : "";
	stream.start(async (events) => {
		for (const ev of events as any[]) {
			if (env.PI_DEBUG === "1") process.stderr.write(`[event] ${ev.type}\n`);
			try { onEvent(ev); } catch (err) { process.stderr.write(`[event] listener error: ${String(err)}\n`); }
		}
	});
	function onEvent(ev: any) {
		{
			if (ev.type === "message_start") inMessage = 0;
			else if (ev.type === "message_update") {
				for (const ch of ev.changes) {
					if (ch.type === "text_delta") { streamed += ch.delta.length; inMessage += ch.delta.length; emit({ type: "delta", text: ch.delta }); }
					else if (ch.type === "block" && ch.block?.type === "text" && ch.block.text && inMessage === 0) {
						// a provider (or the scripted test model) that gives whole blocks instead of deltas
						streamed += ch.block.text.length; inMessage += ch.block.text.length; emit({ type: "delta", text: ch.block.text });
					} else if (ch.type === "message" && inMessage === 0 && textOf(ch.message)) {
						const t = textOf(ch.message); streamed += t.length; inMessage += t.length; emit({ type: "delta", text: t });
					}
				}
			} else if (ev.type === "message_end") {
				// a message that arrived whole (no deltas at all): send its text now so the page still shows it live
				const t = textOf((ev.entry as any)?.model?.[0] ?? (ev.entry as any)?.message);
				if (inMessage === 0 && t) { streamed += t.length; emit({ type: "delta", text: t }); }
				inMessage = 0;
				emit({ type: "message_end" });
			} else if (ev.type === "tool_execution_start") emit({ type: "tool", name: ev.toolName, args: ev.args });
			else if (ev.type === "tool_execution_end") emit({ type: "tool_end", name: ev.toolName });
		}
	}
	// Same requestId after a crash finds the same submission instead of asking twice.
	const submission = await conversation.submit({ type: "input", content: question, requestId: REQUEST_ID }, context);
	const settled = await submission.wait(context);
	await stream.stop();
	let answer = "";
	let failure: { reason: string; detail: unknown } | null = null;
	if (settled.status === "done" && settled.type === "input") {
		const entry = await conversation.commit((tx) => tx.entry(AssistantEntry, settled.answer), context);
		const message: any = entry?.model?.[0];
		answer = (message?.content ?? []).filter((b: any) => b.type === "text").map((b: any) => b.text).join("\n");
	} else {
		// The model API failed (budget, key, outage...): report it as a failure, not as an answer.
		failure = { reason: (settled as any).reason ?? settled.status, detail: (settled as any).detail ?? null };
	}
	await harness.close(context);
	process.stdout.write(JSON.stringify({ answer, conversation: conversation.id, model: `${model.provider}/${model.modelId}`,
		status: settled.status, failure, streamed }) + "\n");
}

main().catch((err) => {
	process.stderr.write(String(err?.stack ?? err) + "\n");
	process.exit(1);
});
