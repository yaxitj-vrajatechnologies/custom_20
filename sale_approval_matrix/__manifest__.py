# -*- coding: utf-8 -*-
{
    # App information
    'name': 'Sales Approval Matrix | Sales Margin & Quotation Approval',
    'category': 'Sales/Sales',
    'version': '20.0.1.0.0',
    'summary': """
            Complete revenue and margin based approval matrix that automatically evaluates every quotation against a configurable Green, Yellow and Red zone chart, so high-risk or low-margin deals are flagged before they reach the customer.
            Each quotation's zone is auto-computed from untaxed revenue and overall margin percentage, with a red Manager Review Required banner or a yellow Manager Approval Required banner shown directly on the quotation the moment it crosses your configured thresholds.
            Order lines are highlighted individually too, amber when a line's margin drops below 10% and red when a line is sold at a loss, so risk is visible at the line level, not just the order total.
            Clean state-driven approval workflow moving through Not Requested, Pending Approval, Approved, and Rejected, with dedicated Request Approval, Approve and Reject buttons restricted to the Sales Manager group.
            Send by Email and Confirm are automatically blocked on Yellow or Red quotations until a manager approves, closing the loophole where a rep pushes a risky deal through before anyone reviews it.
            Rejections capture a mandatory reason through a guided wizard, and every request, approval and rejection is logged in the chatter with an Activity assigned straight to the approving manager.
            Company-level Enable and Disable switch lets you turn the entire matrix on or off per company from Sales > Configuration > Settings, with quotations behaving exactly as if the module were not installed when disabled.            
            Revenue Margin Approval Matrix
            Sales Order Quotation Approval
            Sales Quotation Risk Zones
            Automated Sales Approval Rules
            Low Margin Deal Detection
            Sales Quotation Approval & Margin Control
            Margin Based Quotation Approval
            Sales Order Approval Governance
            Odoo Quotation Risk Management
            Configurable Approval Threshold Matrix
    """,
    'description': "",
    'license': 'OPL-1',

    # Dependencies
    'depends': ['sale_management', 'sale_margin', 'mail', 'sales_team'],

    # Views
    'data': [
        'security/ir.access.csv',
        'views/approval_matrix_views.xml',
        'views/reject_wizard_views.xml',
        'views/sale_order_views.xml',
        'views/res_config_settings_views.xml',
        'views/crm_team_views.xml',
    ],

    # Odoo Store Specific
    'images': ['static/description/cover.gif'],

    # Author
    "author": "Vraja Technologies",
    "website": "www.vrajatechnologies.com",
    "maintainer": "Vraja Technologies",
    "live_test_url": "https://www.vrajatechnologies.com/contactus",

    #hooks
    'post_init_hook': '_post_init_hook',

    # Technical
    "demo": [],
    "installable": True,
    "application": True,
    "auto_install": False,
    "price": '309',
    "currency": "EUR",
}
