# -*- coding: utf-8 -*-
import logging

_logger = logging.getLogger(__name__)

# (rule action xml_id in this module, description,
#  candidate core report xml_ids, fallback search (model, report_name fragment))
DEFAULT_RULES = [
    ("print_document_on_transfer", "Print Delivery Slip After Validation",
     ["stock.action_report_delivery"], ("stock.picking", "delivery")),
    ("print_document_on_transfer", "Print Delivery Slip for all outgoing transfers (after validation)",
     ["stock.action_report_delivery"], ("stock.picking", "delivery")),
    ("print_backorder_document",
     "Print Delivery Slip after Delivery Order Confirmation for backorder (created after Transfer validation)",
     ["stock.action_report_delivery"], ("stock.picking", "delivery")),
    ("print_sales_order_document", "Print document on Sales Order (after confirmation)",
     ["sale.action_report_saleorder"], ("sale.order", "saleorder")),
    ("print_purchase_order_document", "Print Purchase Order document (after confirmation)",
     ["purchase.action_report_purchase_order"], ("purchase.order", "purchase_order")),
    ("print_product_label_transfer", "Print product labels for validated transfer",
     ["stock.label_product_product"], ("product.product", "label")),
    ("print_picking_document_after_sale_order_confirmation",
     "Print Picking Document after Sales Order Validation",
     ["stock.action_report_picking"], ("stock.picking", "picking")),
    ("print_document_on_picking_after_po_confirmation",
     "Print Picking Document after Purchase Order Validation",
     ["stock.action_report_picking"], ("stock.picking", "picking")),
    ("print_document_on_invoice_validation", "Print Customer Invoice after Validation",
     ["account.account_invoices"], ("account.move", "invoice")),
    ("print_document_when_picking_status_change",
     "Print Delivery Slip on Picking Status becomes Ready",
     ["stock.action_report_delivery"], ("stock.picking", "delivery")),
    ("print_put_in_pack_package", "Print Package on Put in Pack for Internal Pickings",
     ["stock.action_report_package_barcode_small"], ("stock.package", "package")),
    ("print_product_label_when_packaging_on_transfer",
     "Print multiple product labels on Transfer based on pack qty(after val.)",
     ["product.report_product_template_label_2x7"], ("product.template", "label")),
]


def _find_report(env, xml_ids, fallback):
    for xml_id in xml_ids:
        report = env.ref(xml_id, raise_if_not_found=False)
        if report and report._name == "ir.actions.report":
            return report
    model, fragment = fallback
    if model in env:
        return env["ir.actions.report"].search(
            [("model", "=", model), ("report_name", "ilike", fragment)], limit=1)
    return env["ir.actions.report"]


def post_init_hook(env):
    """Create the (inactive) default print rules.

    Core report xml_ids change between Odoo versions, so the rules are created
    here and skipped (with a log line) when the core report no longer exists,
    instead of aborting the whole module installation.
    """
    Rule = env["printnode.rule"].with_context(active_test=False)
    for action_xmlid, description, report_xmlids, fallback in DEFAULT_RULES:
        action = env.ref("printnode_odoo_connector.%s" % action_xmlid, raise_if_not_found=False)
        if not action:
            _logger.warning("PrintNode: rule action %s not found, skipping default rule.", action_xmlid)
            continue
        report = _find_report(env, report_xmlids, fallback)
        if not report:
            _logger.warning("PrintNode: no core report found for default rule '%s', skipping.", description)
            continue
        if Rule.search([("action", "=", action.id), ("report_id", "=", report.id),
                        ("description", "=", description)], limit=1):
            continue
        Rule.create({
            "action": action.id,
            "report_id": report.id,
            "description": description,
            "domain": "[]",
            "active": False,
        })
