from dotenv import load_dotenv
import os
import random

load_dotenv()

def get_random_id():
    ranges = os.getenv('RANGES').split(',')
    range_ints = []
    total_id_count = 0
    for range in ranges:
        split_range = range.split('-')
        start = int(split_range[0])
        end = int(split_range[1])
        range_ints.append((start, end))
        total_id_count += end - start + 1
    
    random_id_index = random.randint(0, total_id_count)
    for start, end in range_ints:
        if random_id_index <= end - start:
            return start + random_id_index
        else:
            random_id_index -= end - start + 1






