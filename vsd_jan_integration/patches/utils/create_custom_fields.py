import json
import os

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

folder = "../custom_fields_json"

# Maps the "human label" export format to real Custom Field fieldnames.
# If a key isn't in here, normalize_entry() just passes it through as-is —
# so files already using real fieldnames (e.g. from export_custom_fields)
# work unchanged.
LABEL_TO_FIELDNAME = {
    "DocType": "dt",
    "Field Type": "fieldtype",
    "Label": "label",
    "Fieldname": "fieldname",
    "Insert After": "insert_after",
    "Options": "options",
    "Placeholder": "placeholder",
    "Length": "length",
    "Precision": "precision",
    "Default Value": "default",
    "Depends On": "depends_on",
    "Mandatory Depends On": "mandatory_depends_on",
    "Read Only Depends On": "read_only_depends_on",
    "Collapsible": "collapsible",
    "Collapsible Depends On": "collapsible_depends_on",
    "Is Mandatory Field": "reqd",
    "Read Only": "read_only",
    "Hidden": "hidden",
    "Unique": "unique",
    "Is Virtual": "is_virtual",
    "Print Hide": "print_hide",
    "Print Hide If No Value": "print_hide_if_no_value",
    "Print Width": "print_width",
    "No Copy": "no_copy",
    "Allow on Submit": "allow_on_submit",
    "In List View": "in_list_view",
    "In Standard Filter": "in_standard_filter",
    "In Global Search": "in_global_search",
    "In Preview": "in_preview",
    "Bold": "bold",
    "Report Hide": "report_hide",
    "Translatable": "translatable",
    "Non Negative": "non_negative",
    "Field Description": "description",
    "Permission Level": "permlevel",
    "Width": "width",
    "Columns": "columns",
    "Fetch From": "fetch_from",
    "Fetch on Save if Empty": "fetch_if_empty",
    "Module (for export)": "module",
}

# Fieldnames whose values should be coerced to int (checkbox/int-like columns)
INT_FIELDS = {
    "reqd", "read_only", "hidden", "unique", "is_virtual", "print_hide",
    "print_hide_if_no_value", "no_copy", "allow_on_submit", "in_list_view",
    "in_standard_filter", "in_global_search", "in_preview", "bold",
    "report_hide", "translatable", "non_negative", "collapsible",
    "permlevel", "columns", "fetch_if_empty", "length", "precision",
}


def normalize_entry(entry):
    """Translate a label-style exported row (e.g. 'DocType', 'Field Type')
    into real Custom Field fieldnames ('dt', 'fieldtype'). Keys that are
    already real fieldnames (not in the map) pass through unchanged, so
    files from export_custom_fields() work as-is."""
    normalized = {}
    for key, value in entry.items():
        fieldname = LABEL_TO_FIELDNAME.get(key, key)  # fallback: keep original key
        if fieldname in INT_FIELDS:
            try:
                value = int(value) if value not in ("", None) else 0
            except (ValueError, TypeError):
                pass
        normalized[fieldname] = value
    return normalized


def load_json(file):
    CURR_DIR = os.path.abspath(os.path.dirname(__file__))
    json_file_path = os.path.join(CURR_DIR, folder, file)
    # TODO do not load the file if already applied
    with open(json_file_path, "r") as file:
        data = json.load(file)
    return data


def create_fields_from_json(custom_fields_obj):
    disallowed_fields = [
        "name",
        "owner",
        "creation",
        "modified",
        "modified_by",
        "docstatus",
        "idx",
        "is_system_generated",
        "__last_sync_on",
    ]
    doctype_custom_fields_dict = {}

    for raw_field in custom_fields_obj:
        custom_field = normalize_entry(raw_field)

        if not custom_field.get("dt"):
            frappe.log_error(
                title="Skipping custom field with no dt",
                message=str(raw_field),
            )
            continue

        doctype = custom_field["dt"]
        all_fields = frappe.get_meta("Custom Field").get_valid_columns()
        field_list = set(all_fields).difference(disallowed_fields)
        custom_field_dict = {}
        for field_name in field_list:
            custom_field_dict[field_name] = custom_field.get(field_name)

        # Ensure the list for the doctype is initialized
        if doctype not in doctype_custom_fields_dict:
            doctype_custom_fields_dict[doctype] = []

        doctype_custom_fields_dict[doctype].append(custom_field_dict)

    create_custom_fields(doctype_custom_fields_dict, update=False)


def execute():
    # read names of only json files in this folder and put it into files list
    files = list(
        filter(
            lambda x: x.endswith(".json"),
            os.listdir(
                os.path.join(os.path.abspath(os.path.dirname(__file__)), folder)
            ),
        )
    )
    for file in files:
        data = load_json(file)
        create_fields_from_json(data)


@frappe.whitelist()
def export_custom_fields(docnames):
    docnames = frappe.parse_json(docnames)
    custom_fields = []

    for docname in docnames:
        doc = frappe.get_doc("Custom Field", docname)
        custom_fields.append(
            doc.as_dict(
                convert_dates_to_str=True, no_default_fields=True, no_nulls=True
            )
        )

    return str(custom_fields)