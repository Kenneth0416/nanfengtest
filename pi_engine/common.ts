// Shared by the Copilot engine (agent.ts) and the gatherer (gather.ts): Python tools over the local
// bridge become Pi Durable tools, and the model is picked from the environment.
import {
	createModels, fauxAssistantMessage, fauxProvider, fauxText, fauxToolCall, Type,
} from "@earendil-works/pi-ai";
import { anthropicProvider } from "@earendil-works/pi-ai/providers/anthropic";
import { openaiProvider } from "@earendil-works/pi-ai/providers/openai";
import { xiaomiProvider } from "@earendil-works/pi-ai/providers/xiaomi";
import { defineTool } from "@earendil-works/pi-durable";
import { readFileSync } from "node:fs";

export const env = process.env;
export const BRIDGE = env.BRIDGE_URL ?? "http://127.0.0.1:8765";
export const ROLE = env.ROLE ?? "team";
export const REQUEST_ID = env.REQUEST_ID ?? `req-${Date.now()}`;

export type JsonSchema = { type?: string; description?: string; enum?: string[]; items?: JsonSchema;
	properties?: Record<string, JsonSchema>; required?: string[] };
export type BridgeTool = { name: string; description: string; parameters: JsonSchema; readOnly: boolean };

// Python tools describe their arguments in JSON Schema; Pi Durable validates with TypeBox.
export function toTypeBox(s: JsonSchema): any {
	const opts = s.description ? { description: s.description } : {};
	if (s.enum) return Type.Union(s.enum.map((v) => Type.Literal(v)), opts);
	switch (s.type) {
		case "string": return Type.String(opts);
		case "number": return Type.Number(opts);
		case "integer": return Type.Integer(opts);
		case "boolean": return Type.Boolean(opts);
		case "array": return Type.Array(toTypeBox(s.items ?? {}), opts);
		case "object": {
			const props: Record<string, any> = {};
			for (const [k, v] of Object.entries(s.properties ?? {})) {
				props[k] = (s.required ?? []).includes(k) ? toTypeBox(v) : Type.Optional(toTypeBox(v));
			}
			return Type.Object(props, opts);
		}
		default: return Type.Any(opts);
	}
}

export async function callPython(tool: string, args: unknown): Promise<any> {
	const res = await fetch(`${BRIDGE}/call`, {
		method: "POST",
		headers: { "content-type": "application/json", "x-request-id": REQUEST_ID },
		body: JSON.stringify({ tool, args, role: ROLE }),
	});
	const body = await res.json();
	if (!res.ok) throw new Error(body.error ?? `tool ${tool} failed`);
	return body;
}

export function bridgeTool(t: BridgeTool) {
	return defineTool({
		name: t.name,
		description: t.description,
		parameters: toTypeBox(t.parameters),
		// Read-only tools may rerun after a crash; a write reports "interrupted" instead.
		replay: t.readOnly ? "safe" : undefined,
		execute: async (args: unknown) => ({ content: [{ type: "text", text: JSON.stringify(await callPython(t.name, args)) }] }),
	} as any);
}

export async function manifest(): Promise<any> {
	return (await fetch(`${BRIDGE}/manifest?role=${encodeURIComponent(ROLE)}`)).json();
}

// PI_FAUX=1 runs a scripted model for tests (no API key). PI_FAUX_SCRIPT points at a JSON list of
// steps: {"tool": name, "args": {...}} for a tool call, or {"text": "..."} for the final answer.
export function pickModel(models: ReturnType<typeof createModels>, defaultScript: any[]) {
	if (env.PI_FAUX === "1") {
		const faux = fauxProvider({});
		models.setProvider(faux.provider);
		const steps = env.PI_FAUX_SCRIPT ? JSON.parse(readFileSync(env.PI_FAUX_SCRIPT, "utf8")) : defaultScript;
		faux.setResponses(steps.map((s: any) => s.tool
			? fauxAssistantMessage([fauxToolCall(s.tool, s.args ?? {})], { stopReason: "toolUse" })
			: fauxAssistantMessage([fauxText(s.text)])));
		return { provider: faux.getModel().provider, modelId: faux.getModel().id };
	}
	if (env.XIAOMI_API_KEY) {  // the project default: Xiaomi MiMo (Python passes MIMO_API_KEY through as this)
		models.setProvider(xiaomiProvider());
		return { provider: "xiaomi", modelId: env.MIMO_MODEL ?? "mimo-v2.6-flash" };
	}
	if (env.ANTHROPIC_API_KEY) {
		models.setProvider(anthropicProvider());
		return { provider: "anthropic", modelId: env.ANTHROPIC_MODEL ?? "claude-opus-5-5" };
	}
	if (env.OPENAI_API_KEY) {
		models.setProvider(openaiProvider());
		return { provider: "openai", modelId: env.OPENAI_MODEL ?? "gpt-5.5" };
	}
	throw new Error("Set MIMO_API_KEY, ANTHROPIC_API_KEY or OPENAI_API_KEY (or PI_FAUX=1 for a scripted test run)");
}
