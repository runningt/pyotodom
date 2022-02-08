#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import os

from otodom.category import get_category_json
from otodom.offer import get_offer_information

log = logging.getLogger(__file__)

SCRAPE_LIMIT = os.environ.get("SCRAPE_LIMIT", None)

if __name__ == "__main__":
    input_dict = {}

    if os.getenv("PRICE_TO"):
        input_dict["priceMax"] = os.getenv("PRICE_TO")

    # input_dict['priceMin'] = 675000
    # input_dict['priceMax'] = 680000
    # parsed_category = get_category("wynajem", "mieszkanie", "gda", **input_dict)

    filters = {
        "areaMin": 40,
        "areaMax": 60,
        "market": "SECONDARY",
        "roomsNumber": ["TWO", "THREE", "FOUR"],
    }
    parsed_category = get_category_json(
        "sprzedaz", "mieszkanie", "krk", offers_per_page="10", limit=10, **filters
    )

    log.info("Offers in that category - {0}".format(len(parsed_category)))

    print("Offers in that category - {0}".format(len(parsed_category)))
    if SCRAPE_LIMIT:
        parsed_category = parsed_category[: int(SCRAPE_LIMIT)]
        log.info("Scarping limit - {0}".format(len(parsed_category)))

        print("Scarping limit - {0}".format(len(parsed_category)))

    for offer in parsed_category:
        log.info("Scarping offer - {0}".format(offer["detail_url"]))
        # ffer_detail = get_offer_information(offer["detail_url"], context=offer)
        # log.info("Scraped offer - {0}".format(offer_detail))
        print("Scraped offer - {0}".format(offer))
