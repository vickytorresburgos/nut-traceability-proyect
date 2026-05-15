import sys
import logging
from engine.pipeline import process_caliber_image

logging.basicConfig(level=logging.INFO)
res = process_caliber_image("test-img/caliber.png")
print(res)
