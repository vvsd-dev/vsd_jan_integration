// Copyright (c) 2026, VV Systems Developer LTD and contributors
frappe.query_reports["Jan BL Costing"] = {
	filters: [
		{
			fieldname: "currency",
			label: __("Currency"),
			fieldtype: "Select",
			options: "TZS\nYEN\nUSD",
			default: "TZS",
			reqd: 1,
		},
		{
			fieldname: "import_file",
			label: __("Import File"),
			fieldtype: "Link",
			options: "Import File",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "chassis",
			label: __("Chassis"),
			fieldtype: "Data",
		},
	],
};
