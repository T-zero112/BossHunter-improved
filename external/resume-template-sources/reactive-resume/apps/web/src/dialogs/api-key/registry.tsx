import type { AnyDialogRendererEntry } from "../renderer-registry";
import { CreateApiKeyDialog } from "./create";

export const apiKeyDialogRenderers: readonly AnyDialogRendererEntry[] = [
	{ type: "api-key.create", render: () => <CreateApiKeyDialog /> },
];
