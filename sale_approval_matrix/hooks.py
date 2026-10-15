# -*- coding: utf-8 -*-


def _post_init_hook(env):
    """Seed the Approval Matrix with the Revenue x Margin chart supplied by the business.
    Revenue bands (rows):   Up to 1,200 | 1,200-2,000 | 2,000-5,000 | 5,000-10,000 |
                             10,000-15,000 | 15,000+
    Margin bands (columns): Under 10% | 10-12% | 12-15% | 15-17% | 17-20% | 20%+
    """
    Matrix = env['approval.matrix.line']

    if Matrix.search_count([]):
        # Already seeded (e.g. module updated, not freshly installed) - don't duplicate.
        return

    revenue_bands = [
        (0.0, 1199.99),
        (1200.0, 1999.99),
        (2000.0, 4999.99),
        (5000.0, 9999.99),
        (10000.0, 14999.99),
        (15000.0, 100000000.0),
    ]
    margin_bands = [
        (0, 9.99),
        (10.0, 11.99),
        (12.0, 14.99),
        (15.0, 16.99),
        (17.0, 19.99),
        (20.0, 100.0),
    ]

    # Rows = revenue bands (top to bottom as in the chart), columns = margin bands (left to right)
    grid = [
        ['red', 'yellow', 'yellow', 'green', 'green', 'green'],  # Up to 1,200
        ['red', 'yellow', 'yellow', 'green', 'green', 'green'],  # 1,200 - 2,000
        ['red', 'red', 'yellow', 'yellow', 'green', 'green'],  # 2,000 - 5,000
        ['red', 'red', 'yellow', 'yellow', 'yellow', 'green'],  # 5,000 - 10,000
        ['red', 'red', 'yellow', 'yellow', 'yellow', 'green'],  # 10,000 - 15,000
        ['red', 'red', 'yellow', 'yellow', 'yellow', 'yellow'],  # 15,000+
    ]

    vals_list = []
    sequence = 10
    for r_idx, (revenue_from, revenue_to) in enumerate(revenue_bands):
        for m_idx, (margin_from, margin_to) in enumerate(margin_bands):
            vals_list.append({
                'sequence': sequence,
                'revenue_from': revenue_from,
                'revenue_to': revenue_to,
                'margin_from': margin_from,
                'margin_to': margin_to,
                'zone': grid[r_idx][m_idx],
            })
            sequence += 10

    Matrix.create(vals_list)

    # IMPORTANT: Odoo computes stored fields like sale.order.approval_zone for all
    # existing records automatically when the field/column is first added - and
    # that happens BEFORE this hook runs, while the Approval Matrix above is still
    # empty at that point. Left alone, every pre-existing quotation would get stuck
    # with the fail-safe 'red' zone forever, regardless of its real margin. Force a
    # fresh recompute now that the matrix data actually exists, and flush it to the DB.
    orders = env['sale.order'].search([])
    if orders:
        orders._compute_total_margin_percent()
        orders._compute_approval_zone()
        orders.flush_recordset([
            'total_margin_percent', 'approval_zone',
            'show_manager_review_banner', 'show_yellow_review_banner',
        ])
        lines = orders.order_line
        if lines:
            lines._compute_line_risk_flag()
            lines.flush_recordset(['line_risk_flag'])
