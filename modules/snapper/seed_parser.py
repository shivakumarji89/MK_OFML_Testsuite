import xml.etree.ElementTree as ET


class SeedParseError(ValueError):
    """Raised when the OBX XML is malformed or missing required fields."""
    pass


def parse_seed(xml_string: str) -> dict:
    """
    Parse a pCon OBX XML string and extract seed data from the first bskArticle.

    Args:
        xml_string: Full content of an OBX file as a string.

    Returns:
        {
            "article": str,           # base article code, e.g. "NOCLE4"
            "manufacturer": str,      # e.g. "HM"
            "series": str,            # e.g. "CLOUD"
            "properties": [
                {
                    "name": str,          # property name, e.g. "Type"
                    "article_class": str, # e.g. "CLOUD_ATTR_ARM_CHAIR"
                    "seed_value": str,    # the value from the seed OBX
                },
                ...
            ]
        }

    Raises:
        SeedParseError: if the XML cannot be parsed, no bskArticle is found,
                        or required fields (manufacturer, series, base artNr,
                        ofmlvarcode artNr) are missing.
    """
    try:
        root = ET.fromstring(xml_string)
    except ET.ParseError as e:
        raise SeedParseError(f"Invalid XML: {e}") from e

    article_el = root.find(".//bskArticle")
    if article_el is None:
        raise SeedParseError("No <bskArticle> element found in OBX")

    mfr_el = article_el.find("manufacturer")
    if mfr_el is None or not mfr_el.get("id"):
        raise SeedParseError("Missing <manufacturer id='...'> in bskArticle")
    manufacturer = mfr_el.get("id")

    series_el = article_el.find("series")
    if series_el is None or not series_el.get("id"):
        raise SeedParseError("Missing <series id='...'> in bskArticle")
    series = series_el.get("id")

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
        raise SeedParseError("Missing <artNr type='ofmlvarcode'> in bskArticle")

    properties = _parse_varcode(varcode_str)

    return {
        "article": article_code,
        "manufacturer": manufacturer,
        "series": series,
        "properties": properties,
    }


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
