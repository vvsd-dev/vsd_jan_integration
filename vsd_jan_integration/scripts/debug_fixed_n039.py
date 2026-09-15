"""Debug recreate Fixed JE for one N039 car."""
import frappe


def run():
	from vsd_jan_integration.vsd_jan_international_customization.utils.mkt_fixed_costing import (
		create_or_update_fixed_costing_journal_entry,
		get_fixed_costing_heads,
		_build_fixed_je_template,
	)

	heads = get_fixed_costing_heads()
	print("heads", [h.costing_code for h in heads])
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	tpl = _build_fixed_je_template(company, heads)
	print("template ok", tpl.get("ok"), "lines", len(tpl.get("lines") or []), "err", tpl.get("error"))

	item = "TOYOTA NOAH - ZRR70-0198971"
	cheque = f"FIXED|{item}"[:140]
	print(
		"existing JE",
		frappe.get_all(
			"Journal Entry",
			filters={"cheque_no": cheque},
			fields=["name", "docstatus"],
		),
	)
	try:
		name, created = create_or_update_fixed_costing_journal_entry(
			item, import_file="N.TAN039/26MSC", company=company, auto_submit=False, template=tpl
		)
		print("result", name, created)
	except Exception:
		print(frappe.get_traceback())
	# latest error log
	err = frappe.get_all("Error Log", order_by="creation desc", limit=3, fields=["name", "method", "creation"])
	for e in err:
		print("ERR", e.name, e.method, e.creation)
		doc = frappe.get_doc("Error Log", e.name)
		print(doc.error[:800] if doc.error else "")
