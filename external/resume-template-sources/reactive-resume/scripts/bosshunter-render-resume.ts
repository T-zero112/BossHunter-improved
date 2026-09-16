import { basename } from "node:path";
import { readFile, writeFile } from "node:fs/promises";
import { createResumePdfFile } from "../packages/pdf/src/server";

async function main() {
	const [inputPath, outputPath] = process.argv.slice(2);

	if (!inputPath || !outputPath) {
		console.error("Usage: tsx scripts/bosshunter-render-resume.ts <input.json> <output.pdf>");
		process.exit(2);
	}

	const payload = JSON.parse(await readFile(inputPath, "utf-8")) as {
		template?: string;
		data?: Record<string, unknown>;
	};

	if (!payload.data) {
		console.error("Input JSON must contain a data object.");
		process.exit(2);
	}

	const file = await createResumePdfFile({
		data: payload.data as never,
		filename: basename(outputPath),
		template: payload.template as never,
	});

	await writeFile(outputPath, new Uint8Array(await file.arrayBuffer()));
}

main().catch((error: unknown) => {
	console.error(error);
	process.exit(1);
});
