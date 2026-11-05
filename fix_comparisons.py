with open(r"C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL\tests\research\test_rdce_property_based.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix comparisons: result == FeasibilityStatus.XXX -> result.status == FeasibilityStatus.XXX
content = content.replace('assert result == FeasibilityStatus.SAT', 'assert result.status == FeasibilityStatus.SAT')
content = content.replace('assert result == FeasibilityStatus.UNSAT', 'assert result.status == FeasibilityStatus.UNSAT')
content = content.replace('assert result == FeasibilityStatus.UNKNOWN', 'assert result.status == FeasibilityStatus.UNKNOWN')

# Also fix the test_notipaddress_with_ipaddress which has two assertions
content = content.replace('assert result == FeasibilityStatus.SAT, f"Expected SAT for allow={allow_cidr} minus deny={deny_cidrs}"', 'assert result.status == FeasibilityStatus.SAT, f"Expected SAT for allow={allow_cidr} minus deny={deny_cidrs}"')
content = content.replace('assert result == FeasibilityStatus.UNSAT, f"Expected UNSAT for fully denied allow={allow_cidr} by deny={deny_cidrs}"', 'assert result.status == FeasibilityStatus.UNSAT, f"Expected UNSAT for fully denied allow={allow_cidr} by deny={deny_cidrs}"')

with open(r"C:\SNEHARSHA\ANTIGRAVITY\ARF-RT-TEMPORAL\tests\research\test_rdce_property_based.py", "w", encoding="utf-8") as f:
    f.write(content)
print("Fixed")