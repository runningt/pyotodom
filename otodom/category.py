#!/usr/bin/python
# -*- coding: utf-8 -*-

import logging
import sys
from bs4 import BeautifulSoup

from otodom import WHITELISTED_DOMAINS, BASE_URL
from otodom.utils import get_response_for_url, get_url

if sys.version_info < (3, 3):
    from urlparse import urlparse
else:
    from urllib.parse import urlparse


log = logging.getLogger(__file__)


def _price_to_float(price: str) -> float:
    try:
        filtered = "".join(d for d in price if d.isdigit() and d.isalpha or d in [",", "."]).replace(",",".")
        return float(filtered)
    except ValueError:
        return 0.0


def parse_category_offer(offer_markup):
    """
    A method for getting the most important data out of an offer markup.

    :param offer_markup: a requests.response.content object
    :rtype: dict(string, string)
    :return: see the return section of :meth:`scrape.category.get_category` for more information
    """
    html_parser = BeautifulSoup(offer_markup, "html.parser")
    link = html_parser.find("a")
    url = link.attrs['href']
    if not url:
        # detail url is not present
        return {}
    offer_id = url.split("-")[-1]
    url = BASE_URL + url
    image = html_parser.find("img")
    image = image.get("src","").split(";")[0] or image.text
    article = html_parser.find("article")
    title = article.find("h3", {"data-cy":"listing-item-title"})
    title = title.text.strip() if title else ""
    data = article.findAll("p")
    price = _price_to_float(data[1].text)
    size = ""
    rooms = ""
    per_m2 = ""
    try:
        details = data[2]
        details = details.findAll("span")
        if len(details) > 2:
            rooms = "".join(filter(str.isdigit, details[0].text))
            size = details[1].text.strip()
            per_m2 = _price_to_float(details[2].text)
    except IndexError:
        pass

    # TODO: add poster
    # posters = article.find("div/span")
    # if len(posters)> 2:
    #    poster = posters[1].text if posters[1].text else posters[2].text or ""
    # else:
    #   poster = ""
    return {
        'detail_url': url,
        'offer_id': offer_id,
        # 'poster': poster,
        'image': image,
        'price': price,
        'size': size,
        'rooms': rooms,
        'price_per_m2' : per_m2
    }


def parse_category_content(markup, get_promoted=False):
    """
    A method for getting a list of all the offers found in the markup.

    :param markup: a requests.response.content object
    :get_promoted: True if promoted offers should be added to results
    :rtype: list of parsed offers dicts
    """
    html_parser = BeautifulSoup(markup, "html.parser")

    search_listings = html_parser.findAll("div", {"data-cy":"search.listing"})
    if len(search_listings) > 1:
        if not get_promoted:
            listing = search_listings[1]
        else:
            listing = html_parser
    elif len(search_listings) ==1:
        listing = search_listings[0]
    else:
        return []

    offers = listing.findAll("a", {"data-cy":"listing-item-link"})
    parsed_offers = [
        parse_category_offer(str(offer)) for offer in offers
    ]
    return parsed_offers


def get_category_number_of_pages(markup):
    """
    A method that returns the maximal page number for a given markup, used for pagination handling.

    :param markup: a requests.response.content object
    :rtype: int
    """
    html_parser = BeautifulSoup(markup, "html.parser")
    navigation = html_parser.find("div", attrs={"role":"navigation"})
    buttons = html_parser.findAll("button", recursive=True)
    if not navigation:
        return 1
    #pages = navigation.findAll("button", recursive=True)
    res = [1]
    for page in buttons:
        try:
            num = int(page.text)
            res.append(num)
        except:
            pass
    return max(res)



def was_category_search_successful(markup):
    html_parser = BeautifulSoup(markup, "html.parser")
    has_warning = bool(html_parser.find(class_="search-location-extended-warning"))
    return not has_warning

def get_num_offers_from_markup(markup):
    """
    Get total number of offers scrapping page
    """
    html_parser = BeautifulSoup(markup, "html.parser")
    num_offers = html_parser.find("strong", {"data-cy":"search.listing-panel.label.ads-number"})
    try:
        return int(num_offers.findAll("span")[-1].text)
    except ValueError:
        return 0

def get_distinct_category_page(page, main_category, detail_category, region, **filters):
    """A method for scraping just the distinct page of a category"""
    parsed_content = []
    url = get_url(main_category, detail_category, region, "72", page, **filters)
    content = get_response_for_url(url).content

    parsed_content.extend(parse_category_content(content))

    return parsed_content


def get_category(main_category, detail_category, region, limit="400", **filters):
    """
    Scrape OtoDom search results based on supplied parameters.

    :param main_category: "wynajem" or "sprzedaz", should not be empty
    :param detail_category: "mieszkanie", "dom", "pokoj", "dzialka", "lokal", "haleimagazyny", "garaz", or
                            empty string for any
    :param region: a string that contains the region name. Districts, cities and voivodeships are supported. The exact
                    location is established using OtoDom's API, just as it would happen when typing something into the
                    search bar. Empty string returns results for the whole country. Will be ignored if either 'city',
                    'region', '[district_id]' or '[street_id]' is present in the filters.
    :param filters: the following dict contains every possible filter with examples of its values, but can be empty:

    ::

        filters = {
            'distanceRadius: 0,  # distance from region
            'priceMin': 0,  # minimal price
            'priceMax': 0,  # maximal price
            'pricePerMeterMin': 0  # maximal price per square meter, only used for apartments for sale
            'pricePerMeterMax': 0  # minimal price per square meter, only used for apartments for sale
            'market': [PRIMARY, SECONDARY]  # enum: PRIMARY, SECONDARY
            'buildingMaterial': [BRICK, CONCRETE]  # enum: BRICK, WOOD, BREEZEBLOCK, HYDROTON, CONCRETE_PLATE, CONCRETE,
            SILIKAT, CELLULAR_CONCRETE, OTHER, REINFORCED_CONCRETE, only used for apartments for sale
            'areaMin': 0,  # minimal surface
            'areaMax: 0,  # maximal surface
            roomsNumber': [ONE, TWO, THREE]',  # number of rooms, enum: from "ONE" to "TEN", or "MORE"
            #'[private_business]': 'private',  # poster type, enum: private, business
            'hasOpenDay': 0,  # whether or not the poster organises an open day
            'isExclusiveOffer': 0,  # whether or not the offer is otodom exclusive
            #'[filter_enum_rent_to_students][]': 0,  # whether or not the offer is aimed for students, only used for
                apartments for rent
            'floors': 'CELLAR',  # enum: CELLAR, ground_floor, floor_1-floor_10, floor_higher_10,
                garret
            'floorsNumberMin': 1,  # minimal number of floors in the building
            'floorsNumberMax': 1,  # maximal number of floors in the building
            'buildingType': enum BLOCK,TENEMENT,HOUSE,INFILL,RIBBON,APARTMENT,LOFT
            #'[filter_enum_heating][]': 'urban',  # enum: urban, gas, tiled_stove, electrical, boiler_room, other
            'buildYearMin': 1980,  # minimal year the building was built in
            'buildYearMax': 2016,  # maximal year the building was built in
            'extras': ['BALCONY', 'BASEMENT'],  # enum: AIR_CONDITIONING, BALCONY, BASEMENT, GARAGE, GARDEN, LIFT, NON_SMOKERS_ONLY, SEPARATE_KITCHEN, TERRACE, TWO_STOREY, USABLE_ROOM]
            #'[filter_enum_media_types][]': ['internet', 'phone'],  # enum: internet, cable-television, phone
            #'[free_from]': 'from_now',  # when will it be possible to move in, enum: from_now, 30, 90
            'daysSinceCreated': 3,  # when was the offer posted on otodom in days, enum: 1, 3, 7, 14
            'id': 48326376,  # otodom offer ID, found at the very bottom of each offer
            'description': 'wygodne',  # the resulting offers' descriptions must contain this string
            'hasPhotos': false,  # bool whether or not the offer contains photos
            'hasMovie': false,  # bool whether or not the offer contains video
            'hasWalkaround'': false  # bool whether or not the offer contains a walkaround 3D view
            'city':  # lowercase, no diacritics, '-' instead of spaces, _city_id at the end
            'voivodeship':  # lowercase, no diacritics, '-' instead of spaces
            'district_id': from otodom API
            'street_id': from otodom API
        }

    :rtype: list of dict(string, string)
    :return: Each of the dictionaries contains the following fields:

    ::

        'detail_url' - a link to the offer
        'offer_id' - the internal otodom's offer ID, not to be mistaken with the '[id]' field from the input_dict
        'poster' - a piece of information about the poster. Could either be a name of the agency or "Oferta prywatna"
    """
    parsed_content = []
    max_offers = 0
    offers = 0
    page = 1

    while offers == 0 or offers < max_offers and offers_parsed >= int(limit):
        url = get_url(main_category, detail_category, region, limit, page, **filters)
        content = get_response_for_url(url).content
        if not was_category_search_successful(content):
            log.warning("Search for category wasn't successful", url)
            return []
        if not max_offers:
            max_offers = max(12000, get_num_offers_from_markup(content))
        parsed_page = parse_category_content(content)
        offers_parsed = len(parsed_page)
        parsed_content.extend(parsed_page)
        offers = len(parsed_content)
        page+=1
    return parsed_content

