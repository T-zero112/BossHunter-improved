import { Checkbox as CheckboxPrimitive } from "@base-ui/react/checkbox";
import { CheckIcon, MinusIcon } from "@phosphor-icons/react";
import { cn } from "@reactive-resume/utils/style";

function Checkbox({ className, ...props }: CheckboxPrimitive.Root.Props) {
	return (
		<CheckboxPrimitive.Root
			data-slot="checkbox"
			className={cn(
				"peer flex size-4 shrink-0 items-center justify-center rounded-[4px] border border-input shadow-xs outline-none transition-shadow focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 aria-invalid:border-destructive data-disabled:cursor-not-allowed data-checked:border-primary data-indeterminate:border-primary data-checked:bg-primary data-indeterminate:bg-primary data-checked:text-primary-foreground data-indeterminate:text-primary-foreground data-disabled:opacity-50",
				className,
			)}
			{...props}
		>
			<CheckboxPrimitive.Indicator
				data-slot="checkbox-indicator"
				className="flex items-center justify-center text-current"
			>
				{props.indeterminate ? (
					<MinusIcon weight="bold" className="size-3" />
				) : (
					<CheckIcon weight="bold" className="size-3" />
				)}
			</CheckboxPrimitive.Indicator>
		</CheckboxPrimitive.Root>
	);
}

export { Checkbox };
