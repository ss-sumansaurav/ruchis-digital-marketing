# Spend Approval Request {SAR-ID}

**Client / campaign / date:** {client} / {campaign} / {date}

**What you are approving:** {one sentence}

| | |
|---|---|
| Amount | {currency} {amount} |
| Channel | {channel} |
| Dates | {start} to {end} |
| Daily cap | {currency} {daily_cap} |

**Objective and KPI:** {objective}; primary KPI {kpi}, target {target}

**Expected outcome:** {low} to {high} {kpi unit} (base {base}). Source: {data source}. Assumptions: {assumptions}

**Budget position:** ceiling {ceiling} | already approved {approved} | spent to date {spent} | headroom after this request {headroom}

**Risks and kill criteria:** {risks}. The campaign is paused automatically if {kill criteria}

**Alternatives considered:** {alternatives}. The CEO recommends this one because {reason}

**Checks:** QA {pass/fail/not yet applicable} | Compliance {pass/fail/not yet applicable}

**Your options** (run in your own terminal; you will be asked for your approval key):

    APPROVE   python -m agency.cli --client {client} approve {SAR-ID}
    MODIFY    python -m agency.cli --client {client} approve {SAR-ID} --amount N --daily-cap N
    REJECT    python -m agency.cli --client {client} reject {SAR-ID} --note "reason"

Detail: {links to plan, forecast, QA report}
