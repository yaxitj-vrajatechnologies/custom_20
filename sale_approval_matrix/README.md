# Sales Approval Matrix — Custom Odoo Module

Implements the Revenue x Margin approval chart, warning banners, line-level
risk highlighting, and a manager approval workflow for Quotations.

## Dependencies

This module depends on Odoo's own `sale_management`, `sale_margin`, and
`mail` modules. **`sale_margin` must be installed** — it is what provides
the `margin` / `margin_percent` fields on quotations and their lines that
this module reads from. It will auto-install as a dependency, but make
sure your product costs (cost price / vendor price / BOM cost) are set up
correctly, otherwise margin will always compute as 0.

## Installation

1. Copy the `sale_approval_matrix` folder into your Odoo `addons` path
   (or a custom addons directory already referenced in your Odoo config).
2. Restart the Odoo service.
3. Go to **Apps**, remove the "Apps" filter, search for
   **"Sales Approval Matrix"**, and click **Install**.
4. On install, the module automatically seeds the approval matrix with
   the exact chart you supplied (6 revenue bands x 6 margin bands = 36
   cells -> Green/Yellow/Red). You can review/edit it any time at
   **Sales → Configuration → Approval Matrix**.

## What it does

- **Approval Matrix (Sales → Configuration → Approval Matrix)**
  Editable table of Revenue-from/to and Margin%-from/to bands, each
  mapped to Green, Yellow, or Red. Fully reconfigurable without code.

- **On every Quotation**, two fields are computed live from the order
  lines: `Overall Margin %` and `Approval Zone` (looked up against the
  matrix above). Both the revenue and margin used for this lookup are
  based on the **untaxed** total (`amount_untaxed`), not the tax-inclusive
  total — tax is a pass-through, not revenue, and `sale_margin`'s own
  line-level margin is also computed pre-tax, so this keeps both sides
  of the comparison consistent.

- **Two banners on the quotation form**, both driven directly by
  `Approval Zone` (not a separate hardcoded threshold — the zone lookup
  already correctly reflects your chart's revenue-dependent bands, e.g.
  10-12% margin is Red above $2,000 revenue but Yellow below it):
  - **Red** "Manager Review Required" — shown when the zone is Red.
  - **Yellow** "Manager Approval Required" — shown when the zone is
    Yellow. Only one banner shows at a time.

- **Line highlighting**: each order line is shaded amber if its margin
  is below 10%, and red if its profit is negative.

- **Approval workflow** (buttons in the header):
  - *Request Approval* — shown to the salesperson when the quotation is
    Yellow or Red. Notifies the specific users configured as this quotation's
    Sales Team's "Approval Managers" (Sales Teams → open a team → Approval
    Managers field), creating an Activity + chatter notification for each of
    them. If the team has no Approval Managers configured, or the quotation
    has no Sales Team assigned, it falls back to notifying everyone in the
    Sales Manager group, so a request never goes unnoticed.
  - *Approve* / *Reject* — visible only to users in the Sales Manager
    group, while the quotation is Pending. Reject opens a small wizard
    asking for a reason, which is stored and logged in the chatter.
  - When a manager **approves**, the salesperson gets a plain chatter/inbox
    notification (no task attached - nothing further for them to do).
  - When a manager **rejects**, the salesperson gets the same kind of
    notification plus an Activity (to-do) reminding them to revise the
    quote and request approval again.
  - A status bar (Not Requested → Pending Approval → Approved/Rejected)
    is shown in the header.

- **Guard rails**: "Send by Email" and "Confirm" are blocked (with a
  clear error message) on any Yellow/Red quotation that has not been
  Approved yet. Green quotations are unaffected and flow normally.

- **Approval Matrix tab** on the quotation form shows the computed zone,
  margin %, approval status, who approved/rejected it, when, and any
  rejection reason.

## Testing checklist before go-live

- [ ] Confirm boundary values (exactly $1,200 revenue, exactly 10%
      margin, etc.) fall into the band you expect — adjust the matrix
      rows if you want different boundary inclusivity.
- [ ] Confirm the Red banner appears for every Red cell, and the Yellow
      banner for every Yellow cell — not just margin-below-10% cases.
- [ ] Confirm a Green quotation can be sent/confirmed with no approval
      step.
- [ ] Confirm a Yellow/Red quotation blocks Send/Confirm until Approved.
- [ ] Confirm a non-manager user cannot see/use Approve/Reject buttons,
      and gets blocked even via direct method call.
- [ ] Confirm the manager receives an Activity and chatter entry on
      Request Approval, and that it's marked done on Approve/Reject.
- [ ] Confirm order lines with negative profit show red, and lines
      under 10% margin show amber.
- [ ] Re-test after adjusting product costs, since margin depends on
      `sale_margin`'s cost data being accurate.
- [ ] Confirm revenue/margin calculations use the untaxed total — test
      with a customer/fiscal position that has a non-zero tax rate and
      verify the zone doesn't shift based on tax amount.
