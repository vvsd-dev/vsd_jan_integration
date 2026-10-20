def run(chassis="KDH200-0045678"):
	from vsd_jan_integration.api.costing_report import execute

	columns, data = execute({"currency": "TZS", "chassis": chassis})
	row = data[0] if data else {}
	print(
		{
			"rows": len(data),
			"chassis": row.get("chassis"),
			"selling": row.get("selling"),
			"vat_18": row.get("vat_18"),
			"city_levy_tax": row.get("city_levy_tax"),
			"vat": row.get("vat"),
			"total_exp": row.get("total_exp"),
		}
	)
	assert row.get("selling") == 12500000
	assert abs(row.get("vat_18") - 12500000 * 0.18) < 1
	assert abs(row.get("city_levy_tax") - 37500) < 1
	assert abs(row.get("vat") - 450000) < 1
	# Total EXP includes city levy + vat cost (not vat_18)
	assert row.get("total_exp") >= 37500 + 450000
	print("REPORT_ROW_OK")
	return row
