# Debug why report shows 0 for Fixed heads despite submitted JEs
import frappe
from vsd_jan_integration.api import costing_report as cr

def execute():
	cols, data = cr.execute({"currency": "TZS", "import_file": "N.TAN039/26MSC"})
	fixed_codes = [
		"bond_insurance",
		"service",
		"driver_port_to_yard",
		"ex_bond",
		"inspection",
		"japan_cost",
	]
	print("rows", len(data))
	for i, row in enumerate(data):
		vals = {}
		for c in fixed_codes:
			vals[c] = row.get(c)
		print(
			i,
			"item=",
			row.get("item"),
			"chassis=",
			row.get("chassis"),
			"vals=",
			vals,
			"total=",
			row.get("total_exp"),
		)

	item = data[0]["item"] if data else None
	if not item:
		return
	heads = cr._landed_costing_heads()
	hba = cr._heads_by_account(heads)
	hbn = {h["name"]: h for h in heads}
	je_by = cr._load_je_by_item(["N.TAN039/26MSC"], hba)
	ifcv, on = cr._load_ifcv_allocations(["N.TAN039/26MSC"], hbn)
	act = cr._load_item_actuals([d["item"] for d in data])
	print("je_by keys", list(je_by.keys()))
	print("items_on_ifcv", on)
	print("item_actuals keys", list(act.keys()))
	for d in data:
		it = d["item"]
		full = cr._load_item_actuals_including_zero([it], only_items=on | set(act))
		raw, src = cr._resolve_head_amounts(it, heads, act, full, ifcv, on, je_by)
		print("RESOLVE", it, "src=", src)
		for c in fixed_codes:
			print(" ", c, raw.get(c))
		# also show if nonzero actuals block JE
		print("  nonzero_act", act.get(it))
		print("  je", je_by.get(it))
