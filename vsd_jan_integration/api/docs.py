# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Permission-aware DocType list/get/save helpers for Jan UI."""

from __future__ import annotations

import json

import frappe
from frappe import _
from frappe.desk.search import search_link
from frappe.model import no_value_fields
from frappe.utils import cint, sbool
JAN_DOCTYPES = {
	"Purchase Invoice": {
		"slug": "purchase-invoices",
		"title": "Purchase Invoices",
		"list_fields": ["name", "supplier", "bill_no", "posting_date", "grand_total", "currency", "status", "docstatus"],
		"search_fields": ["name", "supplier", "bill_no", "supplier_name"],
		"section": "Accounting",
	},
	"Sales Invoice": {
		"slug": "sales-invoices",
		"title": "Sales Invoices",
		"list_fields": ["name", "customer", "posting_date", "grand_total", "currency", "status", "docstatus"],
		"search_fields": ["name", "customer", "customer_name"],
		"section": "Accounting",
	},
	"Stock Entry": {
		"slug": "stock-entries",
		"title": "Stock Entries (Transfer)",
		"list_fields": ["name", "stock_entry_type", "posting_date", "from_warehouse", "to_warehouse", "docstatus"],
		"search_fields": ["name", "from_warehouse", "to_warehouse"],
		"default_filters": [["purpose", "=", "Material Transfer"]],
		"section": "Accounting",
	},
	"Journal Entry": {
		"slug": "journal-entries",
		"title": "Journal Entries",
		"list_fields": ["name", "voucher_type", "posting_date", "cheque_no", "total_debit", "docstatus", "user_remark"],
		"search_fields": ["name", "cheque_no", "user_remark"],
		"section": "Accounting",
	},
	"Account": {
		"slug": "accounts",
		"title": "Chart of Accounts",
		"list_fields": [
			"name",
			"account_name",
			"account_number",
			"parent_account",
			"is_group",
			"root_type",
			"account_type",
			"company",
			"account_currency",
		],
		"search_fields": ["name", "account_name", "account_number"],
		"section": "Accounting",
		"is_tree": True,
	},
	"Import File": {
		"slug": "import-files",
		"title": "Import Files",
		"list_fields": ["name", "bl_number", "supplier_invoice_no", "supplier_name", "docstatus", "modified"],
		"search_fields": ["name", "bl_number", "supplier_invoice_no", "supplier_name"],
		"section": "Costing",
	},
	"Import File Cost Voucher": {
		"slug": "ifcvs",
		"title": "Import File Cost Voucher",
		"list_fields": [
			"name",
			"import_file",
			"posting_date",
			"total_expense_amount",
			"total_allocated_amount",
			"docstatus",
		],
		"search_fields": ["name", "import_file"],
		"section": "Costing",
	},
	"Car Costing": {
		"slug": "car-costings",
		"title": "Car Costings",
		"list_fields": ["name", "item", "chassis_no", "costing_date", "total_cost_usd", "cost", "docstatus", "modified"],
		"search_fields": ["name", "item", "chassis_no"],
		"section": "Costing",
	},
	"Costing": {
		"slug": "costings",
		"title": "Costing",
		"list_fields": ["name", "costing_code", "costing_name", "region", "disabled", "modified"],
		"search_fields": ["name", "costing_code", "costing_name"],
		"section": "Costing",
	},
	"Costing Settings": {
		"slug": "costing-settings",
		"title": "Costing Settings",
		"list_fields": ["name", "modified"],
		"search_fields": ["name"],
		"section": "Costing",
		"is_single": True,
	},
	"Customer": {
		"slug": "customers",
		"title": "Customers",
		"list_fields": ["name", "customer_name", "customer_group", "territory", "disabled"],
		"search_fields": ["name", "customer_name"],
		"section": "Masters",
	},
	"Supplier": {
		"slug": "suppliers",
		"title": "Suppliers",
		"list_fields": ["name", "supplier_name", "supplier_group", "country", "disabled"],
		"search_fields": ["name", "supplier_name"],
		"section": "Masters",
	},
	"Address": {
		"slug": "addresses",
		"title": "Addresses",
		"list_fields": ["name", "address_title", "address_type", "city", "country", "disabled"],
		"search_fields": ["name", "address_title", "city"],
		"section": "Masters",
	},
	"Item Excel Importer": {
		"slug": "excel-importer",
		"title": "Excel Importer",
		"list_fields": [
			"name",
			"import_type",
			"import_status",
			"warehouse",
			"processed_invoices",
			"total_invoices",
			"processed_cars",
			"total_cars",
			"modified",
		],
		"search_fields": ["name", "import_type", "import_status"],
		"section": "Operations",
	},
}

SLUG_TO_DOCTYPE = {cfg["slug"]: dt for dt, cfg in JAN_DOCTYPES.items()}

PAGE_SIZE_OPTIONS = (20, 100, 500, 2500)
MAX_PAGE_SIZE = 2500


def _resolve_doctype(doctype=None, slug=None):
	if doctype:
		if doctype not in JAN_DOCTYPES:
			frappe.throw(_("DocType {0} is not available in Jan UI").format(doctype), frappe.PermissionError)
		return doctype
	if slug:
		dt = SLUG_TO_DOCTYPE.get(slug)
		if not dt:
			frappe.throw(_("Unknown Jan UI section: {0}").format(slug), frappe.DoesNotExistError)
		return dt
	frappe.throw(_("doctype or slug is required"))


def _existing_fields(doctype, fields):
	meta = frappe.get_meta(doctype)
	out = []
	for f in fields:
		if f in ("name", "docstatus", "owner", "creation", "modified", "modified_by"):
			out.append(f)
		elif meta.has_field(f):
			out.append(f)
	if "name" not in out:
		out.insert(0, "name")
	return out


def _serialize_doc(doc):
	data = doc.as_dict(no_nulls=False)
	for key, value in list(data.items()):
		if isinstance(value, list):
			data[key] = [dict(r) if hasattr(r, "items") else r for r in value]
	return data


def _form_fields(meta):
	"""Flatten value + table fields for SPA forms (skip layout-only)."""
	fields = []
	for df in meta.fields:
		if df.fieldtype in ("Section Break", "Column Break", "Tab Break", "Fold"):
			# Keep section/column markers so SPA can approximate Desk layout in dialogs
			fields.append(
				{
					"fieldname": df.fieldname,
					"label": df.label or df.fieldname,
					"fieldtype": df.fieldtype,
					"options": df.options,
					"reqd": 0,
					"read_only": 0,
					"hidden": cint(df.hidden),
					"in_list_view": 0,
					"in_standard_filter": 0,
					"allow_on_submit": 0,
					"depends_on": df.depends_on,
					"default": df.default,
					"description": df.description,
					"permlevel": cint(df.permlevel),
					"is_layout": 1,
				}
			)
			continue
		if df.fieldtype in no_value_fields and df.fieldtype not in ("Table", "Table MultiSelect"):
			if df.fieldtype not in ("Attach", "Attach Image", "HTML", "Button", "Heading"):
				continue
		fields.append(
			{
				"fieldname": df.fieldname,
				"label": df.label or df.fieldname,
				"fieldtype": df.fieldtype,
				"options": df.options,
				"reqd": cint(df.reqd),
				"read_only": cint(df.read_only),
				"hidden": cint(df.hidden),
				"in_list_view": cint(df.in_list_view),
				"in_standard_filter": cint(getattr(df, "in_standard_filter", 0)),
				"allow_on_submit": cint(getattr(df, "allow_on_submit", 0)),
				"depends_on": df.depends_on,
				"default": df.default,
				"description": df.description,
				"permlevel": cint(df.permlevel),
				"is_layout": 0,
			}
		)
	return fields


def _list_fields_for(doctype, cfg):
	"""Prefer List View Settings columns, then in_list_view, then cfg defaults."""
	meta = frappe.get_meta(doctype)
	fields = []

	# List View Settings.fields is a JSON string of [{fieldname:...}, ...]
	try:
		lvs = frappe.get_cached_doc("List View Settings", doctype)
		raw = lvs.get("fields")
		if raw:
			parsed = json.loads(raw) if isinstance(raw, str) else raw
			for item in parsed or []:
				fn = item.get("fieldname") if isinstance(item, dict) else None
				if fn and (fn in ("name", "docstatus", "status") or meta.has_field(fn)):
					if fn not in fields:
						fields.append(fn)
	except frappe.DoesNotExistError:
		frappe.clear_messages()
	except Exception:
		pass

	if not fields:
		for df in meta.fields:
			if cint(df.in_list_view) and df.fieldname not in fields:
				fields.append(df.fieldname)

	if not fields:
		fields = list(cfg.get("list_fields") or ["name"])

	# Always include name first
	if "name" in fields:
		fields = ["name"] + [f for f in fields if f != "name"]
	else:
		fields.insert(0, "name")

	# Keep docstatus for submittable
	if cint(meta.is_submittable) and "docstatus" not in fields:
		fields.append("docstatus")

	return _existing_fields(doctype, fields)


def _standard_filters(meta):
	"""Top / standard list filters — same selection Desk uses (in_standard_filter + title)."""
	title_field = meta.get("title_field")
	out = []
	seen = set()
	for df in meta.fields:
		if cint(df.hidden):
			continue
		use = cint(getattr(df, "in_standard_filter", 0)) or (title_field and df.fieldname == title_field)
		if not use:
			continue
		if df.fieldname in seen:
			continue
		seen.add(df.fieldname)
		condition = "="
		fieldtype = df.fieldtype
		if fieldtype in (
			"Text",
			"Small Text",
			"Text Editor",
			"HTML Editor",
			"Data",
			"Code",
			"Phone",
			"JSON",
			"Read Only",
		):
			fieldtype = "Data"
			condition = "like"
		out.append(
			{
				"fieldname": df.fieldname,
				"label": df.label or df.fieldname,
				"fieldtype": fieldtype,
				"options": df.options,
				"condition": condition,
			}
		)
	return out


@frappe.whitelist()
def list_jan_sections():
	"""Sidebar catalog filtered by current user permissions."""
	sections = []
	for doctype, cfg in JAN_DOCTYPES.items():
		if not frappe.has_permission(doctype, "read"):
			continue
		# Skip singles that aren't listable usefully except via form
		sections.append(
			{
				"doctype": doctype,
				"slug": cfg["slug"],
				"title": cfg["title"],
				"section": cfg.get("section") or "Other",
				"is_tree": bool(cfg.get("is_tree")),
				"is_single": bool(cfg.get("is_single")),
				"can_create": bool(frappe.has_permission(doctype, "create")),
				"can_write": bool(frappe.has_permission(doctype, "write")),
			}
		)
	return {"sections": sections}


@frappe.whitelist()
def get_meta(doctype=None, slug=None):
	doctype = _resolve_doctype(doctype, slug)
	frappe.has_permission(doctype, "read", throw=True)
	meta = frappe.get_meta(doctype)
	cfg = JAN_DOCTYPES[doctype]
	child_metas = {}
	for df in meta.fields:
		if df.fieldtype == "Table" and df.options:
			child = frappe.get_meta(df.options)
			child_metas[df.fieldname] = {
				"doctype": df.options,
				"fields": _form_fields(child),
				"title_field": child.get("title_field"),
			}
	list_fields = _list_fields_for(doctype, cfg)
	return {
		"doctype": doctype,
		"slug": cfg["slug"],
		"title": cfg["title"],
		"is_submittable": cint(meta.is_submittable),
		"is_tree": bool(cfg.get("is_tree") or meta.is_tree),
		"is_single": bool(cfg.get("is_single") or meta.issingle),
		"title_field": meta.get("title_field"),
		"nsm_parent_field": meta.get("nsm_parent_field"),
		"fields": _form_fields(meta),
		"list_fields": list_fields,
		"standard_filters": _standard_filters(meta),
		"page_size_options": list(PAGE_SIZE_OPTIONS),
		"child_tables": child_metas,
		"section": cfg.get("section") or "Other",
		"permissions": {
			"read": bool(frappe.has_permission(doctype, "read")),
			"write": bool(frappe.has_permission(doctype, "write")),
			"create": bool(frappe.has_permission(doctype, "create")),
			"delete": bool(frappe.has_permission(doctype, "delete")),
			"submit": bool(frappe.has_permission(doctype, "submit")),
			"cancel": bool(frappe.has_permission(doctype, "cancel")),
			"amend": bool(frappe.has_permission(doctype, "amend")),
		},
	}


@frappe.whitelist()
def list_docs(
	doctype=None,
	slug=None,
	search=None,
	filters=None,
	limit=20,
	start=0,
	order_by="modified desc",
	order_field=None,
	order_dir=None,
):
	doctype = _resolve_doctype(doctype, slug)
	frappe.has_permission(doctype, "read", throw=True)
	cfg = JAN_DOCTYPES[doctype]
	meta = frappe.get_meta(doctype)

	if cfg.get("is_single") or meta.issingle:
		# Singles: return the one document name
		name = doctype
		if frappe.db.exists(doctype, name):
			row = frappe.get_doc(doctype, name).as_dict()
			fields = _list_fields_for(doctype, cfg)
			return {
				"doctype": doctype,
				"rows": [{f: row.get(f) for f in fields}],
				"total": 1,
				"fields": fields,
				"page_size_options": list(PAGE_SIZE_OPTIONS),
			}
		return {"doctype": doctype, "rows": [], "total": 0, "fields": [], "page_size_options": list(PAGE_SIZE_OPTIONS)}

	limit = cint(limit) or 20
	if limit not in PAGE_SIZE_OPTIONS and limit != -1:
		# allow any positive up to max, prefer known sizes
		limit = min(max(limit, 1), MAX_PAGE_SIZE)
	elif limit == -1:
		# load-more sentinel handled by client with a page size; treat as 100
		limit = 100
	else:
		limit = min(limit, MAX_PAGE_SIZE)
	start = cint(start) or 0

	if isinstance(filters, str):
		filters = json.loads(filters) if filters else []
	filters = list(filters or [])
	for f in cfg.get("default_filters") or []:
		filters.append(f)

	fields = _list_fields_for(doctype, cfg)
	# Ensure sort field is selected
	if order_field and order_field not in fields and (order_field in ("name", "modified", "creation") or meta.has_field(order_field)):
		fields.append(order_field)

	or_filters = []
	search = (search or "").strip()
	if search:
		for sf in cfg.get("search_fields") or ["name"]:
			if sf == "name" or meta.has_field(sf):
				or_filters.append([doctype, sf, "like", f"%{search}%"])

	if order_field:
		direction = "desc" if str(order_dir or "").lower() == "desc" else "asc"
		safe = order_field if order_field in ("name", "modified", "creation", "docstatus") or meta.has_field(order_field) else "modified"
		order_by = f"`tab{doctype}`.`{safe}` {direction}"

	rows = frappe.get_list(
		doctype,
		fields=fields,
		filters=filters,
		or_filters=or_filters or None,
		limit_page_length=limit,
		limit_start=start,
		order_by=order_by,
	)
	total = start + len(rows)
	try:
		total = frappe.db.count(doctype, filters=filters) if not or_filters else None
		if total is None:
			all_names = frappe.get_list(
				doctype,
				fields=["name"],
				filters=filters,
				or_filters=or_filters or None,
				limit_page_length=100000,
				limit_start=0,
			)
			total = len(all_names)
		# When search or_filters present, count via get_list length above
		if or_filters:
			all_names = frappe.get_list(
				doctype,
				fields=["name"],
				filters=filters,
				or_filters=or_filters,
				limit_page_length=100000,
				limit_start=0,
			)
			total = len(all_names)
	except Exception:
		pass

	return {
		"doctype": doctype,
		"rows": rows,
		"total": cint(total),
		"fields": fields,
		"page_size_options": list(PAGE_SIZE_OPTIONS),
		"start": start,
		"limit": limit,
	}


@frappe.whitelist()
def get_doc(doctype=None, slug=None, name=None):
	doctype = _resolve_doctype(doctype, slug)
	cfg = JAN_DOCTYPES[doctype]
	meta = frappe.get_meta(doctype)
	if cfg.get("is_single") or meta.issingle:
		name = doctype
	if not name:
		frappe.throw(_("name is required"))
	frappe.has_permission(doctype, "read", throw=True)
	if not frappe.db.exists(doctype, name):
		frappe.throw(_("{0} {1} not found").format(doctype, name), frappe.DoesNotExistError)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("read")
	return _serialize_doc(doc)


@frappe.whitelist()
def save_doc(doctype=None, slug=None, doc=None):
	doctype = _resolve_doctype(doctype, slug)
	if isinstance(doc, str):
		doc = json.loads(doc)
	if not isinstance(doc, dict):
		frappe.throw(_("doc must be an object"))

	meta = frappe.get_meta(doctype)
	cfg = JAN_DOCTYPES[doctype]
	name = doc.get("name")
	if cfg.get("is_single") or meta.issingle:
		name = doctype
		doc["name"] = doctype
		is_new = not frappe.db.exists(doctype, name)
	else:
		is_new = not name or str(name).startswith("new-") or not frappe.db.exists(doctype, name)

	if is_new:
		frappe.has_permission(doctype, "create", throw=True)
		d = frappe.new_doc(doctype)
	else:
		frappe.has_permission(doctype, "write", throw=True)
		d = frappe.get_doc(doctype, name)
		d.check_permission("write")

	submitted = cint(d.docstatus) == 1

	for df in meta.fields:
		fn = df.fieldname
		if fn not in doc:
			continue
		# After submit: only allow_on_submit fields (and child tables marked allow_on_submit)
		if submitted and not cint(getattr(df, "allow_on_submit", 0)):
			continue
		if df.fieldtype == "Table":
			d.set(fn, [])
			for row in doc.get(fn) or []:
				if isinstance(row, dict):
					# Keep row name for updates when present
					d.append(fn, row)
		elif df.fieldtype not in ("Section Break", "Column Break", "Tab Break", "Fold", "HTML", "Button", "Heading"):
			d.set(fn, doc.get(fn))

	for sys_f in ("naming_series", "company", "posting_date", "purpose", "stock_entry_type"):
		if submitted:
			break
		if sys_f in doc and meta.has_field(sys_f):
			d.set(sys_f, doc.get(sys_f))

	if is_new:
		d.insert()
	else:
		# Frappe sets update_after_submit automatically when docstatus==1
		d.save()
	return _serialize_doc(d)


@frappe.whitelist()
def submit_doc(doctype=None, slug=None, name=None):
	doctype = _resolve_doctype(doctype, slug)
	frappe.has_permission(doctype, "submit", throw=True)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("submit")
	doc.submit()
	return _serialize_doc(doc)


@frappe.whitelist()
def cancel_doc(doctype=None, slug=None, name=None):
	doctype = _resolve_doctype(doctype, slug)
	frappe.has_permission(doctype, "cancel", throw=True)
	doc = frappe.get_doc(doctype, name)
	doc.check_permission("cancel")
	doc.cancel()
	return _serialize_doc(doc)


@frappe.whitelist()
def amend_doc(doctype=None, slug=None, name=None):
	"""Create amended draft from cancelled/submitted doc (ERPNext amend pattern)."""
	doctype = _resolve_doctype(doctype, slug)
	frappe.has_permission(doctype, "amend", throw=True)
	source = frappe.get_doc(doctype, name)
	source.check_permission("read")
	if cint(source.docstatus) != 2:
		frappe.throw(_("Only cancelled documents can be amended"))
	amended = frappe.copy_doc(source)
	amended.amended_from = source.name
	amended.insert()
	return _serialize_doc(amended)


@frappe.whitelist()
def delete_doc(doctype=None, slug=None, name=None):
	doctype = _resolve_doctype(doctype, slug)
	frappe.has_permission(doctype, "delete", throw=True)
	frappe.delete_doc(doctype, name)
	return {"ok": True}


@frappe.whitelist()
def link_search(doctype, txt="", filters=None, page_length=20, reference_doctype=None, ignore_user_permissions=0):
	"""Permission-aware Link search — wraps Desk search_link."""
	frappe.has_permission(doctype, "read", throw=True)
	if isinstance(filters, str):
		filters = json.loads(filters) if filters else None
	page_length = min(cint(page_length) or 20, 50)
	results = search_link(
		doctype=doctype,
		txt=txt or "",
		query=None,
		filters=filters,
		page_length=page_length,
		reference_doctype=reference_doctype or "",
		ignore_user_permissions=cint(ignore_user_permissions),
	)
	if results is None:
		results = frappe.response.get("message") or []
	return results or []


# ---- Account tree (Chart of Accounts) ----


@frappe.whitelist()
def list_companies():
	frappe.has_permission("Company", "read", throw=True)
	rows = frappe.get_list("Company", fields=["name"], order_by="name asc", limit_page_length=200)
	default = frappe.defaults.get_user_default("Company") or (rows[0]["name"] if rows else "")
	return {"companies": [r["name"] for r in rows], "default": default}


@frappe.whitelist()
def get_account_children(company, parent=None, is_root=0):
	"""Tree nodes for Chart of Accounts — wraps erpnext.accounts.utils.get_children."""
	frappe.has_permission("Account", "read", throw=True)
	if not company:
		frappe.throw(_("Company is required"))
	from erpnext.accounts.utils import get_children

	is_root = sbool(is_root) or not parent or parent in ("", "Accounts", company)
	nodes = get_children("Account", parent or "", company, is_root=is_root)
	# Attach title for display
	for n in nodes:
		n["title"] = n.get("value")
	return {"nodes": nodes, "company": company, "parent": parent or ""}


@frappe.whitelist()
def add_account(company, parent_account, account_name, account_number=None, is_group=0, account_type=None, root_type=None, account_currency=None):
	frappe.has_permission("Account", "create", throw=True)
	from erpnext.accounts.utils import add_ac

	args = {
		"doctype": "Account",
		"company": company,
		"parent": parent_account,
		"parent_account": parent_account,
		"account_name": account_name,
		"account_number": account_number or "",
		"is_group": cint(is_group),
		"is_root": "false",
	}
	if account_type:
		args["account_type"] = account_type
	if root_type:
		args["root_type"] = root_type
	if account_currency:
		args["account_currency"] = account_currency
	name = add_ac(args)
	return {"name": name}


@frappe.whitelist()
def rebuild_account_tree(company=None):
	"""Rebuild nested set for Account tree (Desk Rebuild Tree)."""
	frappe.has_permission("Account", "write", throw=True)
	from frappe.utils.nestedset import rebuild_tree

	rebuild_tree("Account", "parent_account")
	return {"ok": True, "company": company}
