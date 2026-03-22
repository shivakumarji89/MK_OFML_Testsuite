import itertools
import uuid
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString


def compute_permutations(
    articles: list[str],
    dimensions: dict[str, list[str]],
) -> list[dict]:
    """
    Compute cartesian product of articles × all selected property values.

    Args:
        articles: list of base article codes to include
        dimensions: {property_name: [selected_values]}
            Property values that are hierarchy children (e.g. fabric colours)
            should already be resolved and either excluded or pre-assigned
            before calling this function.

    Returns:
        list of {article: str, properties: {prop_name: value}}
    """
    if not articles:
        return []

    if not dimensions:
        return [{"article": a, "properties": {}} for a in articles]

    prop_names = list(dimensions.keys())
    value_lists = [dimensions[p] for p in prop_names]

    results = []
    for article in articles:
        for combo in itertools.product(*value_lists):
            results.append({
                "article": article,
                "properties": dict(zip(prop_names, combo)),
            })
    return results


def build_varcode(article_class: str, properties: dict[str, str]) -> str:
    """
    Build an OFML varcode string from an article class and property assignments.
    Format: ArticleClass.Prop1=Val1;ArticleClass.Prop2=Val2
    Returns empty string if no properties.
    """
    if not properties:
        return ""
    parts = [f"{article_class}.{k}={v}" for k, v in properties.items()]
    return ";".join(parts)


def build_varcode_multi(
    properties: dict[str, str],
    property_to_class: dict[str, str],
    prop_val_to_class: dict[tuple, str] | None = None,
) -> str:
    """
    Build an OFML varcode with per-property article class prefixes.

    Each property may have a different article class prefix.
    Lookup order: prop_val_to_class[(prop, val)] first, then property_to_class[prop].

    Example output: "CLOUD_ATTR_ARM_CHAIR.Type=10;CLOUD_OPT.Base_Finish=R00"
    """
    parts = []
    for prop_name, value in properties.items():
        cls = None
        if prop_val_to_class:
            cls = prop_val_to_class.get((prop_name, value))
        if cls is None:
            cls = property_to_class.get(prop_name, "")
        if cls and prop_name:
            parts.append(f"{cls}.{prop_name}={value}")
    return ";".join(parts)


def build_obx(
    permutations: list[dict],
    article_class_map: dict[str, str],
    manufacturer_code: str,
    series_code: str,
    property_to_class: dict[str, str] | None = None,
    prop_val_to_class: dict[tuple, str] | None = None,
) -> str:
    """
    Build an OBX XML document from a list of permutations.

    Args:
        permutations: output of compute_permutations (list of {article, properties})
        article_class_map: {article_code: article_class} — from OCD artbase data
        manufacturer_code: e.g. "HM" — from ocd_article.csv col[2]
        series_code: e.g. "COSM" — from ocd_article.csv col[3]
        property_to_class: optional {prop_name: article_class} for per-property prefixes
        prop_val_to_class: optional {(prop_name, value): article_class} for finer-grained lookup

    Returns:
        Pretty-printed XML string.

    NOTE: The minimum required XML structure must be verified empirically against
    a real pCon installation. See design spec Section 10. If pCon's Update step
    fails to resolve entries, try:
    - Adding updateState='Outdated' (forces re-resolution)
    - Adding empty <features/> element
    - Adding <description type='short'><text lang='en'/></description> stub
    """
    session_id = str(uuid.uuid4())

    root = Element("cutBuffer")
    SubElement(root, "state", sessionId=session_id)
    SubElement(root, "versionInfo",
               vendorKey="EasternGraphics",
               appKey="EAI-Server",
               appVersion="4.18.3",
               bskXmlVersion="1.8.10")

    items = SubElement(root, "items")

    for perm in permutations:
        article_code = perm["article"]
        properties = perm["properties"]
        article_class = article_class_map.get(article_code, "")

        basket_article = SubElement(items, "bskArticle",
                                    basketId=str(uuid.uuid4()),
                                    itemType="BasketAggregate",
                                    updateState="UpToDate")

        SubElement(basket_article, "manufacturer", id=manufacturer_code)
        SubElement(basket_article, "series", id=series_code)

        base_artnr = SubElement(basket_article, "artNr", type="base")
        base_artnr.text = article_code

        if properties:
            if property_to_class is not None:
                varcode = build_varcode_multi(properties, property_to_class, prop_val_to_class)
            elif article_class:
                varcode = build_varcode(article_class, properties)
            else:
                varcode = ""
            if varcode:
                varcode_el = SubElement(basket_article, "artNr", type="ofmlvarcode")
                varcode_el.text = varcode

    xml_bytes = tostring(root, encoding="unicode")
    return parseString(xml_bytes).toprettyxml(indent="  ")
