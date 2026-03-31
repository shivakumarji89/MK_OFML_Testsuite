import uuid
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom.minidom import parseString

from modules.snapper.generator import build_varcode_multi


def build_import_obx(items: list[dict]) -> str:
    """
    Build an OBX file from a list of decoded SKU items.

    Each item: {
        article: str,
        manufacturer_code: str,
        series_code: str,
        prog_id: str,
        properties: {prop_name: value},
        property_to_class: {prop_name: article_class},
    }

    All articles get updateState="Outdated" to force pCon re-resolution on Update.
    pdInfo is included per article so pCon locates the correct catalog.
    """
    session_id = str(uuid.uuid4())

    root = Element("cutBuffer")
    SubElement(root, "state", sessionId=session_id)
    SubElement(root, "versionInfo",
               vendorKey="EasternGraphics",
               appKey="EAI-Server",
               appVersion="4.18.3",
               bskXmlVersion="1.8.10")

    items_el = SubElement(root, "items")
    basket_ids: list[str] = []

    for item in items:
        bid = str(uuid.uuid4())
        basket_ids.append(bid)

        bsk = SubElement(items_el, "bskArticle",
                         basketId=bid,
                         itemType="BasketAggregate",
                         updateState="Outdated")

        SubElement(bsk, "manufacturer", id=item["manufacturer_code"])
        SubElement(bsk, "series", id=item["series_code"])

        base_nr = SubElement(bsk, "artNr", type="base")
        base_nr.text = item["article"]

        varcode = build_varcode_multi(item["properties"], item["property_to_class"])
        if varcode:
            vc_el = SubElement(bsk, "artNr", type="ofmlvarcode")
            vc_el.text = varcode

        SubElement(bsk, "pdInfo",
                   pdbType="ocd",
                   pkgName="::ofml::oi",
                   manufacturerId=item["manufacturer_code"],
                   seriesId=item["series_code"],
                   progId=item["prog_id"],
                   region="EURO",
                   salesOnly="false",
                   aggrSalesOnly="false")

    doc_calc = SubElement(root, "docCalculationChanges", ppName="STDB2B_WBK")
    for bid in basket_ids:
        SubElement(doc_calc, "itemCalculationChanges", id=bid)

    xml_bytes = tostring(root, encoding="unicode")
    return parseString(xml_bytes).toprettyxml(indent="  ")
