/** Desk-like number formatting (thousands separators + fixed decimals). */

const NUMERIC_TYPES = new Set(["Int", "Float", "Currency", "Percent"]);

/** UI filter label YEN → ISO used by Currency / Desk formatters */
const CURRENCY_DISPLAY: Record<string, string> = {
	YEN: "JPY",
	JPY: "JPY",
	TZS: "TZS",
	USD: "USD",
};

export function resolveCurrencyCode(currency?: string | null): string | null {
	if (!currency) return null;
	const c = String(currency).trim().toUpperCase();
	if (!c || c === "CURRENCY") return null;
	return CURRENCY_DISPLAY[c] || c;
}

export function isNumericFieldtype(fieldtype?: string | null): boolean {
	return NUMERIC_TYPES.has(String(fieldtype || ""));
}

export function parseLooseNumber(v: unknown): number | null {
	if (v == null || v === "") return null;
	if (typeof v === "number") return Number.isFinite(v) ? v : null;
	const s = String(v).replace(/,/g, "").trim();
	if (!s) return null;
	const n = Number(s);
	return Number.isFinite(n) ? n : null;
}

/** Format like Frappe Desk Currency / Float display (e.g. 22,800,000.00). */
export function formatNumber(
	v: unknown,
	fieldtype?: string | null,
	currency?: string | null,
): string {
	const n = parseLooseNumber(v);
	if (n == null) return v == null || v === "" ? "—" : String(v);

	const ft = String(fieldtype || "");
	if (ft === "Int") {
		return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
	}
	if (ft === "Percent") {
		return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 6 });
	}
	if (ft === "Currency") {
		const formatted = n.toLocaleString(undefined, {
			minimumFractionDigits: 2,
			maximumFractionDigits: 2,
		});
		const code = resolveCurrencyCode(currency);
		return code ? `${code} ${formatted}` : formatted;
	}
	if (ft === "Float") {
		const hasFrac = !Number.isInteger(n);
		return n.toLocaleString(undefined, {
			minimumFractionDigits: hasFrac ? 2 : 2,
			maximumFractionDigits: 6,
		});
	}
	// Unknown / list cells without fieldtype: currency-style when fractional, else int
	if (Number.isInteger(n)) {
		return n.toLocaleString(undefined, { maximumFractionDigits: 0 });
	}
	return n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export function formatCellValue(
	v: unknown,
	fieldtype?: string | null,
	currency?: string | null,
): string {
	if (v == null || v === "") return "—";
	if (isNumericFieldtype(fieldtype) || typeof v === "number") {
		return formatNumber(
			v,
			fieldtype || (typeof v === "number" ? "Float" : undefined),
			currency,
		);
	}
	// numeric strings from API sometimes arrive as strings
	if (
		typeof v === "string" &&
		/^-?\d+(\.\d+)?$/.test(v) &&
		(fieldtype === "Currency" || fieldtype === "Float")
	) {
		return formatNumber(v, fieldtype, currency);
	}
	return String(v);
}
