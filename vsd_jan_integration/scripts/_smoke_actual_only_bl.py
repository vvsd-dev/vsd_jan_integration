# Copyright (c) 2026, VV Systems Developer LTD and contributors
# Transient smoke: Selling/VAT from submitted SI only; no ESP / Item selling fallback.


def run():
	import frappe
	from frappe.utils import flt
	from vsd_jan_integration.api import costing_report as cr

	chassis_list = ["YF15-019010", "ZRR70-0198971", "KDH200-0045678", "NSP120-2035270"]
	ccs = frappe.get_all(
		"Car Costing",
		filters={"chassis_no": ["in", chassis_list]},
		fields=["name", "item", "chassis_no", "expected_selling_price"],
	)
	print("CCS", [(c.chassis_no, c.item, c.expected_selling_price) for c in ccs])
	items = [c.item for c in ccs]
	heads = cr._report_costing_heads()
	heads_by_name = {h["name"]: h for h in heads}
	heads_by_account = cr._heads_by_account(heads)

	if frappe.db.table_exists("Item Costing Line"):
		rows = frappe.db.sql(
			"""
			SELECT parent, costing_code, actual_amount, projected_amount, currency
			FROM `tabItem Costing Line`
			WHERE parent IN %(items)s AND costing_code IN ('city_levy_tax','vat')
			""",
			{"items": items},
			as_dict=True,
		)
		print("ITEM_LINES", rows)

	import_files = list(
		{
			r.import_file
			for r in frappe.get_all(
				"Car Costing",
				filters={"item": ["in", items]},
				fields=["import_file"],
			)
			if r.import_file
		}
	)
	ifcv, on_ifcv = cr._load_ifcv_allocations(import_files, heads_by_name)
	for it in items:
		print(
			"IFCV",
			it,
			{k: v for k, v in (ifcv.get(it) or {}).items() if k in ("city_levy_tax", "vat")},
			"on_ifcv",
			it in on_ifcv,
		)

	je = cr._load_je_by_item([], heads_by_account, item_codes=items)
	for it in items:
		print(
			"JE",
			it,
			{k: v for k, v in (je.get(it) or {}).items() if k in ("city_levy_tax", "vat")},
		)

	# Cars with ESP but no submitted SI — Selling / VAT 18% must be 0;
	# City Levy / VAT heads must be 0 unless Actual/JE exists (no ESP formula).
	esp_cars = frappe.db.sql(
		"""
		SELECT cc.name, cc.item, cc.chassis_no, cc.expected_selling_price
		FROM `tabCar Costing` cc
		WHERE IFNULL(cc.expected_selling_price, 0) > 0
		AND NOT EXISTS (
			SELECT 1 FROM `tabSales Invoice Item` sii
			INNER JOIN `tabSales Invoice` si ON si.name = sii.parent AND si.docstatus = 1
			WHERE sii.item_code = cc.item
		)
		LIMIT 8
		""",
		as_dict=True,
	)
	print(
		"ESP_CANDIDATES",
		[(r.chassis_no, r.item, r.expected_selling_price) for r in esp_cars],
	)

	checked = []
	for r in esp_cars:
		_cols, data = cr.execute({"currency": "TZS", "chassis": r.chassis_no})
		for row in data:
			if row.get("chassis") != r.chassis_no:
				continue
			item_sell = flt(
				frappe.db.get_value("Item", r.item, "custom_selling_price")
				if frappe.db.has_column("Item", "custom_selling_price")
				else 0
			)
			# No SI → Selling / VAT 18% must be 0 (ESP and Item selling ignored)
			assert flt(row.get("selling")) == 0, (
				f"{r.chassis_no}: selling not SI-only "
				f"(esp={r.expected_selling_price}, item_sell={item_sell}) → {row.get('selling')}"
			)
			assert flt(row.get("vat_18")) == 0, (
				f"{r.chassis_no}: vat_18 without SI → {row.get('vat_18')}"
			)
			# City levy / vat from ESP formula would be esp*0.003 / esp*0.18*0.2
			esp = flt(r.expected_selling_price)
			formula_levy = esp * 0.003
			formula_vat = esp * 0.18 * 0.2
			actual = cr._load_item_actuals([r.item]).get(r.item) or {}
			je_map = (je.get(r.item) if je else None) or cr._load_je_by_item(
				[], heads_by_account, item_codes=[r.item]
			).get(r.item) or {}
			has_actual_levy = flt((actual.get("city_levy_tax") or {}).get("amount")) or flt(
				(je_map.get("city_levy_tax") or {}).get("amount")
			)
			has_actual_vat = flt((actual.get("vat") or {}).get("amount")) or flt(
				(je_map.get("vat") or {}).get("amount")
			)
			levy = flt(row.get("city_levy_tax"))
			vat = flt(row.get("vat"))
			if not has_actual_levy and abs(levy - formula_levy) < 1 and levy > 0:
				raise AssertionError(
					f"{r.chassis_no}: city_levy matches ESP formula without Actual ({levy})"
				)
			if not has_actual_vat and abs(vat - formula_vat) < 1 and vat > 0:
				raise AssertionError(
					f"{r.chassis_no}: vat matches ESP formula without Actual ({vat})"
				)
			checked.append(
				{
					"chassis": r.chassis_no,
					"esp": esp,
					"item_sell": item_sell,
					"selling": row.get("selling"),
					"vat_18": row.get("vat_18"),
					"city_levy": levy,
					"vat": vat,
					"has_actual_levy": has_actual_levy,
					"has_actual_vat": has_actual_vat,
				}
			)
			print("CHECK", checked[-1])
			break

	# Zero-actual car with ESP: heads that previously came from formula should be 0
	zero_esp = None
	for c in checked:
		if not c["has_actual_levy"] and not c["has_actual_vat"] and c["esp"] > 0:
			zero_esp = c
			break
	print("ZERO_ACTUAL_WITH_ESP", zero_esp)
	print("OK_SI_ONLY_SELLING")
	return {"ok": True, "checked": checked, "zero_esp_sample": zero_esp}
