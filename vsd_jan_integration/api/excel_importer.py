# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Excel Importer helpers for Jan UI (progress + enqueue)."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.utils import cint, sbool
from frappe.utils.file_manager import save_file


@frappe.whitelist()
def get_importer(name):
	frappe.has_permission("Item Excel Importer", "read", throw=True)
	doc = frappe.get_doc("Item Excel Importer", name)
	doc.check_permission("read")
	return doc.as_dict()


@frappe.whitelist()
def list_importers(search=None, limit=50, start=0):
	frappe.has_permission("Item Excel Importer", "read", throw=True)
	limit = min(cint(limit) or 50, 200)
	start = cint(start) or 0
	search = (search or "").strip()
	filters = []
	or_filters = None
	if search:
		or_filters = [
			["Item Excel Importer", "name", "like", f"%{search}%"],
			["Item Excel Importer", "import_status", "like", f"%{search}%"],
		]
	fields = [
		"name",
		"import_type",
		"import_status",
		"warehouse",
		"processed_invoices",
		"total_invoices",
		"processed_cars",
		"total_cars",
		"estimated_time",
		"modified",
	]
	meta = frappe.get_meta("Item Excel Importer")
	fields = [f for f in fields if f == "name" or f == "modified" or meta.has_field(f)]
	rows = frappe.get_list(
		"Item Excel Importer",
		fields=fields,
		filters=filters,
		or_filters=or_filters,
		limit_page_length=limit,
		limit_start=start,
		order_by="modified desc",
	)
	return {"importers": rows, "total": len(rows) + start}


@frappe.whitelist()
def save_importer(doc):
	frappe.has_permission("Item Excel Importer", "write", throw=True)
	if isinstance(doc, str):
		doc = json.loads(doc)
	name = doc.get("name")
	is_new = not name or not frappe.db.exists("Item Excel Importer", name)
	if is_new:
		frappe.has_permission("Item Excel Importer", "create", throw=True)
		d = frappe.new_doc("Item Excel Importer")
	else:
		d = frappe.get_doc("Item Excel Importer", name)

	for field in (
		"excel_file",
		"import_type",
		"import_file_number_format",
		"warehouse",
		"auto_submit_purchase_invoice",
		"auto_submit_journal_entry",
		"create_ifcv",
	):
		if field in doc and d.meta.has_field(field):
			d.set(field, doc.get(field))

	if is_new:
		d.insert()
	else:
		d.save()
	return d.as_dict()


@frappe.whitelist()
def start_import(docname, retry_failed_only=False):
	frappe.has_permission("Item Excel Importer", "write", throw=True)
	from vsd_jan_integration.vsd_jan_international_customization.doctype.item_excel_importer.item_excel_importer import (
		enqueue_import,
	)

	return enqueue_import(docname, retry_failed_only=sbool(retry_failed_only))


@frappe.whitelist()
def get_progress(docname):
	frappe.has_permission("Item Excel Importer", "read", throw=True)
	if not frappe.db.exists("Item Excel Importer", docname):
		frappe.throw(_("Importer {0} not found").format(docname))
	row = frappe.db.get_value(
		"Item Excel Importer",
		docname,
		[
			"name",
			"import_status",
			"import_type",
			"warehouse",
			"processed_invoices",
			"total_invoices",
			"processed_cars",
			"total_cars",
			"estimated_time",
			"import_log",
			"failed_records",
			"excel_file",
		],
		as_dict=True,
	)
	pi = cint(row.processed_invoices)
	ti = cint(row.total_invoices)
	pc = cint(row.processed_cars)
	tc = cint(row.total_cars)
	# Mirror Desk progress weighting: invoices + cars
	if ti or tc:
		done = pi + pc
		total = max(ti + tc, 1)
		percent = min(100, int(round(100.0 * done / total)))
	else:
		percent = 0 if row.import_status in ("Pending", "Queued") else (100 if "Completed" in (row.import_status or "") else 5)
	row["progress_percent"] = percent
	return row


@frappe.whitelist()
def upload_excel(docname, filename, filedata):
	"""Attach uploaded Excel to an importer doc (base64 filedata from SPA)."""
	frappe.has_permission("Item Excel Importer", "write", throw=True)
	doc = frappe.get_doc("Item Excel Importer", docname)
	doc.check_permission("write")
	if isinstance(filedata, str) and "," in filedata[:100]:
		# data URL
		filedata = filedata.split(",", 1)[1]
	f = save_file(filename, filedata, "Item Excel Importer", docname, decode=True, is_private=1)
	doc.excel_file = f.file_url
	doc.auto_detect_format()
	doc.save()
	return doc.as_dict()
