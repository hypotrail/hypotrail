# Append-only example decision log

Preparation steps that remove rows or change value meaning cite `DECISION D-xxx`. D5 checks that each identifier exists here. These are synthetic fixture examples, not current human decisions or legal advice.

| id | date | layer | provenance | scope | decision | reason | rejected alternative | reversible |
|---|---|---|---|---|---|---|---|---|
| D-001 | 2026-10-09 | FRAMING | HUMAN | F1 | 36-month loans only | observable label within 36 months | include 60-month loans with immature labels | Y |
| D-002 | 2026-10-09 | FRAMING | HUMAN | F4 | 36-month backtest gap | defaults known only at maturity | no gap, exposing only early defaults | N |
| D-003 | 2026-10-09 | FRAMING | HUMAN | C1 | exclude zip_code, addr_state, emp_title | possible protected-attribute proxies | retain with a fairness assessment | Y |
| D-004 | 2026-10-11 | DATA | HUMAN | emp_length | map < 1 year to 0, N years to N, 10+ years to 10, n/a to missing | first-number parsing conflated < 1 and 1 year | categorical encoding | Y |
| D-005 | 2026-10-11 | DATA | HUMAN | F1 | exclude Does not meet the credit policy statuses | loans originated under another policy | retain with a policy indicator | Y |
| D-006 | 2026-10-11 | DATA | HUMAN | F1 | exclude joint applications | annual_inc and dti mean different things for joint applicants | use annual_inc_joint and dti_joint | Y |
| D-007 | 2026-10-11 | DATA | HUMAN | int_rate, grade, sub_grade | retain as features | known at origination; outputs from the Lending Club model | exclude for independence from pricing | Y |
