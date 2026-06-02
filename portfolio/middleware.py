from __future__ import annotations

import re

from django.db import OperationalError, ProgrammingError
from django.utils import translation

from .translations import SUPPORTED_LANGUAGES, translate_ui


class AppLanguageMiddleware:
    """Apply the globally configured CasaFlow language to HTML responses."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language_code = self._language_code(request)
        request.casaflow_language_code = language_code
        translation.activate("de" if language_code == "de" else "en")
        try:
            response = self.get_response(request)
        finally:
            translation.deactivate()
        return self._translate_response(request, response, language_code)

    def _language_code(self, request):
        if request.path_info.startswith(("/static/", "/media/")):
            return "en"
        try:
            from .models import AppSettings

            configured = AppSettings.load().language_code
        except (OperationalError, ProgrammingError):
            configured = "en"
        return configured if configured in SUPPORTED_LANGUAGES else "en"

    def _translate_response(self, request, response, language_code):
        if language_code != "de" or getattr(response, "streaming", False):
            return response
        content_type = response.get("Content-Type", "")
        if "text/html" not in content_type:
            return response
        charset = getattr(response, "charset", None) or "utf-8"
        try:
            html = response.content.decode(charset)
        except UnicodeDecodeError:
            return response
        translated = self._translate_html_preserving_code(html, language_code)
        if translated == html:
            return response
        response.content = translated.encode(charset)
        response["Content-Length"] = str(len(response.content))
        return response

    def _translate_html_preserving_code(self, html: str, language_code: str) -> str:
        preserved_blocks = []

        def preserve(match):
            preserved_blocks.append(match.group(0))
            return f"__CASAFLOW_PRESERVED_BLOCK_{len(preserved_blocks) - 1}__"

        protected_html = re.sub(
            r"<(script|style|template)\b[^>]*>.*?</\1>",
            preserve,
            html,
            flags=re.IGNORECASE | re.DOTALL,
        )
        translated = self._translate_visible_text_and_safe_attributes(protected_html, language_code)
        for index, block in enumerate(preserved_blocks):
            translated = translated.replace(f"__CASAFLOW_PRESERVED_BLOCK_{index}__", block)
        return translated

    def _translate_visible_text_and_safe_attributes(self, html: str, language_code: str) -> str:
        def translate_tag(match):
            tag = match.group(0)

            def translate_attribute(attribute_match):
                name, quote, value = attribute_match.groups()
                return f'{name}={quote}{translate_ui(value, language_code)}{quote}'

            return re.sub(
                r"\b(data-tooltip|placeholder|title|aria-label|alt)=(['\"])(.*?)\2",
                translate_attribute,
                tag,
                flags=re.IGNORECASE | re.DOTALL,
            )

        def translate_segment(match):
            tag = match.group("tag")
            if tag is not None:
                return translate_tag(match)
            return translate_ui(match.group("text") or "", language_code)

        return re.sub(
            r"(?P<tag><[^>]+>)|(?P<text>[^<]+)",
            translate_segment,
            html,
            flags=re.DOTALL,
        )
