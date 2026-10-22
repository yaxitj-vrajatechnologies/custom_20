# -*- coding: utf-8 -*-
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class FruugoFeedController(http.Controller):
    """Public HTTP endpoint that Fruugo polls to retrieve the product XML feed.

    URL pattern:  GET /fruugo/feed/<token>.xml
    - The token uniquely identifies the feed record.
    - The URL is fixed forever (unless the user explicitly regenerates the token).
    - No authentication required — the token itself acts as a secret.
    - Fruugo sets this URL once in the Retailer Portal and polls it automatically.
    """

    @http.route(
        '/fruugo/feed/<string:token>.xml',
        auth='public',
        type='http',
        methods=['GET'],
        csrf=False,
        sitemap=False,
    )
    def fruugo_feed_xml(self, token, **kwargs):
        """Serve the Fruugo XML feed for the given token."""
        if not token:
            return request.not_found()

        # Look up the feed by token — only serve active feeds
        feed = request.env['fruugo.feed'].sudo().search(
            [('feed_token', '=', token), ('state', '=', 'active')],
            limit=1,
        )

        if not feed:
            _logger.warning('Fruugo feed request: unknown or inactive token "%s"', token)
            return request.not_found()

        try:
            xml_bytes = feed._get_latest_xml()
            _logger.info(
                'Fruugo feed "%s" served: %d bytes', feed.name, len(xml_bytes)
            )
            return request.make_response(
                xml_bytes,
                headers=[
                    ('Content-Type', 'application/xml; charset=utf-8'),
                    ('Content-Disposition', 'inline; filename="fruugo_feed.xml"'),
                    ('Cache-Control', 'no-cache, no-store, must-revalidate'),
                    ('X-Feed-Name', feed.name),
                ],
            )
        except Exception as exc:
            _logger.exception('Fruugo feed "%s" serve error: %s', feed.name, exc)
            return request.make_response(
                b'<?xml version="1.0"?><error>Feed generation failed</error>',
                status=500,
                headers=[('Content-Type', 'application/xml; charset=utf-8')],
            )
