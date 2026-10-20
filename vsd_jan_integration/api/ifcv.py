import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def get_ifcv(name):
	frappe.has_permission("Import File Cost Voucher", "read", throw=True)
	if not name or not frappe.db.exists("Import File Cost Voucher", name):
		frappe.throw(_("IFCV {0} not found").format(name), frappe.DoesNotExistError)

	doc = frappe.get_doc("Import File Cost Voucher", name)
	return {
		"name": doc.name,
		"import_file": doc.import_file,
		"posting_date": doc.posting_date,
		"docstatus": doc.docstatus,
		"company_currency": doc.get("company_currency"),
		"usd_currency": doc.get("usd_currency"),
		"jpy_currency": doc.get("jpy_currency"),
		"exchange_rate_company_usd": flt(doc.get("exchange_rate_company_usd")),
		"exchange_rate_usd_jpy": flt(doc.get("exchange_rate_usd_jpy")),
		"total_expense_amount": flt(doc.get("total_expense_amount")),
		"total_allocated_amount": flt(doc.get("total_allocated_amount")),
		"vehicles": [
			{
				"item": r.item,
				"chassis_no": r.get("chassis_no"),
				"maker": r.get("maker"),
				"stock_id": r.get("stock_id") or r.get("new_stock_id"),
				"m3": flt(r.get("m3")),
				"applicable_charges": flt(r.get("applicable_charges")),
				"applicable_charges_usd": flt(r.get("applicable_charges_usd")),
				"applicable_charges_yen": flt(r.get("applicable_charges_yen")),
				"exchange_rate": flt(r.get("exchange_rate")),
			}
			for r in (doc.vehicles or [])
		],
		"expenses": [
			{
				"idx": r.idx,
				"costing_head": r.get("costing_head"),
				"costing_code": r.get("costing_code"),
				"expense_account": r.get("expense_account"),
				"currency": r.get("currency"),
				"amount": flt(r.get("amount")),
				"distribution_method": r.get("distribution_method"),
				"source": r.get("source"),
				"description": r.get("description") or r.get("remarks"),
			}
			for r in (doc.expenses or [])
		],
		"allocations": [
			{
				"item": r.item,
				"account": r.get("account"),
				"currency": r.get("currency"),
				"amount": flt(r.get("amount")),
				"costing_head": r.get("costing_head"),
				"source_row": r.get("source_row"),
			}
			for r in (doc.allocations or [])
		],
	}


@frappe.whitelist()
def get_vehicle_ledger(name, item):
	"""Per-vehicle allocation ledger matching Desk View by Vehicle totals."""
	data = get_ifcv(name)
	vehicles = data.get("vehicles") or []
	vehicle = next((v for v in vehicles if v.get("item") == item), None)
	if not vehicle:
		frappe.throw(_("Vehicle {0} not found on this IFCV").format(item))

	expenses_by_idx = {e["idx"]: e for e in (data.get("expenses") or [])}
	rows = []
	for a in data.get("allocations") or []:
		if a.get("item") != item or not flt(a.get("amount")):
			continue
		exp = expenses_by_idx.get(a.get("source_row")) if a.get("source_row") else None
		rows.append(
			{
				"costing": a.get("costing_head") or (exp or {}).get("costing_head") or "",
				"code": (exp or {}).get("costing_code") or a.get("costing_head") or "",
				"account": a.get("account") or (exp or {}).get("expense_account") or "—",
				"currency": a.get("currency") or (exp or {}).get("currency") or "",
				"method": (exp or {}).get("distribution_method") or "",
				"source": (exp or {}).get("source") or "",
				"description": (exp or {}).get("description") or "",
				"amount": flt(a.get("amount")),
			}
		)
	rows.sort(key=lambda r: r.get("costing") or "")

	company_cur = data.get("company_currency") or "TZS"
	usd_cur = data.get("usd_currency") or "USD"
	jpy_cur = data.get("jpy_currency") or "JPY"
	usd_rate = flt(data.get("exchange_rate_company_usd")) or 1
	yen_rate = flt(vehicle.get("exchange_rate")) or 1

	company_total = flt(vehicle.get("applicable_charges"))
	if not company_total:
		company_total = sum(flt(r.get("amount")) for r in rows)

	usd_total = flt(vehicle.get("applicable_charges_usd"))
	yen_total = flt(vehicle.get("applicable_charges_yen"))
	if not usd_total and usd_rate:
		usd_total = company_total / usd_rate
	if not yen_total and yen_rate:
		yen_total = company_total / yen_rate

	return {
		"vehicle": vehicle,
		"rows": rows,
		"company_currency": company_cur,
		"usd_currency": usd_cur,
		"jpy_currency": jpy_cur,
		"company_total": company_total,
		"usd_total": usd_total,
		"yen_total": yen_total,
	}


@frappe.whitelist()
def reload_from_import_file(name):
	frappe.has_permission("Import File Cost Voucher", "write", throw=True)
	from vsd_jan_integration.vsd_jan_international_customization.doctype.import_file_cost_voucher.import_file_cost_voucher import (
		reload_from_import_file as _reload,
	)

	return _reload(name)
