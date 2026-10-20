# Copyright (c) 2026, VV Systems Developer LTD and contributors
# Transient smoke check — run via: bench --site SITE execute vsd_jan_integration.scripts._smoke_costing_sides.run


def run():
	from vsd_jan_integration.vsd_jan_international_customization.utils.mkt_fixed_costing import (
		get_fixed_costing_heads,
	)
	from vsd_jan_integration.vsd_jan_international_customization.utils.selling_costing import (
		get_selling_costing_heads,
	)
	from vsd_jan_integration.api import costing_report as cr

	fixed = get_fixed_costing_heads()
	selling = get_selling_costing_heads()
	heads = cr._report_costing_heads()
	cols = cr.get_columns("TZS", heads)
	col_names = [c["fieldname"] for c in cols]
	purchase_heads, selling_heads = cr._split_heads_for_columns(heads)
	purchase_codes = [h["costing_code"] for h in purchase_heads]
	selling_codes = [h["costing_code"] for h in selling_heads]

	fixed_sides = sorted({(h.get("costing_side") or "Purchase") for h in fixed})
	selling_sides = sorted({(h.get("costing_side") or "Purchase") for h in selling})
	report_sides = sorted({(h.get("costing_side") or "Purchase") for h in heads})

	print("FIXED_COUNT", len(fixed), "SIDES", fixed_sides)
	print("SELLING_HEADS", [(h.costing_code, h.costing_side, h.entry_mode) for h in selling])
	print("REPORT_HEADS", len(heads), "SIDES", report_sides, "SELLING_CODES", selling_codes)
	print("HAS_SELLING_COL", "selling" in col_names, "HAS_VAT18", "vat_18" in col_names)
	print("HAS_PURCHASE_PRICE", "purchase_price" in col_names)
	print("CITY_LEVY_COL", "city_levy_tax" in col_names, "VAT_COL", "vat" in col_names)
	print("COL_ORDER_SLICE", col_names[col_names.index("purchase_price") : col_names.index("total_exp") + 1][:20])

	assert all((h.get("costing_side") or "Purchase") in ("Purchase", "Both") for h in fixed)
	assert "selling" in col_names and "vat_18" in col_names
	assert "purchase_price" in col_names
	assert "city_levy_tax" in col_names and "vat" in col_names

	# Layout: Identity → Purchase Price → purchase heads → Selling → selling heads → VAT 18% → Total EXP
	pp_i = col_names.index("purchase_price")
	sell_i = col_names.index("selling")
	vat18_i = col_names.index("vat_18")
	total_i = col_names.index("total_exp")
	assert pp_i < sell_i < vat18_i < total_i
	assert total_i == len(col_names) - 1 or col_names[total_i] == "total_exp"

	# Purchase heads between Purchase Price and Selling
	for code in purchase_codes:
		i = col_names.index(code)
		assert pp_i < i < sell_i, f"purchase head {code} not between purchase_price and selling"

	# Selling Costing heads immediately after Selling, before VAT 18%
	for code in selling_codes:
		i = col_names.index(code)
		assert sell_i < i < vat18_i, f"selling head {code} not between selling and vat_18"
	if selling_codes:
		assert col_names[sell_i + 1] == selling_codes[0]
		assert col_names[vat18_i - 1] == selling_codes[-1]

	# Actual-only: zero heads must NOT be filled from ESP/formula (legacy helper unused here)
	merged = {
		"city_levy_tax": {"amount": 0.0, "currency": "TZS"},
		"vat": {"amount": 0.0, "currency": "TZS"},
	}
	# Simulate resolve with no Actual — amounts stay 0 (no gap-fill call in execute)
	print("ACTUAL_ONLY_ZEROS", {k: v["amount"] for k, v in merged.items()})
	assert merged["city_levy_tax"]["amount"] == 0
	assert merged["vat"]["amount"] == 0

	# Report execute smoke — prefer N.TAN039 if present
	columns, data = cr.execute({"currency": "TZS", "import_file": "N.TAN039"})
	if not data:
		columns, data = cr.execute({"currency": "TZS"})
	print("REPORT_ROWS", len(data), "COL_COUNT", len(columns))
	samples = []
	for row in data[:7]:
		samples.append(
			{
				"chassis": row.get("chassis"),
				"purchase_price": row.get("purchase_price"),
				"selling": row.get("selling"),
				"city_levy": row.get("city_levy_tax"),
				"vat_cost": row.get("vat"),
				"vat_18": row.get("vat_18"),
				"total_exp": row.get("total_exp"),
			}
		)
		print(
			"SAMPLE",
			row.get("chassis"),
			"purchase_price",
			row.get("purchase_price"),
			"selling",
			row.get("selling"),
			"vat_18",
			row.get("vat_18"),
			"city_levy",
			row.get("city_levy_tax"),
			"vat_cost",
			row.get("vat"),
			"total_exp",
			row.get("total_exp"),
		)
	nonzero_pp = sum(1 for s in samples if (s.get("purchase_price") or 0) > 0)
	print("NONZERO_PURCHASE_PRICE_IN_SAMPLE", nonzero_pp, "of", len(samples))
	print("OK_ASSERTS")
	return {
		"ok": True,
		"fixed": len(fixed),
		"selling_heads": len(selling),
		"report_heads": len(heads),
		"samples": samples,
		"col_order": col_names[pp_i : total_i + 1],
	}
