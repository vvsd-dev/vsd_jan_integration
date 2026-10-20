# Copyright (c) 2026, VV Systems Developer LTD and contributors
# For license information, please see license.txt

"""Report listing + runner for Jan UI (SLE / GL Entry reports + costing)."""

from __future__ import annotations

import json
import re

import frappe
from frappe import _
from frappe.utils import cint, nowdate, add_months, sbool


def _parse_js_filters(script: str) -> list[dict]:
	"""Best-effort extraction of filter defs from report JS (Desk parity without evaluating JS)."""
	if not script:
		return []
	# Find filters: [ ... ] at top level of query_reports assignment
	m = re.search(r"filters\s*:\s*\[", script)
	if not m:
		return []
	start = m.end() - 1  # at '['
	depth = 0
	i = start
	in_str = None
	escape = False
	while i < len(script):
		ch = script[i]
		if in_str:
			if escape:
				escape = False
			elif ch == "\\":
				escape = True
			elif ch == in_str:
				in_str = None
		else:
			if ch in ("'", '"', "`"):
				in_str = ch
			elif ch == "[":
				depth += 1
			elif ch == "]":
				depth -= 1
				if depth == 0:
					block = script[start : i + 1]
					return _filters_from_js_array(block)
		i += 1
	return []


def _filters_from_js_array(block: str) -> list[dict]:
	"""Parse filter objects from a JS array by locating fieldname entries."""
	filters = []
	seen = set()
	# Find each fieldname: "..." then take a window around it as the object body
	for m in re.finditer(r'fieldname\s*:\s*["\']([^"\']+)["\']', block):
		fieldname = m.group(1)
		if fieldname in seen:
			continue
		# Expand outward to nearest braces
		start = block.rfind("{", 0, m.start())
		if start < 0:
			continue
		depth = 0
		end = start
		in_str = None
		escape = False
		for i in range(start, len(block)):
			ch = block[i]
			if in_str:
				if escape:
					escape = False
				elif ch == "\\":
					escape = True
				elif ch == in_str:
					in_str = None
				continue
			if ch in ("'", '"', "`"):
				in_str = ch
			elif ch == "{":
				depth += 1
			elif ch == "}":
				depth -= 1
				if depth == 0:
					end = i
					break
		body = block[start : end + 1]
		fieldtype = _js_prop(body, "fieldtype") or "Data"
		label = _js_label(body) or fieldname.replace("_", " ").title()
		options = _js_prop(body, "options")
		default = _js_default(body, fieldtype)
		reqd = 1 if re.search(r"reqd\s*:\s*1\b", body) or re.search(r"reqd\s*:\s*true\b", body, re.I) else 0
		# MultiSelectList → Link in SPA (single value); Desk uses multi
		spa_type = "Link" if fieldtype == "MultiSelectList" else fieldtype
		seen.add(fieldname)
		filters.append(
			{
				"fieldname": fieldname,
				"label": label,
				"fieldtype": spa_type,
				"options": options or "",
				"default": default,
				"reqd": reqd,
				"original_fieldtype": fieldtype,
			}
		)
	return filters


def _js_prop(body: str, key: str) -> str | None:
	m = re.search(rf'{key}\s*:\s*["\']([^"\']+)["\']', body)
	if m:
		return m.group(1)
	# options: "Company" style without nested
	return None


def _js_label(body: str) -> str | None:
	m = re.search(r'label\s*:\s*__\(\s*["\']([^"\']+)["\']\s*\)', body)
	if m:
		return m.group(1)
	m = re.search(r'label\s*:\s*["\']([^"\']+)["\']', body)
	return m.group(1) if m else None


def _js_default(body: str, fieldtype: str):
	# default: frappe.defaults.get_user_default("Company")
	if re.search(r'get_user_default\s*\(\s*["\']Company["\']\s*\)', body):
		return frappe.defaults.get_user_default("Company") or ""
	# default: frappe.datetime.add_months(frappe.datetime.get_today(), -1)
	m = re.search(r"add_months\s*\(\s*frappe\.datetime\.get_today\s*\(\s*\)\s*,\s*(-?\d+)\s*\)", body)
	if m:
		return add_months(nowdate(), cint(m.group(1)))
	if fieldtype == "Date" and re.search(r"default\s*:.*get_today\s*\(\s*\)", body, re.DOTALL):
		return nowdate()
	m = re.search(r'default\s*:\s*["\']([^"\']*)["\']', body)
	if m:
		return m.group(1)
	m = re.search(r"default\s*:\s*(\d+(?:\.\d+)?)\b", body)
	if m:
		return m.group(1)
	return None


def _report_child_filters(report) -> list[dict]:
	out = []
	for f in report.get("filters") or []:
		out.append(
			{
				"fieldname": f.fieldname,
				"label": f.label or f.fieldname,
				"fieldtype": f.fieldtype or "Data",
				"options": f.options or "",
				"default": f.default,
				"reqd": cint(f.reqd),
			}
		)
	return out


@frappe.whitelist()
def list_reports(search=None, limit=100, start=0):
	"""List Report docs whose ref_doctype is Stock Ledger Entry or GL Entry."""
	frappe.has_permission("Report", "read", throw=True)
	limit = min(cint(limit) or 100, 200)
	start = cint(start) or 0
	search = (search or "").strip()

	filters = {
		"ref_doctype": ["in", ["Stock Ledger Entry", "GL Entry"]],
		"disabled": 0,
	}
	or_filters = None
	if search:
		or_filters = [
			["Report", "name", "like", f"%{search}%"],
			["Report", "report_name", "like", f"%{search}%"],
		]

	fields = ["name", "report_name", "ref_doctype", "report_type", "module", "is_standard", "prepared_report"]
	rows = frappe.get_list(
		"Report",
		filters=filters,
		or_filters=or_filters,
		fields=fields,
		limit_page_length=limit,
		limit_start=start,
		order_by="report_name asc",
	)
	total = frappe.db.count("Report", filters=filters)
	customs = [
		{
			"name": "Jan BL Costing",
			"report_name": "Jan BL Costing",
			"ref_doctype": "Car Costing",
			"report_type": "Script Report",
			"module": "VSD Jan International Customization",
			"is_standard": "No",
			"prepared_report": 0,
			"jan_custom": True,
			"route": "/reports/jan-bl-costing",
		},
		{
			"name": "Jan Sale Report",
			"report_name": "Jan Sale Report",
			"ref_doctype": "Sales Invoice",
			"report_type": "Script Report",
			"module": "VSD Jan International Customization",
			"is_standard": "No",
			"prepared_report": 0,
			"jan_custom": True,
			"route": "/reports/jan-sale-report",
		},
	]
	q = (search or "").lower()
	extra = []
	for custom in customs:
		label = custom["report_name"].lower()
		if not search or q in label or any(tok in label for tok in q.split() if tok):
			extra.append(custom)
	skip = {c["name"] for c in customs}
	rows = extra + [r for r in rows if r.get("name") not in skip]
	return {"reports": rows, "total": cint(total) + len(customs)}


@frappe.whitelist()
def get_report_meta(report_name):
	frappe.has_permission("Report", "read", throw=True)
	if report_name in ("Jan BL Costing", "jan-bl-costing"):
		from vsd_jan_integration.api.costing_report import get_columns, get_filters

		return {
			"name": "Jan BL Costing",
			"report_name": "Jan BL Costing",
			"report_type": "Script Report",
			"ref_doctype": "Car Costing",
			"jan_custom": True,
			"prepared_report": 0,
			"filters": get_filters(),
			"columns": get_columns(),
		}

	if report_name in ("Jan Sale Report", "jan-sale-report"):
		from vsd_jan_integration.api.sale_report import get_columns, get_filters

		return {
			"name": "Jan Sale Report",
			"report_name": "Jan Sale Report",
			"report_type": "Script Report",
			"ref_doctype": "Sales Invoice",
			"jan_custom": True,
			"prepared_report": 0,
			"filters": get_filters(),
			"columns": get_columns(),
		}

	if not frappe.db.exists("Report", report_name):
		frappe.throw(_("Report {0} not found").format(report_name), frappe.DoesNotExistError)

	report = frappe.get_doc("Report", report_name)
	if not frappe.has_permission("Report", "read", report):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	filters = _report_child_filters(report)
	script = ""
	try:
		from frappe.desk.query_report import get_script

		script_data = get_script(report_name)
		if isinstance(script_data, dict):
			script = script_data.get("script") or ""
			# Child table filters from get_script may already be present
			child = script_data.get("filters") or []
			if child and not filters:
				for f in child:
					if isinstance(f, dict):
						filters.append(f)
					else:
						filters.append(
							{
								"fieldname": getattr(f, "fieldname", None),
								"label": getattr(f, "label", None),
								"fieldtype": getattr(f, "fieldtype", "Data"),
								"options": getattr(f, "options", ""),
								"default": getattr(f, "default", None),
								"reqd": cint(getattr(f, "reqd", 0)),
							}
						)
	except Exception:
		frappe.log_error(title="Jan UI get_report_meta script")

	if not filters and script:
		filters = _parse_js_filters(script)

	# Resolve remaining JS defaults for company / dates if empty
	for f in filters:
		if f.get("default") in (None, "") and f.get("fieldname") == "company":
			f["default"] = frappe.defaults.get_user_default("Company") or ""
		if f.get("default") in (None, "") and f.get("fieldtype") == "Date":
			if f.get("fieldname") == "from_date":
				f["default"] = add_months(nowdate(), -1)
			elif f.get("fieldname") == "to_date":
				f["default"] = nowdate()

	return {
		"name": report.name,
		"report_name": report.report_name or report.name,
		"report_type": report.report_type,
		"ref_doctype": report.ref_doctype,
		"prepared_report": cint(report.prepared_report),
		"filters": filters,
		"columns": [],
		"json": report.json,
	}


@frappe.whitelist()
def run_report(report_name, filters=None, ignore_prepared_report=0, prepared_report_name=None):
	frappe.has_permission("Report", "read", throw=True)
	if isinstance(filters, str):
		filters = json.loads(filters) if filters else {}
	filters = dict(filters or {})

	if report_name in ("Jan BL Costing", "jan-bl-costing"):
		from vsd_jan_integration.api.costing_report import execute as costing_execute

		columns, data = costing_execute(filters)
		return {"columns": columns, "result": data, "message": None, "prepared_report": False}

	if report_name in ("Jan Sale Report", "jan-sale-report"):
		from vsd_jan_integration.api.sale_report import execute as sale_execute

		columns, data = sale_execute(filters)
		return {"columns": columns, "result": data, "message": None, "prepared_report": False}

	from frappe.desk.query_report import run

	if prepared_report_name:
		filters["prepared_report_name"] = prepared_report_name

	result = run(
		report_name,
		filters=filters,
		user=frappe.session.user,
		ignore_prepared_report=sbool(ignore_prepared_report),
		are_default_filters=False,
	)
	# Normalize prepared report doc for SPA
	out = {
		"columns": result.get("columns") or [],
		"result": result.get("result") or [],
		"message": result.get("message"),
		"prepared_report": bool(result.get("prepared_report")),
		"doc": None,
	}
	doc = result.get("doc")
	if doc:
		out["doc"] = {
			"name": doc.name,
			"status": doc.status,
			"report_end_time": str(doc.report_end_time) if doc.report_end_time else None,
			"creation": str(doc.creation) if doc.creation else None,
		}
	return out


@frappe.whitelist()
def generate_prepared_report(report_name, filters=None):
	"""Enqueue Prepared Report generation (Desk Generate)."""
	frappe.has_permission("Report", "read", throw=True)
	if isinstance(filters, str):
		filters = json.loads(filters) if filters else {}
	from frappe.core.doctype.prepared_report.prepared_report import make_prepared_report

	return make_prepared_report(report_name, filters=filters)


@frappe.whitelist()
def list_prepared_reports(report_name, filters=None, limit=20):
	"""Recent prepared reports for this user + report (Desk sidebar list)."""
	frappe.has_permission("Report", "read", throw=True)
	if isinstance(filters, str):
		filters = json.loads(filters) if filters else {}
	limit = min(cint(limit) or 20, 50)
	rows = frappe.get_list(
		"Prepared Report",
		filters={"report_name": report_name, "owner": frappe.session.user},
		fields=["name", "status", "creation", "report_end_time", "filters"],
		order_by="creation desc",
		limit_page_length=limit,
	)
	return {"prepared_reports": rows}
