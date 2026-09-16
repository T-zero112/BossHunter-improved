import { useInView, useMotionValue, useSpring } from "motion/react";
import { useCallback, useEffect, useEffectEvent, useRef } from "react";

type CountUpProps = {
	to: number;
	duration?: number;
	className?: string;
	separator?: string;
	"aria-hidden"?: boolean | "true" | "false";
	"aria-live"?: "off" | "polite" | "assertive";
	"aria-atomic"?: boolean | "true" | "false";
};

const getDecimalPlaces = (num: number): number => {
	const str = num.toString();
	if (str.includes(".")) {
		const decimals = str.split(".")[1];
		if (Number.parseInt(decimals, 10) !== 0) return decimals.length;
	}
	return 0;
};

// ponytail: from/direction/delay/startWhen/onStart/onEnd removed — no production caller passes them
export function CountUp({
	to,
	duration = 2,
	className = "",
	separator = "",
	"aria-hidden": ariaHidden,
	"aria-live": ariaLive = "polite",
	"aria-atomic": ariaAtomic = "true",
}: CountUpProps) {
	const ref = useRef<HTMLSpanElement>(null);
	const motionValue = useMotionValue(0);

	const damping = 20 + 40 * (1 / duration);
	const stiffness = 100 * (1 / duration);

	const springValue = useSpring(motionValue, { damping, stiffness });

	const isInView = useInView(ref, { once: true, margin: "0px" });

	const maxDecimals = getDecimalPlaces(to);

	const formatValue = useCallback(
		(latest: number) => {
			const options: Intl.NumberFormatOptions = {
				useGrouping: !!separator,
				minimumFractionDigits: maxDecimals,
				maximumFractionDigits: maxDecimals,
			};
			const formattedNumber = Intl.NumberFormat("en-US", options).format(latest);
			return separator ? formattedNumber.replace(/,/g, separator) : formattedNumber;
		},
		[maxDecimals, separator],
	);

	const formatCurrentValue = useEffectEvent((latest: number) => formatValue(latest));

	useEffect(() => {
		if (ref.current) ref.current.textContent = formatCurrentValue(0);
	}, []);

	useEffect(() => {
		if (isInView) motionValue.set(to);
	}, [isInView, motionValue, to]);

	useEffect(() => {
		const unsubscribe = springValue.on("change", (latest: number) => {
			if (ref.current) ref.current.textContent = formatCurrentValue(latest);
		});
		return () => unsubscribe();
	}, [springValue]);

	return (
		<span
			ref={ref}
			className={className}
			aria-hidden={ariaHidden}
			aria-live={ariaHidden ? undefined : ariaLive}
			aria-atomic={ariaHidden ? undefined : ariaAtomic}
		/>
	);
}
