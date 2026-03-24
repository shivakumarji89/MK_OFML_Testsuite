import xml.etree.ElementTree as ET


class SeedParseError(ValueError):
    """Raised when the OBX XML is malformed or missing required fields."""
    pass


def parse_seed(xml_string: str) -> dict:
    """
    Parse a pCon OBX XML string and extract seed data from ALL bskArticle elements.

    Returns:
        {
            "manufacturer": str,
            "series": str,
            "articles": [
                {
                    "article": str,        # base article code
                    "label": str | None,   # short description (English preferred)
                    "properties": [
                        {"name": str, "article_class": str, "seed_value": str},
                        ...
                    ],
                    "article_xml": str,    # serialised bskArticle element (for seed templates)
                },
                ...
            ],
            "raw_xml": str,
        }

    Raises:
        SeedParseError: if the XML is malformed, no bskArticle found,
                        or required fields are missing in the first article.
    """
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as e:
        raise SeedParseError(f"Invalid XML: {e}") from e

    article_elements = root.findall(".//bskArticle")
    if not article_elements:
        raise SeedParseError("No <bskArticle> element found in OBX")

    # manufacturer and series are read from the first article (shared across all)
    first = article_elements[0]
    mfr_el = first.find("manufacturer")
    if mfr_el is None or not mfr_el.get("id"):
        raise SeedParseError("Missing <manufacturer id='...'> in bskArticle")
    manufacturer = mfr_el.get("id")

    series_el = first.find("series")
    if series_el is None or not series_el.get("id"):
        raise SeedParseError("Missing <series id='...'> in bskArticle")
    series = series_el.get("id")

    articles = []
    info_messages = []
    for article_el in article_elements:
        article_code = None
        varcode_str = None
        for artnr in article_el.findall("artNr"):
            t = artnr.get("type", "")
            if t == "base":
                article_code = (artnr.text or "").strip()
            elif t == "ofmlvarcode":
                varcode_str = (artnr.text or "").strip()

        if not article_code:
            raise SeedParseError("Missing <artNr type='base'> in bskArticle")
        if not varcode_str:
            info_messages.append(f"Article {article_code} excluded. No OFMLVarcode found.")
            continue

        properties = _parse_varcode(varcode_str)
        label = _extract_short_description(article_el)
        article_xml = ET.tostring(article_el, encoding="unicode")

        articles.append({
            "article": article_code,
            "label": label,
            "properties": properties,
            "article_xml": article_xml,
        })

    return {
        "manufacturer": manufacturer,
        "series": series,
        "articles": articles,
        "info_messages": info_messages,
        "raw_xml": xml_string,
    }


def _extract_short_description(article_el: ET.Element) -> str | None:
    """
    Extract the short description text from a bskArticle element.
    Prefers English; falls back to the first available language.
    Returns None if no short description element is present.
    """
    desc_el = next(
        (d for d in article_el.findall("description") if d.get("type") == "short"),
        None,
    )
    if desc_el is None:
        return None

    texts = desc_el.findall("text")
    if not texts:
        return None

    en_text = next((t for t in texts if t.get("lang") == "en"), None)
    if en_text is not None and en_text.text:
        return en_text.text.strip()

    first_text = next((t for t in texts if t.text), None)
    return first_text.text.strip() if first_text is not None else None


def _parse_varcode(varcode_str: str) -> list[dict]:
    """
    Parse an OFML varcode string into a list of property dicts.

    Example input: "CLOUD_ATTR_ARM_CHAIR.Type=10;CLOUD_OPT.Base_Finish=R00"
    Example output:
        [
            {"name": "Type", "article_class": "CLOUD_ATTR_ARM_CHAIR", "seed_value": "10"},
            {"name": "Base_Finish", "article_class": "CLOUD_OPT", "seed_value": "R00"},
        ]

    Segments that do not contain '.' or '=' are skipped silently.
    """
    properties = []
    for segment in varcode_str.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        dot_idx = segment.find(".")
        if dot_idx == -1:
            continue
        article_class = segment[:dot_idx]
        remainder = segment[dot_idx + 1:]
        eq_idx = remainder.find("=")
        if eq_idx == -1:
            continue
        prop_name = remainder[:eq_idx]
        seed_value = remainder[eq_idx + 1:]
        if article_class and prop_name:
            properties.append({
                "name": prop_name,
                "article_class": article_class,
                "seed_value": seed_value,
            })
    return properties
