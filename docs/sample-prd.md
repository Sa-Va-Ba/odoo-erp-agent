# Odoo Implementation PRD — BelgiumParts NV

## Executive Summary

- **Company:** BelgiumParts NV
- **Industry:** Manufacturing
- **Modules:** 9
- **Estimated Setup Time:** 64 minutes
- **Completeness Score:** 100%

## Company Configuration

| Setting | Value |
|---------|-------|
| Country | US |
| Currency | EUR |
| Fiscal Year Start | Month 1 |
| Timezone | UTC |
| Tax Regime | standard |

## Module Installation Plan

| # | Module | Display Name | Priority | Dependencies | Est. Minutes |
|---|--------|-------------|----------|-------------|-------------|
| 1 | `sale_management` | Sales | high | — | 5 |
| 2 | `stock` | Inventory | high | — | 8 |
| 3 | `account` | Invoicing/Accounting | critical | — | 10 |
| 4 | `purchase` | Purchase | medium | stock | 5 |
| 5 | `mrp` | Manufacturing | medium | stock | 10 |
| 6 | `hr` | Employees | medium | — | 5 |
| 7 | `hr_attendance` | Attendance | low | hr | 3 |
| 8 | `hr_holidays` | Time Off | low | hr | 3 |
| 9 | `crm` | CRM | high | sale_management | 5 |

## Detailed Module Configuration

### Sales (`sale_management`)

**Purpose:** Detected from sales domain interview

**Settings:**

```
  group_sale_pricelist: False
  group_discount_per_so_line: False
```

### Inventory (`stock`)

**Purpose:** Detected from inventory domain interview

**Settings:**

```
  group_stock_multi_locations: True
  group_stock_tracking_lot: True
```

### Invoicing/Accounting (`account`)

**Purpose:** Detected from finance domain interview

**Settings:**

```
  group_analytic_accounting: False
```

### Purchase (`purchase`)

**Purpose:** Detected from purchase domain interview

Default configuration — no custom settings required.

### Manufacturing (`mrp`)

**Purpose:** Detected from manufacturing domain interview

Default configuration — no custom settings required.

### Employees (`hr`)

**Purpose:** Detected from hr domain interview

Default configuration — no custom settings required.

### Attendance (`hr_attendance`)

**Purpose:** Recommended based on interview analysis

Default configuration — no custom settings required.

### Time Off (`hr_holidays`)

**Purpose:** Recommended based on interview analysis

Default configuration — no custom settings required.

### CRM (`crm`)

**Purpose:** Recommended based on interview analysis

**Settings:**

```
  group_use_lead: True
```

## User Roles & Security

| Role | Description | Security Groups | Users |
|------|------------|----------------|-------|
| Administrator | Full system access | `base.group_system` | 1 |
| Sales User | Sales team member with CRM and quotation access | `sale.group_sale_salesman`, `base.group_user` | 1 |
| Warehouse User | Warehouse staff with stock and picking access | `stock.group_stock_user`, `base.group_user` | 1 |
| Accountant | Accounting and invoicing access | `account.group_account_user`, `base.group_user` | 1 |
| Manager | Department manager with approval rights | `base.group_user` | 1 |

## Data Migration Plan

| Data Type | Source | Est. Records | Priority |
|-----------|--------|-------------|----------|
| customers | csv | — | medium |
| products | csv | — | medium |
| vendors | csv | — | medium |
| invoices | csv | — | medium |
| employees | csv | — | medium |
| stock_levels | csv | — | medium |

## Integration Requirements

| System | Direction | Type | Priority | Notes |
|--------|-----------|------|----------|-------|
| Excel/CSV | bidirectional | file | medium | Mentioned during scoping: Our main pain points are: inventory tracking across tw |
| Spreadsheets | import | file | medium | Mentioned during scoping: Our main pain points are: inventory tracking across tw |
| DHL | bidirectional | api | medium | Mentioned during scoping: A customer sends an RFQ, our sales team creates a quot |
| Banking | import | file | medium | Mentioned during scoping: Standard 30-day payment terms. We accept bank transfer |

## Pain Points

- Our main pain points are: inventory tracking across two warehouses is done in Excel, production scheduling is manual, purchase orders are emailed manually to suppliers, and our accounting team spends 2 days per month reconciling spreadsheets. We also have no CRM — leads are tracked in a shared inbox.
- We use a basic CRM spreadsheet for leads. Win rate is around 35%. Average deal size is €18,000.
- Two warehouses (Ghent and Antwerp). Tracked in Excel. Monthly manual counts. FIFO costing. Raw material lead time is 2-5 weeks from European suppliers.
- We invoice on delivery. About 300 invoices per month. Bank reconciliation is very manual.

## Implementation Checklist

- [ ] Create Odoo instance and configure company details
- [ ] Install and configure **Sales** (`sale_management`)
- [ ] Install and configure **Inventory** (`stock`)
- [ ] Install and configure **Invoicing/Accounting** (`account`)
- [ ] Install and configure **Purchase** (`purchase`)
- [ ] Install and configure **Manufacturing** (`mrp`)
- [ ] Install and configure **Employees** (`hr`)
- [ ] Install and configure **Attendance** (`hr_attendance`)
- [ ] Install and configure **Time Off** (`hr_holidays`)
- [ ] Install and configure **CRM** (`crm`)
- [ ] Create user roles and assign security groups
- [ ] Execute data migration plan
- [ ] Set up external integrations
- [ ] User acceptance testing
- [ ] Go-live
