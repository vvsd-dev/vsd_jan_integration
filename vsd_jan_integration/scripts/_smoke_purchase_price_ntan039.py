# Copyright (c) 2026, VV Systems Developer LTD and contributors
# Transient — bench --site SITE execute vsd_jan_integration.scripts._smoke_purchase_price_ntan039.run


def run(import_file="N.TAN039/26MSC", currency="YEN"):
	from vsd_jan_integration.api.costing_report import execute

	cols, data = execute({"currency": currency, "import_file": import_file})
	names = [c["fieldname"] for c in cols]
	pp_i = names.index("purchase_price")
	print("LAYOUT", names[pp_i:])
	want = {
		"ZRR70-0198971": 217000,
		"NSP140-9011378": 118000,
		"RT1-1006295": 172000,
		"GRS180-0026901": 174000,
		"ANH20-8050726": 202000,
		"ANH15-0044728": 234000,
		"TRN215-0021658": 1257000,
	}
	by = {r.get("chassis"): r for r in data}
	rows = []
	for ch, excel_yen in want.items():
		r = by.get(ch)
		if not r:
			print("MISSING", ch)
			continue
		pp = r.get("purchase_price")
		rows.append(
			{
				"chassis": ch,
				"excel_yen": excel_yen,
				"purchase_price": pp,
				"selling": r.get("selling"),
				"city_levy_tax": r.get("city_levy_tax"),
				"vat": r.get("vat"),
				"vat_18": r.get("vat_18"),
			}
		)
		print(
			ch,
			"excel",
			excel_yen,
			"pp",
			pp,
			"selling",
			r.get("selling"),
			"city",
			r.get("city_levy_tax"),
			"vat",
			r.get("vat"),
		)
	print("ROWS", len(data), "MATCHED", len(rows))
	return {"ok": True, "layout": names[pp_i:], "rows": rows, "currency": currency, "import_file": import_file}
