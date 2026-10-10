// Pi Durable engine for the London Office Market Agent.
//
// The Python app owns the data, skills and UI and serves its tools on a local
// HTTP bridge. This script runs one question through a Pi Durable harness:
// every model turn and tool call is committed to SQLite before it is shown, so
// a crashed run resumes from its last checkpoint when it is retried with the
// same REQUEST_ID. Each person keeps their own persistent conversation.
//
// Input: the question on stdin. Output: one JSON line on stdout.
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { BACKGROUND_CONTEXT } from "@earendil-works/chord/context";
import { createModels } from "@earendil-works/pi-ai";
import { AssistantEntry, createRegistry, defineExtension, Harness, section } from "@earendil-works/pi-durable";
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

	// One persistent conversation per person, so follow-up questions keep context.
	const mapPath = env.PI_CONVERSATIONS ?? "./pi_conversations.json";
	const map: Record<string, string> = existsSync(mapPath) ? JSON.parse(readFileSync(mapPath, "utf8")) : {};
	let conversation: any;
	try {
		conversation = map[ROLE] ? await harness.conversation(map[ROLE] as any, context) : undefined;
	} catch (err) {
		// A conversation that will not load (a run killed mid-write) is left in the store; a new one starts.
		process.stderr.write(`conversation ${map[ROLE]} could not be loaded, starting a new one: ${String(err)}\n`);
		conversation = undefined;
	}
	if (!conversation) {
		conversation = await harness.createConversation({ ownership: { kind: "ownerless" }, agent: { model } } as any, context);
		map[ROLE] = conversation.id as string;
		writeFileSync(mapPath, JSON.stringify(map, null, 1));
	} else {
		await conversation.configure({ model } as any, context);
	}

	// Same requestId after a crash finds the same submission instead of asking twice.
	const submission = await conversation.submit({ type: "input", content: question, requestId: REQUEST_ID }, context);
	const settled = await submission.wait(context);
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
		status: settled.status, failure }) + "\n");
}

main().catch((err) => {
	process.stderr.write(String(err?.stack ?? err) + "\n");
	process.exit(1);
});
