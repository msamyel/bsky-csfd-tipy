import unittest
from unittest.mock import patch
import main

class TestGetRandomId(unittest.TestCase):

    @patch('main.random.randint')
    @patch('os.getenv')
    def test_get_random_id(self, mock_getenv, mock_randint):
        test_cases = [
            ('1-5,10-15', 3, 4),   # (RANGES, randint return value, expected result)
            ('1-5,10-15', 7, 12),
            ('0-1000,2000-3000', 1500, 2499),
            ('0-1000,2000-3000', 2001, 3000)
        ]

        for ranges, randint_value, expected in test_cases:
            with self.subTest(ranges=ranges, randint_value=randint_value, expected=expected):
                # Mock the environment variable RANGES
                mock_getenv.return_value = ranges
                # Mock random.randint to return a specific value
                mock_randint.return_value = randint_value

                result = main.get_random_id()
                self.assertEqual(result, expected)

        
if __name__ == '__main__':
    unittest.main()