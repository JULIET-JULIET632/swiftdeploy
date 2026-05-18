package swiftdeploy.canary

import rego.v1

default allow := false

allow if {
	error_rate_ok
	latency_ok
}

error_rate_ok if {
	input.error_rate <= data.canary.max_error_rate_pct
}

latency_ok if {
	input.p99_latency <= data.canary.max_p99_latency_ms
}

violations contains msg if {
	not error_rate_ok
	msg := sprintf(
		"Error rate (%.2f%%) exceeds maximum threshold (%.2f%%)",
		[input.error_rate, data.canary.max_error_rate_pct]
	)
}

violations contains msg if {
	not latency_ok
	msg := sprintf(
		"P99 latency (%.1fms) exceeds maximum threshold (%.1fms)",
		[input.p99_latency, data.canary.max_p99_latency_ms]
	)
}

reason := violations
