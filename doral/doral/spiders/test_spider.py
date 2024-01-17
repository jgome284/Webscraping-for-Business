# System imports
import logging, os
import re
import scrapy
from scrapy.http import Response
from scrapy_playwright.page import PageMethod
from typing import Iterator

# Local imports
from doral.items import BusinessItem

# Remove spider log file if it exists
if os.path.exists('testy.log'):
    os.remove('testy.log')
    
# Create logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Create file handler
fh = logging.FileHandler('testy.log')
fh.setLevel(logging.DEBUG)

# Create console handler
ch = logging.StreamHandler()
ch.setLevel(logging.ERROR)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Add formatter to handlers
fh.setFormatter(formatter)
ch.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(fh)
logger.addHandler(ch)

# Test messages
logger.debug('Debug message')
logger.info('Info message')
logger.warning('Warning message')
logger.error('Error message')
logger.critical('Critical message')

class TestSpider(scrapy.Spider):
    name = "testy"
        
    def start_requests(self) -> Iterator[scrapy.Request]: # default callback for requests is self.parse
        
        start_urls: list[str] = [
            'https://www.cityofdoral.com/businesses/local-discounts/'
        ]
        
        for url in start_urls:
            yield scrapy.Request(
                url = url,
                errback = self.errback,
                meta = dict(
                    playwright = True,
                    playwright_include_page = True,
                    playwright_page_methods = [
                        PageMethod('wait_for_selector', 'div.row.bus_row')
                        ]
                    )
                )
            
    async def parse(self, response: Response) -> BusinessItem:
        page = response.meta["playwright_page"]
        await page.close()
        
        # Initalize BusinessItem
        doral_item = BusinessItem()
        
        for business in response.xpath('//div[@class="row bus_row"]'):
            
            # retreive business info...        
            doral_item['business_name'] = business.xpath('h3/text()').get()
            doral_item['industry'] = business.xpath('h3/div/text()').get()
            doral_item['offer'] = business.xpath('section[@class="col-sm-12 label-dis"]/div/text()').get()
            doral_item['website'] = business.xpath('section[@class="col-sm-12 bus_site"]/a/@href').get()
            
            # follow business website
            if doral_item['website'] is not None:
                try:
                    yield response.follow(
                        url = doral_item['website'], 
                        callback = self.parse_phone,
                        errback = self.errback,
                        meta = dict(
                            item = doral_item,
                            playwright = True,
                            playwright_include_page = True,
                            playwright_page_methods = [
                                PageMethod('wait_for_selector', 'html ::text')
                                ]
                            )
                        )
                    
                except ValueError as ve:
                    self.log(f"ValueError: {ve} for URL: {doral_item['website']}")
            else:
                doral_item['phone'] = None
                yield doral_item                

    async def errback(self, failure):
        # When passing playwright_include_page=True, make sure pages are always closed when they are no longer used. 
        # It's recommended to set a Request errback to make sure pages are closed even if a request fails 
        # (if playwright_include_page=False pages are automatically closed upon encountering an exception).
        # This is important, as open pages count towards the limit set by PLAYWRIGHT_MAX_PAGES_PER_CONTEXT 
        # and crawls could freeze if the limit is reached and pages remain open indefinitely.
        self.log(f"Error processing {repr(failure)}", level=logging.ERROR)
        page = failure.request.meta["playwright_page"]
        await page.close()
                
    async def parse_phone(self, response: Response):
        page = response.meta["playwright_page"]
        await page.close()
                
        # Retreive original item from meta
        doral_item = response.meta['item']
        
        # Extract content from business site
        content: str = ' '.join(response.css('html ::text').getall())  # join elements of text with space
                
        # Define a regular expression pattern for matching phone numbers
        phone_number_pattern = re.compile(
                r"""
                (?<![\d.])         # negative lookbehind to ensure no digits or decimals before
                (\+0?1[\s.-]?)?    # optional country code
                \(?\d{3}\)?[\s.-]? # area code
                \d{3}[\s.-]?       # 3 digit telephone prefix
                \d{4}              # 4 digit line number
                (?![\d.])          # negative lookahead to ensure no digits or decimals after
                """
                , re.X)
        
        # Find all matches of the pattern in website content
        phone_numbers_iter: Iterator[re.Match[str]] = phone_number_pattern.finditer(content)
        
        # Process Iterator to retrieve the entire match (group 0) for all numbers
        phone_numbers: list[str] = [phone.group(0) for phone in phone_numbers_iter]
        
        # Discard duplicate phone numbers, remove area code and none digit charcters, and store in item
        doral_item['phone']: set[str] = set(map(lambda x: re.sub('(\+0?1[\s.-]?)|[-.() ]', '', x), phone_numbers))
                
        # Yield the updated item
        yield doral_item
