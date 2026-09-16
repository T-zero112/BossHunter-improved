import type { ReactNode } from "react";
import type { DialogSchema, DialogType } from "./schemas";

// ponytail: defineDialogRenderer/defineDialogRendererRegistry were identity fns; inlined
type DialogRendererEntry<T extends DialogType = DialogType> = {
	type: T;
	render: (dialog: Extract<DialogSchema, { type: T }>) => ReactNode;
};

export type AnyDialogRendererEntry = {
	[T in DialogType]: DialogRendererEntry<T>;
}[DialogType];
