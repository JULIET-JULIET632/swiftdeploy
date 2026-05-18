package swiftdeploy.infrastructure

import rego.v1

default allow := false

allow if {
	disk_ok
	cpu_ok
}

disk_ok if {
	input.disk_free_gb >= data.infrastructure.min_disk_free_gb
}

cpu_ok if {
	input.cpu_load <= data.infrastructure.max_cpu_load
}

violations contains msg if {
	not disk_ok
	msg := sprintf(
		"Disk free (%.1fGB) is below minimum threshold (%.1fGB)",
		[input.disk_free_gb, data.infrastructure.min_disk_free_gb]
	)
}

violations contains msg if {
	not cpu_ok
	msg := sprintf(
		"CPU load (%.2f) exceeds maximum threshold (%.2f)",
		[input.cpu_load, data.infrastructure.max_cpu_load]
	)
}

reason := violations
